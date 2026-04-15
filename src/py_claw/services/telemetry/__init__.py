"""Telemetry and event logging utilities."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

# Monotonically increasing counter for ordering events within a session
_event_sequence: int = 0

# Track whether we've warned about no event logger
_has_warned_no_event_logger: bool = False

# Event logger interface (stub - would connect to OpenTelemetry in full impl)
_event_logger: Any = None


def set_event_logger(logger: Any) -> None:
    """Set the event logger instance."""
    global _event_logger, _has_warned_no_event_logger
    _event_logger = logger
    _has_warned_no_event_logger = False


def get_event_logger() -> Any:
    """Get the current event logger instance."""
    return _event_logger


def is_user_prompt_logging_enabled() -> bool:
    """Check if user prompt logging is enabled via OTEL_LOG_USER_PROMPTS."""
    return os.environ.get("OTEL_LOG_USER_PROMPTS", "").lower() in ("true", "1", "yes")


def redact_if_disabled(content: str) -> str:
    """Redact content if user prompt logging is disabled."""
    return content if is_user_prompt_logging_enabled() else "<REDACTED>"


@dataclass
class TelemetryEvent:
    """Represents a telemetry event."""

    name: str
    timestamp: str
    attributes: dict[str, Any] = field(default_factory=dict)


async def log_otel_event(event_name: str, metadata: dict[str, str | None] | None = None) -> None:
    """
    Log an OpenTelemetry event.

    Args:
        event_name: Name of the event
        metadata: Optional metadata dictionary
    """
    global _event_sequence, _has_warned_no_event_logger

    event_logger = get_event_logger()
    if not event_logger:
        if not _has_warned_no_event_logger:
            _has_warned_no_event_logger = True
            _log_for_debugging(
                f"[3P telemetry] Event dropped (no event logger initialized): {event_name}"
            )
        return

    # Skip logging in test environment
    if os.environ.get("NODE_ENV") == "test":
        return

    attributes: dict[str, Any] = {
        "event.name": event_name,
        "event.timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "event.sequence": _event_sequence,
    }

    # Add prompt ID to events
    prompt_id = os.environ.get("CLAUDE_CODE_PROMPT_ID")
    if prompt_id:
        attributes["prompt.id"] = prompt_id

    # Workspace directory from desktop app
    workspace_dir = os.environ.get("CLAUDE_CODE_WORKSPACE_HOST_PATHS")
    if workspace_dir:
        attributes["workspace.host_paths"] = workspace_dir.split("|")

    # Add metadata as attributes
    if metadata:
        for key, value in metadata.items():
            if value is not None:
                attributes[key] = value

    # Emit the event
    try:
        await event_logger.emit({
            "body": f"claude_code.{event_name}",
            "attributes": attributes,
        })
    except Exception as e:
        _log_for_debugging(f"[3P telemetry] Failed to emit event: {e}")


def _log_for_debugging(message: str) -> None:
    """Log message for debugging."""
    import sys

    print(f"[DEBUG] {message}", file=sys.stderr)


def get_telemetry_attributes() -> dict[str, Any]:
    """
    Get common telemetry attributes.

    Returns a dict with standard attributes for telemetry events.
    """
    attributes: dict[str, Any] = {}

    # Add session ID
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session_id:
        attributes["session.id"] = session_id

    # Add workspace info
    workspace_dir = os.environ.get("CLAUDE_CODE_WORKSPACE_HOST_PATHS")
    if workspace_dir:
        attributes["workspace.host_paths"] = workspace_dir.split("|")

    # Add API provider
    from .model import get_api_provider

    attributes["api.provider"] = get_api_provider().value

    return attributes


async def log_event(event_name: str, metadata: dict[str, Any] | None = None) -> None:
    """
    Log an analytics event.

    This is a convenience wrapper around log_otel_event that formats
    the event name properly.

    Args:
        event_name: Name of the event (e.g., 'tengu_compact')
        metadata: Optional metadata dictionary
    """
    # Prefix with claude_code if not already
    if not event_name.startswith("claude_code."):
        event_name = f"claude_code.{event_name}"

    await log_otel_event(event_name, metadata)
