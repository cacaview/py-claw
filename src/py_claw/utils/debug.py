"""
Debug logging utilities.

Provides configurable debug output to file or stderr, with filtering by level
and pattern matching.
"""
from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import IO

# Global state
_runtime_debug_enabled = False
_has_formatted_output = False


def is_debug_mode() -> bool:
    """Check if debug mode is enabled via env vars or CLI flags."""
    if _runtime_debug_enabled:
        return True
    if os.environ.get("DEBUG") or os.environ.get("DEBUG_SDK"):
        return True
    if "--debug" in sys.argv or "-d" in sys.argv:
        return True
    if "--debug-to-stderr" in sys.argv or "-d2e" in sys.argv:
        return True
    if any(arg.startswith("--debug=") for arg in sys.argv):
        return True
    if get_debug_file_path() is not None:
        return True
    return False


def enable_debug_logging() -> bool:
    """
    Enable debug logging mid-session (e.g. via /debug).
    Returns True if logging was already active.
    """
    global _runtime_debug_enabled
    was_active = is_debug_mode() or os.environ.get("USER_TYPE") == "ant"
    _runtime_debug_enabled = True
    return was_active


def is_debug_to_stderr() -> bool:
    """Check if debug output should go to stderr."""
    return "--debug-to-stderr" in sys.argv or "-d2e" in sys.argv


@lru_cache(maxsize=1)
def get_debug_file_path() -> str | None:
    """Get debug file path from CLI args."""
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--debug-file="):
            return arg[len("--debug-file=") :]
        if arg == "--debug-file" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def set_has_formatted_output(value: bool) -> None:
    """Mark that formatted output (e.g. multiline) has been produced."""
    global _has_formatted_output
    _has_formatted_output = value


def get_has_formatted_output() -> bool:
    """Check if formatted output has been produced."""
    return _has_formatted_output


# --- Buffered writer for debug logs ---

_debug_writer_lock = threading.Lock()
_debug_buffer: list[str] = []
_debug_flush_thread: threading.Thread | None = None
_debug_flush_event = threading.Event()


