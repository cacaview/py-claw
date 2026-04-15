"""Debug logging utilities - mirrors ClaudeCode-main/src/utils/log.ts.

This module provides:
- Debug log level management (verbose, debug, info, warn, error)
- Debug mode detection from environment and CLI arguments
- Debug message filtering
- Debug log file writing with buffering
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    pass


class DebugLogLevel(Enum):
    """Debug log levels in order of severity."""

    VERBOSE = "verbose"
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


# Level order for filtering
LEVEL_ORDER: dict[DebugLogLevel, int] = {
    DebugLogLevel.VERBOSE: 0,
    DebugLogLevel.DEBUG: 1,
    DebugLogLevel.INFO: 2,
    DebugLogLevel.WARN: 3,
    DebugLogLevel.ERROR: 4,
}


# Runtime debug state
_runtime_debug_enabled = False


def _is_env_truthy(value: str | None) -> bool:
    """Check if environment variable is set to truthy value."""
    if not value:
        return False
    return value.lower() in ("1", "true", "yes")


def _get_debug_log_level_from_env() -> DebugLogLevel:
    """Get minimum debug log level from environment variable.

    Defaults to 'debug' which filters out 'verbose' messages.
    Set CLAUDE_CODE_DEBUG_LOG_LEVEL=verbose to include high-volume diagnostics.
    """
    raw = os.environ.get("CLAUDE_CODE_DEBUG_LOG_LEVEL", "").lower().strip()
    if raw in ("verbose", "debug", "info", "warn", "error"):
        return DebugLogLevel(raw)
    return DebugLogLevel.DEBUG


# Cached debug level
_debug_level_cache: DebugLogLevel | None = None


def get_min_debug_log_level() -> DebugLogLevel:
    """Get minimum log level to include in debug output.

    Defaults to 'debug', which filters out 'verbose' messages.
    Use CLAUDE_CODE_DEBUG_LOG_LEVEL=verbose to include verbose diagnostics.
    """
    global _debug_level_cache
    if _debug_level_cache is None:
        _debug_level_cache = _get_debug_log_level_from_env()
    return _debug_level_cache


def is_debug_mode() -> bool:
    """Check if debug mode is enabled.

    Debug mode is active if:
    - DEBUG or DEBUG_SDK environment variable is truthy
    - --debug or -d flag is passed
    - --debug-to-stderr is passed
    - --debug=pattern syntax is used
    - --debug-file is passed
    - User type is 'ant'
    """
    global _runtime_debug_enabled

    if _runtime_debug_enabled:
        return True

    if _is_env_truthy(os.environ.get("DEBUG")):
        return True

    if _is_env_truthy(os.environ.get("DEBUG_SDK")):
        return True

    if "--debug" in sys.argv or "-d" in sys.argv:
        return True

    if "--debug-to-stderr" in sys.argv or "-d2e" in sys.argv:
        return True

    if any(arg.startswith("--debug=") for arg in sys.argv):
        return True

    if _get_debug_file_path() is not None:
        return True

    return False


def enable_debug_logging() -> bool:
    """Enable debug logging mid-session (e.g., via /debug command).

    Non-ants don't write debug logs by default, so this lets them start
    capturing without restarting with --debug.

    Returns:
        True if logging was already active
    """
    global _runtime_debug_enabled, _debug_level_cache

    was_active = is_debug_mode() or os.environ.get("USER_TYPE") == "ant"
    _runtime_debug_enabled = True
    _debug_level_cache = None  # Clear cache
    return was_active


# Debug filter cache
_debug_filter_cache: str | None = None


def get_debug_filter() -> str | None:
    """Extract and parse debug filter from command line arguments.

    Looks for --debug=pattern in argv.

    Returns:
        Filter pattern if found, None otherwise
    """
    global _debug_filter_cache

    if _debug_filter_cache is not None:
        return _debug_filter_cache

    for arg in sys.argv:
        if arg.startswith("--debug="):
            _debug_filter_cache = arg[len("--debug=") :]
            return _debug_filter_cache

    return None


def is_debug_to_stderr() -> bool:
    """Check if debug output should go to stderr instead of file.

    Returns:
        True if --debug-to-stderr or -d2e flag is present
    """
    return "--debug-to-stderr" in sys.argv or "-d2e" in sys.argv


def _get_debug_file_path() -> str | None:
    """Get debug file path from command line arguments.

    Supports both --debug-file=path and --debug-file path syntax.

    Returns:
        File path if --debug-file flag is present, None otherwise
    """
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--debug-file="):
            return arg[len("--debug-file=") :]
        if arg == "--debug-file" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def get_debug_file_path() -> str | None:
    """Get explicit debug file path from CLI if specified.

    Returns:
        Custom debug file path or None
    """
    return _get_debug_file_path()


def should_log_debug_message(message: str) -> bool:
    """Determine if a debug message should be logged.

    Returns:
        True if the message should be logged
    """
    # Skip in test environment unless debug-to-stderr is set
    if os.environ.get("NODE_ENV") == "test" and not is_debug_to_stderr():
        return False

    # Non-ants only log when debug mode is active
    if os.environ.get("USER_TYPE") != "ant" and not is_debug_mode():
        return False

    # Filter by pattern if specified
    filter_pattern = get_debug_filter()
    if filter_pattern:
        return _matches_debug_filter(message, filter_pattern)

    return True


def _matches_debug_filter(message: str, pattern: str) -> bool:
    """Check if message matches debug filter pattern.

    Args:
        message: The debug message
        pattern: Filter pattern (simple substring or regex)

    Returns:
        True if message matches filter
    """
    try:
        # Try regex first
        return bool(re.search(pattern, message))
    except re.error:
        # Fall back to substring match
        return pattern in message


# Formatted output tracking
_has_formatted_output = False


def set_has_formatted_output(value: bool) -> None:
    """Set whether formatted output is active.

    Args:
        value: True if formatted output is active
    """
    global _has_formatted_output
    _has_formatted_output = value


def get_has_formatted_output() -> bool:
    """Check if formatted output is active.

    Returns:
        True if formatted output is active
    """
    return _has_formatted_output


# Debug writer state
_debug_writer: Callable[[str], None] | None = None
_pending_write: object = None


def _noop_write(content: str) -> None:
    """No-op write function."""
    pass


def _get_debug_writer() -> Callable[[str], None]:
    """Get or create the debug writer function.

    The writer handles:
    - Synchronous writes in debug mode (immediate)
    - Buffered writes when not in debug mode (flushes ~1/sec)
    """
    global _debug_writer

    if _debug_writer is None:
        debug_path = get_debug_log_path()
        debug_dir = os.path.dirname(debug_path) if debug_path else ""

        if is_debug_mode():
            # Immediate mode - synchronous writes
            def immediate_write(content: str) -> None:
                if debug_path:
                    os.makedirs(debug_dir, exist_ok=True)
                    with open(debug_path, "a", encoding="utf-8") as f:
                        f.write(content)

            _debug_writer = immediate_write
        else:
            # Buffered mode - queued writes
            buffer: list[str] = []
            last_flush = datetime.now()

            def buffered_write(content: str) -> None:
                nonlocal last_flush
                buffer.append(content)
                # Flush every second
                if (datetime.now() - last_flush).total_seconds() >= 1.0:
                    _flush_buffer(buffer, debug_path, debug_dir)
                    buffer.clear()
                    last_flush = datetime.now()

            _debug_writer = buffered_write

    return _debug_writer


def _flush_buffer(buffer: list[str], debug_path: str | None, debug_dir: str) -> None:
    """Flush buffered writes to disk.

    Args:
        buffer: List of content strings to write
        debug_path: Path to debug log file
        debug_dir: Directory containing debug log
    """
    if not debug_path or not buffer:
        return

    try:
        os.makedirs(debug_dir, exist_ok=True)
        with open(debug_path, "a", encoding="utf-8") as f:
            f.writelines(buffer)
    except OSError:
        # Silently fail if write fails
        pass


def flush_debug_logs() -> None:
    """Flush any pending debug log writes."""
    global _debug_writer
    if _debug_writer:
        # In a real implementation, would flush buffered writes here
        pass


def log_for_debugging(
    message: str,
    level: DebugLogLevel = DebugLogLevel.DEBUG,
) -> None:
    """Log a message for debugging purposes.

    Args:
        message: The message to log
        level: Log level (default: debug)
    """
    # Check minimum level
    if LEVEL_ORDER[level] < LEVEL_ORDER[get_min_debug_log_level()]:
        return

    # Check if should log
    if not should_log_debug_message(message):
        return

    # Multiline messages break jsonl format, so JSON-encode them
    if _has_formatted_output and "\n" in message:
        import json

        message = json.dumps(message)

    timestamp = datetime.now(timezone.utc).isoformat()
    output = f"{timestamp} [{level.value.upper()}] {message.strip()}\n"

    if is_debug_to_stderr():
        print(output, file=sys.stderr, end="")
        return

    writer = _get_debug_writer()
    writer(output)


def get_debug_log_path() -> str:
    """Get the debug log file path.

    Priority:
    1. --debug-file=path from CLI
    2. CLAUDE_CODE_DEBUG_LOGS_DIR environment variable
    3. ~/.claude/debug/{session_id}.txt

    Returns:
        Path to debug log file
    """
    # Check for explicit path
    explicit_path = get_debug_file_path()
    if explicit_path:
        return explicit_path

    # Check environment variable
    env_path = os.environ.get("CLAUDE_CODE_DEBUG_LOGS_DIR")
    if env_path:
        session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
        return os.path.join(env_path, f"{session_id}.txt")

    # Default path in config home
    config_home = os.environ.get("CLAUDE_CONFIG_HOME") or os.path.expanduser("~/.claude")
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
    return os.path.join(config_home, "debug", f"{session_id}.txt")


def log_ant_error(context: str, error: object) -> None:
    """Log errors for Ants only, always visible in production.

    Args:
        context: Description of where the error occurred
        error: The error to log
    """
    if os.environ.get("USER_TYPE") != "ant":
        return

    error_obj = error if isinstance(error, Exception) else Exception(str(error))
    if isinstance(error, Exception) and error.__traceback__:
        stack_trace = "".join(
            f"  {line}\n"
            for line in str(error_obj).split("\n")
        )
        log_for_debugging(
            f"[ANT-ONLY] {context} stack trace:\n{stack_trace}",
            level=DebugLogLevel.ERROR,
        )
