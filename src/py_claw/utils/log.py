"""
Log utilities for error logging, session logs, and log file management.
"""
from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..schemas.common import SerializedMessage


# --- In-memory error log ---

MAX_IN_MEMORY_ERRORS = 100
_in_memory_error_log: deque[dict] = deque(maxlen=MAX_IN_MEMORY_ERRORS)


def _add_to_in_memory_error_log(error_info: dict) -> None:
    """Add error to the rolling in-memory error log."""
    _in_memory_error_log.append(error_info)


# --- Error log sink ---

SinkCallback = Callable[[str], None]


class ErrorLogSink:
    """Sink interface for the error logging backend."""

    def log_error(self, error: str) -> None:
        """Log an error."""
        raise NotImplementedError

    def log_mcp_error(self, server_name: str, error: str) -> None:
        """Log an MCP error."""
        raise NotImplementedError

    def log_mcp_debug(self, server_name: str, message: str) -> None:
        """Log an MCP debug message."""
        raise NotImplementedError

    def get_errors_path(self) -> str:
        """Get path to errors directory."""
        raise NotImplementedError

    def get_mcp_logs_path(self, server_name: str) -> str:
        """Get path to MCP logs for a specific server."""
        raise NotImplementedError


# Queued events before sink is attached
_error_queue: list[dict] = []


# Global sink
_error_log_sink: ErrorLogSink | None = None


def attach_error_log_sink(sink: ErrorLogSink) -> None:
    """
    Attach the error log sink. Queued events are drained immediately.

    Idempotent: if a sink is already attached, this is a no-op.
    """
    global _error_log_sink, _error_queue
    if _error_log_sink is not None:
        return
    _error_log_sink = sink

    if _error_queue:
        queued = list(_error_queue)
        _error_queue.clear()
        for event in queued:
            etype = event.get("type")
            if etype == "error":
                sink.log_error(event["error"])
            elif etype == "mcpError":
                sink.log_mcp_error(event["serverName"], event["error"])
            elif etype == "mcpDebug":
                sink.log_mcp_debug(event["serverName"], event["message"])


def _is_hard_fail_mode() -> bool:
    """Check if --hard-fail is set."""
    return "--hard-fail" in __import__("sys").argv


def log_error(error: BaseException | str) -> None:
    """
    Log an error to debug logs, in-memory log, and persistent error log (ants only).
    """
    import sys

    if _is_hard_fail_mode():
        err_str = str(error) if isinstance(error, Exception) else str(error)
        sys.stderr.write(f"[HARD FAIL] logError called with: {err_str}\n")
        sys.exit(1)

    try:
        # Check if error reporting should be disabled
        disabled = (
            os.environ.get("CLAUDE_CODE_USE_BEDROCK")
            or os.environ.get("CLAUDE_CODE_USE_VERTEX")
            or os.environ.get("CLAUDE_CODE_USE_FOUNDRY")
            or os.environ.get("DISABLE_ERROR_REPORTING")
            or os.environ.get("CLAUDE_CODE_PRIVACY_MODE")
        )
        if disabled:
            return

        err = error if isinstance(error, Exception) else Exception(str(error))
        error_str = getattr(err, "__traceback__", None) and str(err) or str(err)
        if not error_str and isinstance(error, Exception):
            error_str = str(error)

        error_info = {
            "error": error_str,
            "timestamp": datetime.now().isoformat(),
        }

        # Always add to in-memory log
        _add_to_in_memory_error_log(error_info)

        # If sink not attached, queue the event
        if _error_log_sink is None:
            _error_queue.append({"type": "error", "error": error_str})
            return

        _error_log_sink.log_error(error_str)
    except Exception:
        pass


def get_in_memory_errors() -> list[dict]:
    """Get the in-memory error log for the current session."""
    return list(_in_memory_error_log)


def log_mcp_error(server_name: str, error: BaseException | str) -> None:
    """Log an MCP error."""
    try:
        err_str = str(error) if isinstance(error, Exception) else str(error)
        if _error_log_sink is None:
            _error_queue.append({"type": "mcpError", "serverName": server_name, "error": err_str})
            return
        _error_log_sink.log_mcp_error(server_name, err_str)
    except Exception:
        pass


def log_mcp_debug(server_name: str, message: str) -> None:
    """Log an MCP debug message."""
    try:
        if _error_log_sink is None:
            _error_queue.append({"type": "mcpDebug", "serverName": server_name, "message": message})
            return
        _error_log_sink.log_mcp_debug(server_name, message)
    except Exception:
        pass


# --- File-based log loading ---

def date_to_filename(date: datetime) -> str:
    """Convert datetime to ISO filename format."""
    return date.isoformat().replace(":", "-").replace(".", "-")


async def load_error_logs_from_dir(path: str) -> list[dict]:
    """
    Load and parse log files from a directory.

    Returns list of log metadata dicts sorted by date.
    """
    import json

    from .json import json_parse

    p = Path(path)
    if not p.exists():
        return []

    logs: list[dict] = []
    try:
        entries = sorted(p.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    except OSError:
        return []

    for file_path in entries:
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            messages = json_parse(content)
            if not messages:
                continue
            first = messages[0] if messages else None
            last = messages[-1] if messages else None

            first_prompt = ""
            if (
                first
                and first.get("type") == "user"
                and isinstance(first.get("message", {}).get("content"), str)
            ):
                first_prompt = first["message"]["content"]

            stat = file_path.stat()
            log_date = date_to_filename(datetime.fromtimestamp(stat.st_mtime))

            logs.append(
                {
                    "date": log_date,
                    "fullPath": str(file_path),
                    "messages": messages,
                    "created": first.get("timestamp") if first else log_date,
                    "modified": last.get("timestamp") if last else log_date,
                    "firstPrompt": (first_prompt.split("\n")[0][:50] + "…" if len(first_prompt) > 50 else first_prompt) or "No prompt",
                    "messageCount": len(messages),
                    "isSidechain": "sidechain" in str(file_path),
                }
            )
        except Exception:
            continue

    # Sort by date descending
    logs.sort(key=lambda x: x.get("modified", ""), reverse=True)
    return logs


def _reset_error_log_for_testing() -> None:
    """Reset error log state for testing purposes only."""
    global _error_log_sink, _error_queue, _in_memory_error_log
    _error_log_sink = None
    _error_queue.clear()
    _in_memory_error_log.clear()
