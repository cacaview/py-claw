"""
Session history service.

Handles fetching and pagination of session events.

Based on ClaudeCode-main/src/assistant/sessionHistory.ts
"""
from __future__ import annotations

from typing import Any

import httpx

from py_claw.messages.types import Message

from .types import HISTORY_PAGE_SIZE, HistoryAuthCtx, HistoryPage


async def create_history_auth_ctx(
    session_id: str,
    access_token: str,
    org_uuid: str,
    base_api_url: str = "https://api.anthropic.com",
) -> HistoryAuthCtx:
    """
    Prepare auth + headers + base URL once, reuse across pages.

    Args:
        session_id: The session ID
        access_token: OAuth access token
        org_uuid: Organization UUID
        base_api_url: Base API URL

    Returns:
        HistoryAuthCtx with auth headers and base URL
    """
    return HistoryAuthCtx(
        base_url=f"{base_api_url}/v1/sessions/{session_id}/events",
        headers={
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": "ccr-byoc-2025-07-29",
            "x-organization-uuid": org_uuid,
        },
    )


async def _fetch_page(
    ctx: HistoryAuthCtx,
    params: dict[str, str | int | bool],
    label: str,
    timeout: float = 15.0,
) -> HistoryPage | None:
    """
    Fetch a page of session events.

    Args:
        ctx: Authentication context
        params: Query parameters
        label: Label for logging
        timeout: Request timeout in seconds

    Returns:
        HistoryPage or None on error
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                ctx.base_url,
                headers=ctx.headers,
                params=params,
                timeout=timeout,
            )

        if resp.status_code != 200:
            return None

        data = resp.json()
        return HistoryPage(
            events=_parse_messages(data.get("data", [])),
            first_id=data.get("first_id"),
            has_more=data.get("has_more", False),
        )
    except Exception:
        return None


async def fetch_latest_events(
    ctx: HistoryAuthCtx,
    limit: int = HISTORY_PAGE_SIZE,
) -> HistoryPage | None:
    """
    Newest page: last `limit` events, chronological, via anchor_to_latest.
    has_more=true means older events exist.

    Args:
        ctx: Authentication context
        limit: Number of events to fetch

    Returns:
        HistoryPage or None on error
    """
    return await _fetch_page(
        ctx,
        {"limit": limit, "anchor_to_latest": True},
        "fetchLatestEvents",
    )


async def fetch_older_events(
    ctx: HistoryAuthCtx,
    before_id: str,
    limit: int = HISTORY_PAGE_SIZE,
) -> HistoryPage | None:
    """
    Older page: events immediately before `beforeId` cursor.

    Args:
        ctx: Authentication context
        before_id: Cursor for pagination
        limit: Number of events to fetch

    Returns:
        HistoryPage or None on error
    """
    return await _fetch_page(
        ctx,
        {"limit": limit, "before_id": before_id},
        "fetchOlderEvents",
    )


def _parse_messages(data: list[dict[str, Any]]) -> list[Message]:
    """
    Parse raw API messages into Message objects.

    Args:
        data: Raw message data from API

    Returns:
        List of Message objects
    """
    messages: list[Message] = []
    for item in data:
        try:
            # Parse the message based on role
            role = item.get("role", "user")
            content = item.get("content", "")

            if role == "user":
                from py_claw.messages.factories import create_user_message

                msg = create_user_message(content=content)
            elif role == "assistant":
                from py_claw.messages.factories import create_assistant_message

                msg = create_assistant_message(content=content)
            else:
                continue

            messages.append(msg)
        except Exception:
            continue

    return messages
