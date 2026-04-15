"""Session runner for spawning child CLI processes.

Handles NDJSON stdout parsing, process lifecycle management,
and permission request forwarding.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)


# Maximum stderr lines to capture
MAX_STDERR_LINES = 10


@dataclass
class SessionActivity:
    """Activity event from a session."""

    timestamp: datetime
    type: str
    message: str


@dataclass
class SessionDoneStatus:
    """Status when a session completes."""

    exit_code: int | None
    error: str | None


@dataclass
class SessionHandle:
    """Handle for an active session process."""

    session_id: str
    process: subprocess.Popen
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PermissionRequest:
    """Permission request from child CLI."""

    type: str = "control_request"
    request_id: str = ""
    request: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionSpawnOpts:
    """Options for spawning a session."""

    exec_path: str
    script_args: list[str] | None = None
    env: dict[str, str] | None = None
    verbose: bool = False
    sandbox: bool = False
    debug_file: str | None = None
    permission_mode: str | None = None


@dataclass
class SessionSpawnerDeps:
    """Dependencies for SessionSpawner."""

    exec_path: str
    script_args: list[str] | None = None
    env: dict[str, str] | None = None
    verbose: bool = False
    sandbox: bool = False
    debug_file: str | None = None
    permission_mode: str | None = None
    on_debug: Callable[[str], None] = lambda msg: None
    on_activity: Callable[[str, SessionActivity], None] | None = None
    on_permission_request: Callable[
        [str, PermissionRequest, str], None
    ] | None = None


class NDJSONParser:
    """Parser for newline-delimited JSON streams."""

    def __init__(self):
        self._buffer = ""

    def parse(self, data: str) -> list[dict[str, Any]]:
        """Parse NDJSON data, yielding complete JSON objects."""
        self._buffer += data
        lines = self._buffer.split("\n")
        # Keep the last incomplete line in the buffer
        self._buffer = lines.pop() if lines[-1] else ""

        results = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Failed to parse NDJSON line: %s", line[:100])
        return results


class SessionSpawner:
    """Spawns and manages child CLI processes for bridge sessions.

    Handles:
    - Child process lifecycle
    - NDJSON stdout parsing
    - Permission request forwarding
    - Activity tracking
    """

    def __init__(self, deps: SessionSpawnerDeps):
        self._deps = deps
        self._sessions: dict[str, SessionHandle] = {}
        self._parsers: dict[str, NDJSONParser] = {}
        self._activity_buffers: dict[str, list[SessionActivity]] = {}
        self._stderr_buffers: dict[str, list[str]] = {}

    def spawn(self, session_id: str) -> SessionHandle:
        """Spawn a new child process for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            SessionHandle for the spawned process
        """
        if session_id in self._sessions:
            raise ValueError(f"Session already exists: {session_id}")

        # Build command
        cmd = self._build_command()

        # Prepare environment
        env = self._prepare_env()

        # Create parser and buffers
        self._parsers[session_id] = NDJSONParser()
        self._activity_buffers[session_id] = []
        self._stderr_buffers[session_id] = []

        # Spawn process
        self._deps.on_debug(f"Spawning session {session_id}: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
        )

        handle = SessionHandle(session_id=session_id, process=process)
        self._sessions[session_id] = handle

        # Start reading stdout asynchronously
        asyncio.create_task(self._read_stdout(session_id, process))

        # Start reading stderr asynchronously
        asyncio.create_task(self._read_stderr(session_id, process))

        self._emit_activity(
            session_id,
            SessionActivity(
                timestamp=datetime.utcnow(),
                type="spawned",
                message=f"Session {session_id} spawned with PID {process.pid}",
            ),
        )

        return handle

    def _build_command(self) -> list[str]:
        """Build the command to spawn."""
        cmd = [self._deps.exec_path]

        # Add script args if provided (for npm/node scenarios)
        if self._deps.script_args:
            cmd = [sys.executable] + self._deps.script_args + cmd

        # Add CLI flags
        cmd.extend(["--sdk-url", self._deps.exec_path])

        if self._deps.verbose:
            cmd.append("--verbose")

        if self._deps.sandbox:
            cmd.append("--sandbox")

        if self._deps.permission_mode:
            cmd.extend(["--permission-mode", self._deps.permission_mode])

        return cmd

    def _prepare_env(self) -> dict[str, str]:
        """Prepare environment variables for the child process."""
        env = dict(os.environ)
        if self._deps.env:
            env.update(self._deps.env)
        return env

    async def _read_stdout(self, session_id: str, process: subprocess.Popen) -> None:
        """Read and parse NDJSON from stdout."""
        parser = self._parsers.get(session_id)
        if not parser:
            return

        try:
            loop = asyncio.get_event_loop()
            while True:
                line = await loop.run_in_executor(None, process.stdout.readline)
                if not line:
                    break

                objects = parser.parse(line)
                for obj in objects:
                    await self._handle_message(session_id, obj)

        except Exception as e:
            logger.error("Error reading stdout for session %s: %s", session_id, e)

    async def _read_stderr(self, session_id: str, process: subprocess.Popen) -> None:
        """Capture stderr lines."""
        buffer = self._stderr_buffers.get(session_id, [])
        try:
            while True:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, process.stderr.readline
                )
                if not line:
                    break

                buffer.append(line.rstrip())
                # Keep only last MAX_STDERR_LINES
                while len(buffer) > MAX_STDERR_LINES:
                    buffer.pop(0)

        except Exception as e:
            logger.error("Error reading stderr for session %s: %s", session_id, e)

    async def _handle_message(
        self, session_id: str, obj: dict[str, Any]
    ) -> None:
        """Handle a parsed NDJSON message from the child process."""
        msg_type = obj.get("type")

        if msg_type == "control_request":
            # Permission request
            request = PermissionRequest(
                type="control_request",
                request_id=obj.get("request_id", ""),
                request=obj.get("request", {}),
            )
            if self._deps.on_permission_request:
                # Get access token from deps
                access_token = self._deps.env.get("ACCESS_TOKEN", "")
                self._deps.on_permission_request(session_id, request, access_token)

        elif msg_type == "activity":
            # Activity event
            activity = SessionActivity(
                timestamp=datetime.fromisoformat(
                    obj.get("timestamp", datetime.utcnow().isoformat())
                ),
                type=obj.get("activity_type", "unknown"),
                message=obj.get("message", ""),
            )
            self._emit_activity(session_id, activity)

        elif msg_type == "debug":
            # Debug message
            self._deps.on_debug(obj.get("message", ""))

        else:
            logger.debug("Unhandled message type %s: %s", msg_type, obj)

    def _emit_activity(self, session_id: str, activity: SessionActivity) -> None:
        """Emit an activity event."""
        activities = self._activity_buffers.get(session_id, [])
        activities.append(activity)
        # Keep only last MAX_ACTIVITIES
        while len(activities) > MAX_ACTIVITIES:
            activities.pop(0)

        if self._deps.on_activity:
            self._deps.on_activity(session_id, activity)

    def send_input(self, session_id: str, data: str) -> bool:
        """Send input to a session's stdin.

        Args:
            session_id: Session identifier
            data: Data to send (will be JSON serialized)

        Returns:
            True if sent successfully
        """
        handle = self._sessions.get(session_id)
        if not handle or handle.process.stdin is None:
            return False

        try:
            handle.process.stdin.write(data + "\n")
            handle.process.stdin.flush()
            return True
        except Exception as e:
            logger.error("Error sending input to session %s: %s", session_id, e)
            return False

    def terminate(self, session_id: str, timeout: float = 5.0) -> SessionDoneStatus:
        """Terminate a session gracefully.

        Args:
            session_id: Session identifier
            timeout: Seconds to wait for graceful termination

        Returns:
            SessionDoneStatus with exit info
        """
        handle = self._sessions.get(session_id)
        if not handle:
            return SessionDoneStatus(exit_code=None, error="Session not found")

        try:
            handle.process.terminate()
            handle.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            handle.process.kill()
            handle.process.wait()

        return self._collect_status(session_id)

    def kill(self, session_id: str) -> SessionDoneStatus:
        """Force kill a session.

        Args:
            session_id: Session identifier

        Returns:
            SessionDoneStatus with exit info
        """
        handle = self._sessions.get(session_id)
        if not handle:
            return SessionDoneStatus(exit_code=None, error="Session not found")

        handle.process.kill()
        handle.process.wait()

        return self._collect_status(session_id)

    def _collect_status(self, session_id: str) -> SessionDoneStatus:
        """Collect final status for a session."""
        handle = self._sessions.pop(session_id, None)
        self._parsers.pop(session_id, None)
        self._activity_buffers.pop(session_id, None)
        stderr = self._stderr_buffers.pop(session_id, [])

        if handle is None:
            return SessionDoneStatus(exit_code=None, error="Session not found")

        stderr_msg = "\n".join(stderr[-MAX_STDERR_LINES:]) if stderr else None
        return SessionDoneStatus(
            exit_code=handle.process.returncode,
            error=stderr_msg if handle.process.returncode != 0 else None,
        )

    def get_activity_log(self, session_id: str) -> list[SessionActivity]:
        """Get the activity log for a session."""
        return list(self._activity_buffers.get(session_id, []))

    def list_sessions(self) -> list[str]:
        """List active session IDs."""
        return list(self._sessions.keys())
