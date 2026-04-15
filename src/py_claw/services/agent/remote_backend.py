"""
Remote/tmux agent backend service.

Provides remote agent execution via tmux or SSH, complementing
the local subprocess backend (ForkedAgentBackend).

Supports:
- TmuxAgentBackend: Agent execution in a tmux session
- SSHAgentBackend: Agent execution over SSH

Remote backends implement the same QueryBackend interface as
ForkedAgentBackend, allowing transparent swapping.
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ─── Backend Type ───────────────────────────────────────────────────────────────


@dataclass
class RemoteBackendConfig:
    """Configuration for remote agent backend."""

    backend_type: str = "tmux"  # "tmux" or "ssh"
    host: str | None = None  # SSH host
    user: str | None = None  # SSH user
    port: int | None = None  # SSH port
    key_file: str | None = None  # SSH private key
    tmux_session: str | None = None  # tmux session name
    remote_cwd: str | None = None  # Remote working directory
    python_path: str = "python"  # Python interpreter on remote


# ─── Base Remote Backend ───────────────────────────────────────────────────────


class RemoteAgentBackend:
    """Base class for remote agent backends.

    Implements the QueryBackend interface for remote agent execution.
    Subclasses must implement _start_remote, _send_command, and _close.
    """

    def __init__(self, config: RemoteBackendConfig):
        """Initialize the remote backend.

        Args:
            config: Remote backend configuration
        """
        self._config = config
        self._connected = False
        self._lock = threading.Lock()

    def run_turn(self, prepared, context) -> "BackendTurnResult":
        """Execute a turn on the remote agent.

        Args:
            prepared: Prepared query with query_text
            context: Query context with session_id, state, transcript

        Returns:
            BackendTurnResult with assistant response
        """
        from py_claw.query.backend import BackendToolCall, BackendTurnResult

        if not self._connected:
            self._start_remote(context)

        query_text = prepared.query_text or ""

        # Send the turn to the remote agent
        self._send_command({"type": "turn", "query_text": query_text})

        # Wait for result
        result = self._wait_for_result()

        return BackendTurnResult(
            assistant_text=result.get("assistant_text", ""),
            stop_reason=result.get("stop_reason", "end_turn"),
            usage=result.get("usage", {}),
            model_usage=result.get("model_usage", {}),
            tool_calls=[
                BackendToolCall(
                    tool_name=tc.get("tool_name", ""),
                    arguments=tc.get("arguments", {}),
                    tool_use_id=tc.get("tool_use_id"),
                    parent_tool_use_id=tc.get("parent_tool_use_id"),
                )
                for tc in result.get("tool_calls", [])
            ],
        )

    def _start_remote(self, context) -> None:
        """Start the remote agent session.

        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def _send_command(self, cmd: dict[str, Any]) -> None:
        """Send a command to the remote session.

        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def _wait_for_result(self) -> dict[str, Any]:
        """Wait for a result from the remote session.

        Default implementation uses polling with iter_messages.
        Subclasses can override for event-driven approaches.
        """
        timeout = 120.0  # 2 minute timeout
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            messages = self._recv_messages()
            for msg in messages:
                msg_type = msg.get("type")
                if msg_type == "output":
                    logger.debug("remote agent output: %s", msg.get("delta", ""))
                elif msg_type == "result":
                    return msg
                elif msg_type == "error":
                    raise RuntimeError(f"Remote agent error: {msg.get('message', 'unknown')}")
            time.sleep(0.5)
        raise TimeoutError("Remote agent turn timed out")

    def _recv_messages(self) -> list[dict[str, Any]]:
        """Receive messages from the remote session.

        Subclasses should override for streaming approaches.
        """
        return []

    def close(self) -> None:
        """Close the remote session.

        Must be implemented by subclasses.
        """
        raise NotImplementedError


# ─── Tmux Backend ───────────────────────────────────────────────────────────────


@dataclass
class TmuxAgentBackend(RemoteAgentBackend):
    """Remote agent backend using tmux.

    Executes the agent in a tmux session on the local or remote machine.
    """

    _tmux_session: str = field(default="", init=False)
    _pane_id: str | None = field(default=None, init=False)

    def __init__(self, config: RemoteBackendConfig):
        if config.backend_type != "tmux":
            raise ValueError(f"TmuxAgentBackend requires backend_type='tmux', got '{config.backend_type}'")
        super().__init__(config)

    def _start_remote(self, context) -> None:
        """Start the agent in a tmux session."""
        import uuid

        session_name = self._config.tmux_session or f"py-claw-agent-{uuid.uuid4().hex[:8]}"
        self._tmux_session = session_name

        # Build command to run
        python_path = self._config.python_path
        cmd = [
            python_path, "-m", "py_claw.fork.child_main",
        ]

        # Create tmux session and send command
        # Use tmux new-session -d to create detached session
        create_cmd = ["tmux", "new-session", "-d", "-s", session_name, " ".join(cmd)]
        subprocess.run(
            " ".join(create_cmd),
            shell=True,
            capture_output=True,
        )

        self._connected = True
        logger.debug("Started tmux session: %s", session_name)

    def _send_command(self, cmd: dict[str, Any]) -> None:
        """Send a command to the tmux session via stdin pipe."""
        if not self._tmux_session:
            raise RuntimeError("Tmux session not started")

        line = json.dumps(cmd) + "\n"
        # Send to tmux session's stdin using tmux send-keys
        subprocess.run(
            ["tmux", "send-keys", "-t", self._tmux_session, line],
            capture_output=True,
        )

    def _recv_messages(self) -> list[dict[str, Any]]:
        """Receive messages by capturing tmux pane output."""
        # This is a simplified approach - real implementation would
        # use a more efficient method like socket or FIFO
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", self._tmux_session, "-p"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Parse NDJSON from captured pane
            messages = []
            for line in result.stdout.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return messages
        except Exception:
            return []

    def close(self) -> None:
        """Kill the tmux session."""
        if self._tmux_session:
            subprocess.run(
                ["tmux", "kill-session", "-t", self._tmux_session],
                capture_output=True,
            )
            logger.debug("Killed tmux session: %s", self._tmux_session)
            self._tmux_session = ""
        self._connected = False


# ─── SSH Backend ───────────────────────────────────────────────────────────────


@dataclass
class SSHAgentBackend(RemoteAgentBackend):
    """Remote agent backend using SSH.

    Executes the agent on a remote machine via SSH.
    Requires SSH key-based authentication configured.
    """

    _ssh_process: Any = field(default=None, init=False, repr=False)

    def __init__(self, config: RemoteBackendConfig):
        if config.backend_type != "ssh":
            raise ValueError(f"SSHAgentBackend requires backend_type='ssh', got '{config.backend_type}'")
        super().__init__(config)

    def _build_ssh_command(self) -> list[str]:
        """Build the SSH command arguments."""
        args = ["ssh"]
        if self._config.user:
            args.extend(["-l", self._config.user])
        if self._config.port:
            args.extend(["-p", str(self._config.port)])
        if self._config.key_file:
            args.extend(["-i", self._config.key_file])
        # Strict host key checking disabled for automation
        args.extend(["-o", "StrictHostKeyChecking=no"])
        args.append(self._config.host or "localhost")
        return args

    def _start_remote(self, context) -> None:
        """Start the agent via SSH."""
        python_path = self._config.python_path
        remote_cwd = self._config.remote_cwd or "~"
        cmd = f"cd {remote_cwd} && {python_path} -m py_claw.fork.child_main"

        ssh_cmd = self._build_ssh_command()
        ssh_cmd.append(cmd)

        self._ssh_process = subprocess.Popen(
            ssh_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._connected = True
        logger.debug("Started SSH agent on %s", self._config.host)

    def _send_command(self, cmd: dict[str, Any]) -> None:
        """Send a command over SSH."""
        if self._ssh_process is None or self._ssh_process.stdin is None:
            raise RuntimeError("SSH process not started")
        line = json.dumps(cmd) + "\n"
        self._ssh_process.stdin.write(line)
        self._ssh_process.stdin.flush()

    def _wait_for_result(self) -> dict[str, Any]:
        """Wait for result from SSH process."""
        if self._ssh_process is None or self._ssh_process.stdout is None:
            raise RuntimeError("SSH process not started")

        timeout = 120.0
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            line = self._ssh_process.stdout.readline()
            if not line:
                if self._ssh_process.poll() is not None:
                    raise RuntimeError("SSH process terminated unexpectedly")
                time.sleep(0.5)
                continue
            try:
                msg = json.loads(line)
                msg_type = msg.get("type")
                if msg_type == "output":
                    logger.debug("ssh agent output: %s", msg.get("delta", ""))
                elif msg_type == "result":
                    return msg
                elif msg_type == "error":
                    raise RuntimeError(f"SSH agent error: {msg.get('message', 'unknown')}")
            except json.JSONDecodeError:
                continue
        raise TimeoutError("SSH agent turn timed out")

    def close(self) -> None:
        """Close the SSH connection."""
        if self._ssh_process is not None:
            self._ssh_process.terminate()
            try:
                self._ssh_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._ssh_process.kill()
            self._ssh_process = None
        self._connected = False


# ─── Backend Factory ────────────────────────────────────────────────────────────


def create_remote_backend(config: RemoteBackendConfig) -> RemoteAgentBackend:
    """Create a remote backend based on configuration.

    Args:
        config: Remote backend configuration

    Returns:
        Appropriate backend instance (TmuxAgentBackend or SSHAgentBackend)

    Raises:
        ValueError: If backend_type is not supported
    """
    if config.backend_type == "tmux":
        return TmuxAgentBackend(config)
    elif config.backend_type == "ssh":
        return SSHAgentBackend(config)
    else:
        raise ValueError(
            f"Unsupported backend_type: '{config.backend_type}'. "
            "Supported types: 'tmux', 'ssh'"
        )
