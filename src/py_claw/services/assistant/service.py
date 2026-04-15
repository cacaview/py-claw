"""
Assistant service.

Session discovery and assistant mode management.

Based on ClaudeCode-main/src/assistant/sessionDiscovery.ts and index.ts
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .session_history import (
    create_history_auth_ctx,
    fetch_latest_events,
    fetch_older_events,
)
from .types import AssistantModeConfig, HistoryAuthCtx, HistoryPage, SessionInfo


def is_assistant_mode_enabled() -> bool:
    """
    Check if assistant mode is enabled via environment variable.

    Returns:
        True if CLAUDE_CODE_ASSISTANT_MODE is '1' or 'true'
    """
    env_value = os.environ.get("CLAUDE_CODE_ASSISTANT_MODE", "")
    return env_value in ("1", "true")


def get_assistant_mode_config() -> AssistantModeConfig:
    """
    Get assistant mode configuration.

    Returns:
        AssistantModeConfig with current settings
    """
    env_value = os.environ.get("CLAUDE_CODE_ASSISTANT_MODE")
    return AssistantModeConfig(
        enabled=is_assistant_mode_enabled(),
        assistant_mode_flag=env_value,
    )


async def discover_assistant_sessions(
    access_token: str | None = None,
    org_uuid: str | None = None,
    base_api_url: str = "https://api.anthropic.com",
) -> list[SessionInfo]:
    """
    Discover available assistant sessions.

    This function queries the API to find existing assistant sessions.

    Args:
        access_token: OAuth access token (required for API calls)
        org_uuid: Organization UUID (required for API calls)
        base_api_url: Base API URL

    Returns:
        List of discovered SessionInfo objects

    Note:
        This is a stub implementation that returns an empty list.
        The TypeScript reference also returns an empty array.
        Full implementation would query the session API.
    """
    # Stub implementation - returns empty list like TS reference
    return []


async def get_session_events(
    session_id: str,
    access_token: str,
    org_uuid: str,
    limit: int = 100,
    base_api_url: str = "https://api.anthropic.com",
) -> HistoryPage | None:
    """
    Get events for a specific session.

    Args:
        session_id: The session ID
        access_token: OAuth access token
        org_uuid: Organization UUID
        limit: Number of events to fetch
        base_api_url: Base API URL

    Returns:
        HistoryPage with events or None on error
    """
    ctx = await create_history_auth_ctx(
        session_id=session_id,
        access_token=access_token,
        org_uuid=org_uuid,
        base_api_url=base_api_url,
    )
    return await fetch_latest_events(ctx, limit)


async def get_older_session_events(
    session_id: str,
    before_id: str,
    access_token: str,
    org_uuid: str,
    limit: int = 100,
    base_api_url: str = "https://api.anthropic.com",
) -> HistoryPage | None:
    """
    Get older events for a specific session using cursor pagination.

    Args:
        session_id: The session ID
        before_id: Cursor for pagination (first_id from previous page)
        access_token: OAuth access token
        org_uuid: Organization UUID
        limit: Number of events to fetch
        base_api_url: Base API URL

    Returns:
        HistoryPage with events or None on error
    """
    ctx = await create_history_auth_ctx(
        session_id=session_id,
        access_token=access_token,
        org_uuid=org_uuid,
        base_api_url=base_api_url,
    )
    return await fetch_older_events(ctx, before_id, limit)


def create_session_info(
    session_id: str,
    created_at: datetime | None = None,
    last_active: datetime | None = None,
    message_count: int = 0,
    title: str | None = None,
    is_remote: bool = False,
    remote_url: str | None = None,
) -> SessionInfo:
    """
    Create a SessionInfo object.

    Args:
        session_id: Unique session identifier
        created_at: When the session was created
        last_active: When the session was last active
        message_count: Number of messages in the session
        title: Optional session title
        is_remote: Whether this is a remote session
        remote_url: Remote URL if applicable

    Returns:
        SessionInfo object
    """
    return SessionInfo(
        session_id=session_id,
        created_at=created_at,
        last_active=last_active,
        message_count=message_count,
        title=title,
        is_remote=is_remote,
        remote_url=remote_url,
    )


def get_assistant_mode_status() -> dict[str, Any]:
    """
    Get assistant mode status information.

    Returns:
        Dictionary with assistant mode status
    """
    config = get_assistant_mode_config()
    return {
        "enabled": config.enabled,
        "env_flag": config.assistant_mode_flag,
        "description": (
            "Assistant mode allows Claude Code to operate as an assistant "
            "without full CLI functionality"
        ),
    }
