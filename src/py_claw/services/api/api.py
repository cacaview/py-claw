"""Error logging utilities - mirrors ClaudeCode-main/src/utils/api.ts.

This module provides:
- Log display title extraction with fallback logic
- Error logging to multiple destinations (debug logs, in-memory, persistent file)
- MCP error and debug logging
- API request capture for bug reports
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    pass


# Constants
MAX_IN_MEMORY_ERRORS = 100
TICK_TAG = "tick"


@dataclass(slots=True)
class ErrorInfo:
    """Error information stored in memory."""

    error: str
    timestamp: str


# In-memory error log for recent errors
_in_memory_error_log: list[ErrorInfo] = []

# Queued events for events logged before sink is attached
_queue: list[dict] = []

# Sink reference
_error_log_sink: "ErrorLogSink | None" = None


class ErrorLogSink:
    """Sink interface for the error logging backend."""

    log_error: Callable[[Exception], None]
    log_mcp_error: Callable[[str, object], None]
    log_mcp_debug: Callable[[str, str], None]
    get_errors_path: Callable[[], str]
    get_mcp_logs_path: Callable[[str], str]

    def __init__(
        self,
        log_error: Callable[[Exception], None],
        log_mcp_error: Callable[[str, object], None],
        log_mcp_debug: Callable[[str, str], None],
        get_errors_path: Callable[[], str],
        get_mcp_logs_path: Callable[[str], str],
    ) -> None:
        self.log_error = log_error
        self.log_mcp_error = log_mcp_error
        self.log_mcp_debug = log_mcp_debug
        self.get_errors_path = get_errors_path
        self.get_mcp_logs_path = get_mcp_logs_path


def _add_to_in_memory_error_log(error_info: ErrorInfo) -> None:
    """Add error to in-memory log with bounded size."""
    if len(_in_memory_error_log) >= MAX_IN_MEMORY_ERRORS:
        _in_memory_error_log.pop(0)  # Remove oldest
    _in_memory_error_log.append(error_info)


def attach_error_log_sink(new_sink: ErrorLogSink) -> None:
    """Attach the error log sink that will receive all error events.

    Queued events are drained immediately to ensure no errors are lost.
    Idempotent: if a sink is already attached, this is a no-op.
    """
    global _error_log_sink

    if _error_log_sink is not None:
        return

    _error_log_sink = new_sink

    # Drain the queue immediately
    if len(_queue) > 0:
        queued_events = _queue.copy()
        _queue.clear()

        for event in queued_events:
            event_type = event.get("type")
            if event_type == "error":
                _error_log_sink.log_error(event["error"])
            elif event_type == "mcpError":
                _error_log_sink.log_mcp_error(event["serverName"], event["error"])
            elif event_type == "mcpDebug":
                _error_log_sink.log_mcp_debug(event["serverName"], event["message"])


def _is_hard_fail_mode() -> bool:
    """Check if --hard-fail flag is present."""
    return "--hard-fail" in sys.argv


def _to_error(error: object) -> Exception:
    """Convert unknown error to Exception."""
    if isinstance(error, Exception):
        return error
    return Exception(str(error))


def _is_env_truthy(value: str | None) -> bool:
    """Check if environment variable is set to a truthy value."""
    if not value:
        return False
    return value.lower() in ("1", "true", "yes")


def _is_essential_traffic_only() -> bool:
    """Check if traffic is marked as essential/privacy-sensitive."""
    # Placeholder - would integrate with privacy settings
    return False


def log_error(error: object) -> None:
    """Log an error to multiple destinations for debugging and monitoring.

    This function logs errors to:
    - Debug logs (visible via `claude --debug`)
    - In-memory error log (accessible via `get_in_memory_errors()`)
    - Persistent error log file (only for internal 'ant' users)

    Args:
        error: The error to log (Exception, string, or any error-like object)
    """
    global _error_log_sink

    err = _to_error(error)

    # HARD FAIL mode check
    if _is_hard_fail_mode():
        print(f"[HARD FAIL] logError called with: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        # Check if error reporting should be disabled
        disable_reasons = [
            _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_BEDROCK")),
            _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_VERTEX")),
            _is_env_truthy(os.environ.get("CLAUDE_CODE_USE_FOUNDRY")),
            _is_env_truthy(os.environ.get("DISABLE_ERROR_REPORTING")),
            _is_essential_traffic_only(),
        ]

        if any(disable_reasons):
            return

        error_str = getattr(err, "stack", None) or str(err)

        error_info = ErrorInfo(
            error=error_str,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Always add to in-memory log
        _add_to_in_memory_error_log(error_info)

        # If sink not attached, queue the event
        if _error_log_sink is None:
            _queue.append({"type": "error", "error": err})
            return

        _error_log_sink.log_error(err)
    except Exception:
        # Silently fail to avoid recursion
        pass


def get_in_memory_errors() -> list[ErrorInfo]:
    """Get the in-memory error log.

    Returns:
        Copy of in-memory errors list
    """
    return list(_in_memory_error_log)


def date_to_filename(date: datetime) -> str:
    """Convert datetime to filename-safe string.

    Args:
        date: The datetime to convert

    Returns:
        ISO format string with colons and dots replaced
    """
    return date.isoformat().replace(":", "-").replace(".", "-")


# Type for log option (simplified from TypeScript)
@dataclass(slots=True)
class LogOption:
    """Represents a log entry for display."""

    date: str
    full_path: str | None = None
    messages: list[object] | None = None
    value: int = 0
    created: datetime | None = None
    modified: datetime | None = None
    first_prompt: str | None = None
    message_count: int = 0
    is_sidechain: bool = False
    agent_name: str | None = None
    custom_title: str | None = None
    summary: str | None = None
    session_id: str | None = None


async def load_error_logs() -> list[LogOption]:
    """Load the list of error logs.

    Returns:
        List of error logs sorted by date
    """
    # Placeholder - actual implementation would read from cache paths
    return []


async def get_error_log_by_index(index: int) -> LogOption | None:
    """Get an error log by its index.

    Args:
        index: Index in the sorted list of logs (0-based)

    Returns:
        Log data or None if not found
    """
    logs = await load_error_logs()
    if 0 <= index < len(logs):
        return logs[index]
    return None


def get_log_display_title(
    log: LogOption,
    default_title: str | None = None,
) -> str:
    """Get the display title for a log/session with fallback logic.

    Skips firstPrompt if it starts with a tick/goal tag (autonomous mode).
    Strips display-unfriendly tags from the result.
    Falls back to truncated session ID when no other title is available.

    Args:
        log: The log option to extract title from
        default_title: Fallback title if no other is available

    Returns:
        Display-friendly title string
    """
    # Skip firstPrompt if it's a tick/goal message (autonomous mode)
    first_prompt = getattr(log, "first_prompt", None) or ""
    is_autonomous = first_prompt.startswith(f"<{TICK_TAG}>")

    # Strip display-unfriendly tags for cleaner titles
    stripped_first_prompt = _strip_display_tags(first_prompt)
    use_first_prompt = stripped_first_prompt and not is_autonomous

    title = (
        getattr(log, "agent_name", None)
        or getattr(log, "custom_title", None)
        or getattr(log, "summary", None)
        or (stripped_first_prompt if use_first_prompt else None)
        or default_title
        or ("Autonomous session" if is_autonomous else None)
        or (getattr(log, "session_id", None)[:8] if getattr(log, "session_id", None) else "")
    )

    # Strip display tags from final title
    return _strip_display_tags(title).strip()


def _strip_display_tags(text: str) -> str:
    """Strip display-unfriendly tags from text.

    Removes tags like <ide_opened_file>, <command-name>, etc.
    """
    if not text:
        return ""

    # Simple tag stripping - remove content within <>
    import re

    # Remove complete tag patterns
    result = re.sub(r"<(?!/?\w)[^>]*>", "", text)  # Remove invalid tags
    result = re.sub(r"<(/?\w+)[^>]*>", "", result)  # Remove valid tags
    return result.strip()


def log_mcp_error(server_name: str, error: object) -> None:
    """Log an MCP server error.

    Args:
        server_name: Name of the MCP server
        error: The error to log
    """
    global _error_log_sink

    try:
        if _error_log_sink is None:
            _queue.append({"type": "mcpError", "serverName": server_name, "error": error})
            return

        _error_log_sink.log_mcp_error(server_name, error)
    except Exception:
        # Silently fail
        pass


def log_mcp_debug(server_name: str, message: str) -> None:
    """Log an MCP debug message.

    Args:
        server_name: Name of the MCP server
        message: Debug message to log
    """
    global _error_log_sink

    try:
        if _error_log_sink is None:
            _queue.append({"type": "mcpDebug", "serverName": server_name, "message": message})
            return

        _error_log_sink.log_mcp_debug(server_name, message)
    except Exception:
        # Silently fail
        pass


def capture_api_request(
    params: dict,
    query_source: str | None = None,
) -> None:
    """Capture the last API request for inclusion in bug reports.

    Stores params WITHOUT messages to avoid retaining the entire conversation.

    Args:
        params: The API request parameters
        query_source: Source of the query (e.g., 'repl_main_thread')
    """
    # Only capture from repl_main_thread variants
    if query_source and not query_source.startswith("repl_main_thread"):
        return

    # Store params without messages
    # Note: In Python implementation, this would integrate with bootstrap state
    # For now, this is a placeholder that mirrors TypeScript behavior
    pass


def reset_error_log_for_testing() -> None:
    """Reset error log state for testing purposes.

    This is for internal testing only.
    """
    global _error_log_sink, _queue

    _error_log_sink = None
    _queue.clear()
    _in_memory_error_log.clear()
