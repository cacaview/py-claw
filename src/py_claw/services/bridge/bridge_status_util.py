"""Bridge status display utilities.

Provides status formatting, URL building, and shimmer animation
helpers for bridge UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# How long a tool activity line stays visible after last tool_start (ms)
TOOL_DISPLAY_EXPIRY_MS = 30_000

# Interval for shimmer animation tick (ms)
SHIMMER_INTERVAL_MS = 150


# Status state machine states
StatusState = Literal["idle", "attached", "titled", "reconnecting", "failed"]


def timestamp() -> str:
    """Get current timestamp string (HH:MM:SS).

    Returns:
        Formatted time string.
    """
    now = datetime.now()
    return f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"


def format_duration(ms: float) -> str:
    """Format milliseconds as human-readable duration.

    Args:
        ms: Duration in milliseconds.

    Returns:
        Formatted string like "5m 30s" or "30s".
    """
    if ms < 60_000:
        return f"{round(ms / 1000)}s"
    minutes = int(ms / 60_000)
    seconds = round((ms % 60_000) / 1000)
    if seconds > 0:
        return f"{minutes}m {seconds}s"
    return f"{minutes}m"


def truncate_to_width(s: str, width: int) -> str:
    """Truncate string to a maximum width.

    Args:
        s: String to truncate.
        width: Maximum width.

    Returns:
        Truncated string with ellipsis if needed.
    """
    # Simple grapheme-aware truncation
    chars = list(s)
    if len(chars) <= width:
        return s
    return "".join(chars[: width - 1]) + "\u2026"


def abbreviate_activity(summary: str) -> str:
    """Abbreviate a tool activity summary for trail display.

    Args:
        summary: Activity summary text.

    Returns:
        Truncated to 30 chars.
    """
    return truncate_to_width(summary, 30)


def build_bridge_connect_url(
    environment_id: str,
    ingress_url: str | None = None,
) -> str:
    """Build the connect URL shown when bridge is idle.

    Args:
        environment_id: The environment ID.
        ingress_url: Optional ingress URL override.

    Returns:
        Connect URL for the bridge.
    """
    if ingress_url:
        base = ingress_url.rstrip("/")
    else:
        base = "https://claude.ai"
    return f"{base}/code?bridge={environment_id}"


def build_bridge_session_url(
    session_id: str,
    environment_id: str,
    ingress_url: str | None = None,
) -> str:
    """Build the session URL shown when session is attached.

    Args:
        session_id: The session ID.
        environment_id: The environment ID.
        ingress_url: Optional ingress URL override.

    Returns:
        Session URL with bridge query param.
    """
    # Translate cse_ to session_ prefix if needed
    if session_id.startswith("cse_"):
        session_id = "session_" + session_id[4:]

    if ingress_url:
        base = ingress_url.rstrip("/")
    else:
        base = "https://claude.ai/code"

    return f"{base}/sessions/{session_id}?bridge={environment_id}"


def compute_glimmer_index(tick: int, message_width: int) -> int:
    """Compute the glimmer index for a reverse-sweep shimmer animation.

    Args:
        tick: Animation tick number.
        message_width: Width of the message in characters.

    Returns:
        Glimmer column index.
    """
    cycle_length = message_width + 20
    return message_width + 10 - (tick % cycle_length)


@dataclass
class BridgeStatusInfo:
    """Computed bridge status label and color."""

    label: Literal[
        "Remote Control failed",
        "Remote Control reconnecting",
        "Remote Control active",
        "Remote Control connecting\u2026",
    ]
    color: Literal["error", "warning", "success"]


def get_bridge_status(
    error: str | None = None,
    connected: bool = False,
    session_active: bool = False,
    reconnecting: bool = False,
) -> BridgeStatusInfo:
    """Derive a status label and color from bridge connection state.

    Args:
        error: Error message if any.
        connected: Whether transport is connected.
        session_active: Whether session is active.
        reconnecting: Whether reconnecting.

    Returns:
        BridgeStatusInfo with label and color.
    """
    if error:
        return BridgeStatusInfo(
            label="Remote Control failed",
            color="error",
        )
    if reconnecting:
        return BridgeStatusInfo(
            label="Remote Control reconnecting",
            color="warning",
        )
    if session_active or connected:
        return BridgeStatusInfo(
            label="Remote Control active",
            color="success",
        )
    return BridgeStatusInfo(
        label="Remote Control connecting\u2026",
        color="warning",
    )


def build_idle_footer_text(url: str) -> str:
    """Footer text shown when bridge is idle.

    Args:
        url: Connect URL.

    Returns:
        Footer message.
    """
    return f"Code everywhere with the Claude app or {url}"


def build_active_footer_text(url: str) -> str:
    """Footer text shown when a session is active.

    Args:
        url: Session URL.

    Returns:
        Footer message.
    """
    return f"Continue coding in the Claude app or {url}"


FAILED_FOOTER_TEXT = "Something went wrong, please try again"


def wrap_with_osc8_link(text: str, url: str) -> str:
    """Wrap text in an OSC 8 terminal hyperlink.

    Args:
        text: Visible text.
        url: Link URL.

    Returns:
        Text with OSC 8 hyperlink escape codes.
    """
    return f"\x1b]8;;{url}\x07{text}\x1b]8;;\x07"
