"""
Assistant service types.

Based on ClaudeCode-main/src/assistant/sessionDiscovery.ts and sessionHistory.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from py_claw.messages.types import Message


# Constants
HISTORY_PAGE_SIZE = 100


@dataclass
class HistoryPage:
    """Page of history events.

    Attributes:
        events: Chronological order within the page
        first_id: Oldest event ID -> before_id cursor for next-older page
        has_more: True = older events exist
    """
    events: list[Message] = field(default_factory=list)
    first_id: str | None = None
    has_more: bool = False


@dataclass
class HistoryAuthCtx:
    """Authentication context for history API requests.

    Attributes:
        base_url: Base URL for the session events API
        headers: HTTP headers including auth
    """
    base_url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class SessionInfo:
    """Information about a discovered assistant session.

    Attributes:
        session_id: Unique session identifier
        created_at: When the session was created
        last_active: When the session was last active
        message_count: Number of messages in the session
        title: Optional session title (from first user message)
        is_remote: Whether this is a remote session
        remote_url: Remote URL if applicable
    """
    session_id: str
    created_at: datetime | None = None
    last_active: datetime | None = None
    message_count: int = 0
    title: str | None = None
    is_remote: bool = False
    remote_url: str | None = None


@dataclass
class AssistantModeConfig:
    """Configuration for assistant mode.

    Attributes:
        enabled: Whether assistant mode is enabled
        assistant_mode_flag: The CLAUDE_CODE_ASSISTANT_MODE env var value
    """
    enabled: bool = False
    assistant_mode_flag: str | None = None


__all__ = [
    "HISTORY_PAGE_SIZE",
    "HistoryPage",
    "HistoryAuthCtx",
    "SessionInfo",
    "AssistantModeConfig",
]