class DebugLogWriter:
    """Thread-safe buffered debug log writer."""

    def __init__(
        self,
        *,
        flush_interval_ms: float = 1000,
        max_buffer_size: int = 100,
        immediate_mode: bool = False,
    ):
        self._path: str | None = None
        self._dir: str | None = None
        self._need_mkdir = False
        self._flush_interval_ms = flush_interval_ms
        self._max_buffer_size = max_buffer_size
        self._immediate_mode = immediate_mode
        self._buffer: list[str] = []
        self._pending_write: threading.Event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _get_path_and_dir(self) -> tuple[str, str]:
        path = (
            get_debug_file_path()
            or os.environ.get("CLAUDE_CODE_DEBUG_LOGS_DIR", "")
            or str(Path.home() / ".claude" / "debug" / f"{os.environ.get('CLAUDE_SESSION_ID', 'session')}.txt")
        )
        dir_path = str(Path(path).parent)
        return path, dir_path

    def write(self, content: str) -> None:
        """Write content to the debug log."""
        if self._immediate_mode:
            self._write_immediate(content)
        else:
            self._buffer.append(content)
            if len(self._buffer) >= self._max_buffer_size:
                self._flush()
            elif not self._flush_event.is_set():
                self._start_flush_thread()

    def _write_immediate(self, content: str) -> None:
        """Write synchronously (for --debug mode)."""
        path, dir_path = self._get_path_and_dir()
        if self._need_mkdir or self._dir != dir_path:
            self._dir = dir_path
            self._need_mkdir = True
            try:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        except OSError:
            pass

    def _flush(self) -> None:
        """Flush buffered content to disk."""
        if not self._buffer:
            return
        content = "".join(self._buffer)
        self._buffer.clear()
        path, dir_path = self._get_path_and_dir()
        try:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        except OSError:
            pass

    def _start_flush_thread(self) -> None:
        """Start background flush thread if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._flush_event.clear()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def _flush_loop(self) -> None:
        """Background flush loop."""
        while not self._stop_event.is_set():
            self._flush_event.wait(timeout=self._flush_interval_ms / 1000)
            if self._stop_event.is_set():
                break
            self._flush()

    def flush(self) -> None:
        """Synchronously flush and stop the flush thread."""
        self._stop_event.set()
        self._flush_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._flush()

    def dispose(self) -> None:
        """Stop and cleanup."""
        self.flush()


# Global writer instance
_debug_writer: DebugLogWriter | None = None


def _get_debug_writer() -> DebugLogWriter:
    """Get or create the global debug writer."""
    global _debug_writer
    if _debug_writer is None:
        _debug_writer = DebugLogWriter(
            immediate_mode=is_debug_mode(),
            flush_interval_ms=1000,
            max_buffer_size=100,
        )
    return _debug_writer


def get_debug_log_path() -> str:
    """Get the debug log file path."""
    return (
        get_debug_file_path()
        or os.environ.get("CLAUDE_CODE_DEBUG_LOGS_DIR", "")
        or str(Path.home() / ".claude" / "debug" / f"{os.environ.get('CLAUDE_SESSION_ID', 'session')}.txt")
    )


# --- Logging functions ---

DEBUG_LEVELS = ["verbose", "debug", "info", "warn", "error"]
_LEVEL_ORDER = {level: i for i, level in enumerate(DEBUG_LEVELS)}


@lru_cache(maxsize=1)
def get_min_debug_log_level() -> str:
    """Get the minimum log level from environment variable."""
    raw = os.environ.get("CLAUDE_CODE_DEBUG_LOG_LEVEL", "").lower().strip()
    if raw in _LEVEL_ORDER:
        return raw
    return "debug"


def log_for_debugging(
    message: str,
    *,
    level: str = "debug",
) -> None:
    """
    Log a debug message if conditions are met.

    Filters by level and debug filter pattern.
    """
    if _LEVEL_ORDER.get(level, 99) < _LEVEL_ORDER.get(get_min_debug_log_level(), 1):
        return

    if not _should_log_debug_message(message):
        return

    # Multiline messages break jsonl output format
    if _has_formatted_output and "\n" in message:
        import json

        message = json.dumps(message)

    timestamp = datetime.now().isoformat()
    output = f"{timestamp} [{level.upper()}] {message.strip()}\n"

    if is_debug_to_stderr():
        sys.stderr.write(output)
        sys.stderr.flush()
        return

    _get_debug_writer().write(output)


def _should_log_debug_message(message: str) -> bool:
    """Check if this message should be logged based on debug mode and environment."""
    # Skip in test mode unless --debug-to-stderr
    if os.environ.get("NODE_ENV") == "test" and not is_debug_to_stderr():
        return False

    # Non-ants only write debug logs when debug mode is active
    if os.environ.get("USER_TYPE") != "ant" and not is_debug_mode():
        return False

    # Check debug filter
    debug_arg = next((a for a in sys.argv if a.startswith("--debug=")), None)
    if debug_arg:
        pattern = debug_arg[len("--debug=") :]
        if pattern and not _matches_debug_filter(message, pattern):
            return False

    return True


def _matches_debug_filter(message: str, pattern: str) -> bool:
    """Simple substring match for debug filter pattern."""
    return pattern.lower() in message.lower()


async def flush_debug_logs() -> None:
    """Flush pending debug log writes."""
    global _debug_writer
    if _debug_writer is not None:
        _debug_writer.flush()


def log_ant_error(context: str, error: BaseException) -> None:
    """
    Log errors for Ants only, always visible in production.
    """
    if os.environ.get("USER_TYPE") != "ant":
        return

    if hasattr(error, "__traceback__") and error.__traceback__:
        import traceback

        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        log_for_debugging(f"[ANT-ONLY] {context} stack trace:\n{tb}", level="error")
    else:
        log_for_debugging(f"[ANT-ONLY] {context}: {error}", level="error")
