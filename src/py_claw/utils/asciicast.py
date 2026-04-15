"""
Asciicast terminal recording utility.

Records terminal sessions in asciicast format (.cast) for sharing.
Captures terminal output with timestamps and handles resize events.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Recording state - filePath is updated when session ID changes (e.g., --resume)
@dataclass
class RecordingState:
    """Mutable recording state."""
    file_path: str | None = None
    timestamp: int = 0

_recording_state = RecordingState()


def _get_env_truthy(key: str) -> bool:
    """Check if an environment variable is set to a truthy value."""
    return os.environ.get(key, "").lower() in ("1", "true", "yes")


def _get_claude_config_home_dir() -> str:
    """Get Claude config home directory."""
    if os.name == "nt":
        return os.environ.get("LOCALAPPDATA", str(Path.home())) + "/claude"
    return os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")) + "/claude"


def _sanitize_path(path: str) -> str:
    """Sanitize a path for use in file paths."""
    # Replace problematic characters with underscores
    import re
    return re.sub(r"[^\w\-.]", "_", path)


def _get_original_cwd() -> str:
    """Get original working directory from bootstrap state."""
    try:
        from py_claw.bootstrap import get_original_cwd
        return get_original_cwd()
    except (ImportError, Exception):
        return os.getcwd()


def _get_session_id() -> str:
    """Get current session ID."""
    try:
        from py_claw.bootstrap import get_session_id
        return get_session_id()
    except (ImportError, Exception):
        import uuid
        return str(uuid.uuid4())


def _is_ant_user() -> bool:
    """Check if running as ant user."""
    return os.environ.get("USER_TYPE") == "ant"


def get_record_file_path() -> str | None:
    """
    Get the asciicast recording file path.

    For ants with CLAUDE_CODE_TERMINAL_RECORDING=1: returns a path.
    Otherwise: returns None.
    The path is computed once and cached in recordingState.
    """
    if _recording_state.file_path is not None:
        return _recording_state.file_path

    if not _is_ant_user():
        return None

    if not _get_env_truthy("CLAUDE_CODE_TERMINAL_RECORDING"):
        return None

    # Record alongside the transcript.
    # Each launch gets its own file so --continue produces multiple recordings.
    projects_dir = os.path.join(_get_claude_config_home_dir(), "projects")
    project_dir = os.path.join(projects_dir, _sanitize_path(_get_original_cwd()))
    _recording_state.timestamp = int(time.time() * 1000)
    _recording_state.file_path = os.path.join(
        project_dir,
        f"{_get_session_id()}-{_recording_state.timestamp}.cast",
    )
    return _recording_state.file_path


def _reset_recording_state_for_testing() -> None:
    """Reset recording state for testing purposes."""
    _recording_state.file_path = None
    _recording_state.timestamp = 0


def get_session_recording_paths() -> list[str]:
    """
    Find all .cast files for the current session.
    Returns paths sorted by filename (chronological by timestamp suffix).
    """
    session_id = _get_session_id()
    projects_dir = os.path.join(_get_claude_config_home_dir(), "projects")
    project_dir = os.path.join(projects_dir, _sanitize_path(_get_original_cwd()))

    try:
        entries = os.listdir(project_dir)
        files = [
            os.path.join(project_dir, f)
            for f in entries
            if f.startswith(session_id) and f.endswith(".cast")
        ]
        files.sort()
        return files
    except OSError:
        return []


async def _rename_recording_for_session() -> None:
    """
    Rename the recording file to match the current session ID.
    Called after --resume/--continue changes the session ID via switchSession().
    """
    old_path = _recording_state.file_path
    if not old_path or _recording_state.timestamp == 0:
        return

    projects_dir = os.path.join(_get_claude_config_home_dir(), "projects")
    project_dir = os.path.join(projects_dir, _sanitize_path(_get_original_cwd()))
    new_path = os.path.join(
        project_dir,
        f"{_get_session_id()}-{_recording_state.timestamp}.cast",
    )

    if old_path == new_path:
        return

    # Flush pending writes before renaming
    await _flush_recorder()

    old_name = os.path.basename(old_path)
    new_name = os.path.basename(new_path)

    try:
        os.rename(old_path, new_path)
        _recording_state.file_path = new_path
    except OSError:
        pass


class BufferedWriter:
    """Buffered writer for asciicast recording."""

    def __init__(
        self,
        write_fn: Callable[[str], None],
        flush_interval_ms: int = 500,
        max_buffer_size: int = 50,
        max_buffer_bytes: int = 10 * 1024 * 1024,
    ):
        self._write_fn = write_fn
        self._flush_interval_ms = flush_interval_ms
        self._max_buffer_size = max_buffer_size
        self._max_buffer_bytes = max_buffer_bytes
        self._buffer: list[str] = []
        self._buffer_bytes: int = 0
        self._lock = threading.Lock()
        self._flush_task: asyncio.Task | None = None
        self._disposed = False

    def write(self, content: str) -> None:
        """Add content to the write buffer."""
        with self._lock:
            self._buffer.append(content)
            self._buffer_bytes += len(content.encode("utf-8"))

            # Flush if buffer is full
            if (
                len(self._buffer) >= self._max_buffer_size
                or self._buffer_bytes >= self._max_buffer_bytes
            ):
                self._do_flush()

    def _do_flush(self) -> None:
        """Flush the buffer to the write function."""
        if not self._buffer:
            return
        content = "".join(self._buffer)
        self._buffer.clear()
        self._buffer_bytes = 0
        try:
            self._write_fn(content)
        except Exception:
            pass

    def flush(self) -> None:
        """Flush the buffer."""
        with self._lock:
            self._do_flush()

    def dispose(self) -> None:
        """Dispose of the writer."""
        self.flush()
        self._disposed = True


@dataclass
class AsciicastRecorder:
    """Recorder interface."""
    flush_fn: Callable[[], None]
    dispose_fn: Callable[[], None]


_recorder: AsciicastRecorder | None = None


def _get_terminal_size() -> tuple[int, int]:
    """Get terminal size (cols, rows)."""
    try:
        cols = os.get_terminal_size().columns or 80
        rows = os.get_terminal_size().lines or 24
    except OSError:
        cols, rows = 80, 24
    return cols, rows


def _json_stringify(obj: object) -> str:
    """JSON stringify with no whitespace."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


