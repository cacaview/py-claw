"""Forked agent subprocess management via subprocess.Popen with NDJSON stdio."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    pass

from py_claw.fork.protocol import (
    ForkHistoryMessage,
    ForkInitMessage,
    ForkMcpCallMessage,
    ForkMessage,
    ForkOutputMessage,
    ForkResultMessage,
    ForkStopMessage,
    ForkTurnMessage,
    NDJSONParser,
)

logger = logging.getLogger(__name__)


@dataclass
class ForkedAgentProcess:
    """Manages a forked py-claw child agent subprocess.

    Uses subprocess.Popen with stdio pipes for JSON-lines communication.
    Thread-safe for concurrent send/recv operations.

    Lifecycle:
        1. spawn()            - creates the child process
        2. send_init()         - initialize child with session config
        3. send_turn() / send_turn_sync()  - send turns
        4. iter_messages()      - yields received messages (for streaming)
        5. terminate() / kill() - clean shutdown
    """
    session_id: str
    exec_path: str | None = None
    system_prompt: str = ""
    model: str | None = None
    allowed_tools: list[str] | None = None
    cwd: str = ""
    mcp_servers: list[dict[str, Any]] | None = None
    parent_transcript: list[dict[str, Any]] = field(default_factory=list)
    # Isolation context for worktree/resource isolation
    isolation: dict[str, Any] | None = None

    _process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default=None, init=False, repr=False)
    _parser: NDJSONParser = field(default_factory=NDJSONParser, init=False, repr=False)
    _stdout_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stderr_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _message_queue: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _queue_cv: threading.Condition = field(default=None, init=False, repr=False)
    _eof: bool = field(default=False, init=False, repr=False)
    # Pending sync turns: turn_count → Event for send_turn_sync
    _pending_turns: dict[int, threading.Event] = field(default_factory=dict, init=False, repr=False)
    # Results for pending sync turns: turn_count → result dict
    _pending_results: dict[int, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        lock = threading.RLock()
        object.__setattr__(self, "_lock", lock)
        object.__setattr__(self, "_queue_cv", threading.Condition(lock))

    def spawn(self) -> None:
        """Spawn the child py-claw subprocess."""
        with self._lock:
            if self._process is not None:
                raise RuntimeError("Process already spawned")

            exec_path = self.exec_path or sys.executable
            cmd = [exec_path, "-m", "py_claw.fork.child_main"]

            env = dict(__import__("os").environ)

            self._process = subprocess.Popen(
                cmd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            self._stderr_thread = threading.Thread(
                target=self._read_stderr,
                args=(self._process.stderr,),
                daemon=True,
                name=f"fork-stderr-{self.session_id}",
            )
            self._stderr_thread.start()

            self._stdout_thread = threading.Thread(
                target=self._read_stdout,
                daemon=True,
                name=f"fork-stdout-{self.session_id}",
            )
            self._stdout_thread.start()

    def send_init(self) -> None:
        """Send init message to child."""
        msg = ForkInitMessage(
            session_id=self.session_id,
            system_prompt=self.system_prompt,
            model=self.model,
            allowed_tools=self.allowed_tools,
            cwd=self.cwd,
            mcp_servers=self.mcp_servers,
            isolation=self.isolation,
        )
        self._send(msg)

    def send_turn(self, query_text: str, turn_count: int) -> None:
        """Send a turn message to child (async — use send_turn_sync for blocking wait)."""
        msg = ForkTurnMessage(query_text=query_text, turn_count=turn_count)
        self._send(msg)

    def send_turn_sync(self, query_text: str, turn_count: int, timeout: float = 60.0) -> dict[str, Any]:
        """Send a turn message and wait for the result synchronously.

        Args:
            query_text: The user message to send.
            turn_count: Monotonic counter for result routing.
            timeout: Maximum seconds to wait for result.

        Returns:
            Result dict with keys: assistant_text, stop_reason, usage, model_usage, tool_calls.

        Raises:
            RuntimeError: If subprocess dies or timeout expires.
        """
        event = threading.Event()
        # Register before sending — no lock needed (GIL protects dict + event)
        self._pending_turns[turn_count] = event
        try:
            self.send_turn(query_text, turn_count)
            # Release GIL while waiting — _read_stdout thread needs to set the event
            if not event.wait(timeout=timeout):
                raise RuntimeError(f"Turn {turn_count} timed out after {timeout}s")
        finally:
            self._pending_turns.pop(turn_count, None)
        result = self._pending_results.pop(turn_count, None)
        if result is None:
            raise RuntimeError(f"No result received for turn {turn_count}")
        return result

    def send_history(self, exchanges: list[dict[str, str]]) -> None:
        """Send conversation history to persistent subprocess."""
        msg = ForkHistoryMessage(type="history", exchanges=exchanges)
        self._send(msg)

    def send_mcp_call(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str,
    ) -> None:
        """Send an MCP tool call to the child for execution via its MCP servers."""
        msg = ForkMcpCallMessage(
            type="mcp_call",
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            call_id=call_id,
        )
        self._send(msg)

    def send_stop(self) -> None:
        """Send stop message to child."""
        msg = ForkStopMessage()
        self._send(msg)

    def iter_messages(self, timeout: float | None = None) -> list[dict[str, Any]]:
        """Return available messages from the child."""
        with self._queue_cv:
            while not self._message_queue and not self._eof:
                self._queue_cv.wait(timeout=timeout)
                if not self._message_queue and self._eof:
                    break
            messages = list(self._message_queue)
            self._message_queue.clear()
        return messages

    def terminate(self, timeout: float = 5.0) -> int | None:
        """Gracefully terminate the child process."""
        with self._lock:
            if self._process is None:
                return None
            self.send_stop()
            try:
                if self._process.stdin:
                    self._process.stdin.flush()
                    self._process.stdin.close()
            except Exception:
                pass
            try:
                exit_code = self._process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
                exit_code = self._process.wait()
            self._process = None
            return exit_code

    def kill(self) -> int | None:
        """Force kill the child process."""
        with self._lock:
            if self._process is None:
                return None
            self._process.kill()
            exit_code = self._process.wait()
            self._process = None
            return exit_code

    @property
    def is_running(self) -> bool:
        """Check if the subprocess is still running."""
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def _send(self, msg: ForkMessage) -> None:
        """Send a message to child stdin."""
        with self._lock:
            if self._process is None or self._process.stdin is None:
                raise RuntimeError("Process not running")
            try:
                line = json.dumps(asdict(msg)) + "\n"
                self._process.stdin.write(line)
                self._process.stdin.flush()
            except OSError:
                # Child process closed stdin (already exited)
                logger.debug("Child process stdin closed; assuming exited")
                self._eof = True

    def _read_stdout(self) -> None:
        """Read stdout in a thread, parse NDJSON, route/queue messages."""
        if self._process is None or self._process.stdout is None:
            return
        try:
            while True:
                line = self._process.stdout.readline()
                if not line:
                    break
                messages = self._parser.parse(line)
                with self._queue_cv:
                    for msg in messages:
                        self._route_message(msg)
                    self._queue_cv.notify_all()
        except Exception as exc:
            logger.error("Error reading stdout from forked agent: %s", exc)
        finally:
            with self._queue_cv:
                self._eof = True
                self._queue_cv.notify_all()

    def _route_message(self, msg: dict[str, Any]) -> None:
        """Route a received message: result → pending sync caller; others → queue."""
        if msg.get("type") == "result":
            turn_count = msg.get("turn_count")
            with self._lock:
                event = self._pending_turns.get(turn_count)
            if event is not None:
                with self._lock:
                    self._pending_results[turn_count] = msg
                event.set()
                return
        self._message_queue.append(msg)

    def _read_stderr(self, stderr: TextIO | None) -> None:
        """Read stderr for logging purposes."""
        if stderr is None:
            return
        try:
            for line in iter(stderr.readline, ""):
                if line:
                    logger.debug("forked agent stderr: %s", line.strip())
        except Exception:
            pass