async def flush_asciicast_recorder() -> None:
    """Flush pending recording data to disk."""
    if _recorder:
        _recorder.flush_fn()


def install_asciicast_recorder() -> None:
    """
    Install the asciicast recorder.
    Wraps process.stdout.write to capture all terminal output with timestamps.
    Must be called before any UI mounts.
    """
    global _recorder

    file_path = get_record_file_path()
    if not file_path:
        return

    cols, rows = _get_terminal_size()
    start_time = time.perf_counter()

    # Write the asciicast v2 header
    header = _json_stringify({
        "version": 2,
        "width": cols,
        "height": rows,
        "timestamp": int(time.time()),
        "env": {
            "SHELL": os.environ.get("SHELL", ""),
            "TERM": os.environ.get("TERM", ""),
        },
    })

    # Ensure directory exists
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    except OSError:
        pass

    # Write header
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(header + "\n")
        os.chmod(file_path, 0o600)
    except OSError:
        return

    pending_write: asyncio.Future | None = None
    writer = BufferedWriter(
        write_fn=lambda content: _async_append_file(file_path, content),
        flush_interval_ms=500,
        max_buffer_size=50,
        max_buffer_bytes=10 * 1024 * 1024,
    )

    original_stdout_write = None

    def _async_append_file(path: str, content: str) -> None:
        """Append content to file asynchronously."""
        nonlocal pending_write
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def _write():
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)
            except OSError:
                pass

        future = loop.create_task(_write())
        pending_write = future

    # Store for cleanup
    resize_handler = None

    def on_resize() -> None:
        """Handle terminal resize events."""
        nonlocal resize_handler
        elapsed = (time.perf_counter() - start_time) / 1000
        cols, rows = _get_terminal_size()
        writer.write(_json_stringify([elapsed, "r", f"{cols}x{rows}"]) + "\n")

    try:
        import sys
        # Handle resize
        if hasattr(sys.stdout, "fileno") and sys.stdout.isatty():
            pass  # resize detection not easily available in Python

        _recorder = AsciicastRecorder(
            flush_fn=lambda: writer.flush(),
            dispose_fn=lambda: writer.dispose(),
        )

    except Exception:
        return


def _uninstall_asciicast_recorder() -> None:
    """Uninstall the asciicast recorder."""
    global _recorder
    if _recorder:
        _recorder.dispose_fn()
        _recorder = None
