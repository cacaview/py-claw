"""Inbound attachment resolution for bridge.

Resolve file_uuid attachments on inbound bridge user messages.

Web composer uploads via cookie-authed /api/{org}/upload, sends file_uuid
alongside the message. Here we fetch each via GET /api/oauth/files/{uuid}/content
(oauth-authed, same store), write to ~/.claude/uploads/{sessionId}/, and
return @path refs to prepend.

Best-effort: any failure (no token, network, non-2xx, disk) logs debug and
skips that attachment.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)


# Download timeout in milliseconds
DOWNLOAD_TIMEOUT_MS = 30_000


@dataclass
class InboundAttachment:
    """An inbound file attachment."""

    file_uuid: str
    file_name: str


def extract_inbound_attachments(msg: dict[str, Any]) -> list[InboundAttachment]:
    """Extract file attachments from an inbound message.

    Args:
        msg: The message dictionary

    Returns:
        List of InboundAttachment objects
    """
    if not isinstance(msg, dict):
        return []

    file_attachments = msg.get("file_attachments")
    if not file_attachments:
        return []

    if not isinstance(file_attachments, list):
        return []

    result = []
    for att in file_attachments:
        if not isinstance(att, dict):
            continue
        if not att.get("file_uuid") or not att.get("file_name"):
            continue
        result.append(
            InboundAttachment(
                file_uuid=str(att["file_uuid"]),
                file_name=str(att["file_name"]),
            )
        )

    return result


def _sanitize_file_name(name: str) -> str:
    """Sanitize a file name for safe local storage.

    Strip path components and keep only filename-safe chars.
    file_name comes from the network (web composer), so treat it as untrusted.

    Args:
        name: The original file name

    Returns:
        Sanitized file name
    """
    # Get just the base name
    base = os.path.basename(name)
    # Replace unsafe chars with underscore
    safe = "".join(c if c.isalnum() or c in ".-_" else "_" for c in base)
    return safe or "attachment"


def _get_uploads_dir(session_id: str) -> str:
    """Get the uploads directory for a session.

    Args:
        session_id: The session ID

    Returns:
        Absolute path to uploads directory
    """
    # Use standard config directory
    config_home = os.path.expanduser("~/.claude")
    return os.path.join(config_home, "uploads", session_id)


def _get_bridge_access_token() -> str | None:
    """Get the bridge access token.

    Returns:
        Access token or None if not available
    """
    # TODO: Integrate with actual bridge config/token storage
    return os.environ.get("CLAUDE_BRIDGE_ACCESS_TOKEN")


def _get_bridge_base_url() -> str | None:
    """Get the bridge base URL.

    Returns:
        Base URL or None if not configured
    """
    # TODO: Integrate with actual bridge config
    return os.environ.get("CLAUDE_BRIDGE_BASE_URL")


async def _resolve_one(
    att: InboundAttachment,
    session_id: str,
) -> str | None:
    """Resolve a single attachment to a local file path.

    Args:
        att: The attachment to resolve
        session_id: The session ID

    Returns:
        Local file path on success, None on failure
    """
    token = _get_bridge_access_token()
    if not token:
        logger.debug("[bridge:inbound-attach] skip: no oauth token")
        return None

    base_url = _get_bridge_base_url()
    if not base_url:
        logger.debug("[bridge:inbound-attach] skip: no base url configured")
        return None

    url = f"{base_url}/api/oauth/files/{quote(att.file_uuid)}/content"

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT_MS / 1000),
            ) as response:
                if response.status != 200:
                    logger.debug(
                        f"[bridge:inbound-attach] fetch {att.file_uuid} failed: status={response.status}"
                    )
                    return None

                data = await response.read()

    except Exception as e:
        logger.debug(f"[bridge:inbound-attach] fetch {att.file_uuid} threw: {e}")
        return None

    # Generate safe filename with UUID prefix to avoid collisions
    safe_name = _sanitize_file_name(att.file_name)
    prefix = att.file_uuid[:8] if len(att.file_uuid) >= 8 else att.file_uuid
    prefix = "".join(c if c.isalnum() or c in "_-" else "_" for c in prefix)
    if not prefix:
        import uuid

        prefix = str(uuid.uuid4())[:8]

    uploads_dir = _get_uploads_dir(session_id)
    out_path = os.path.join(uploads_dir, f"{prefix}-{safe_name}")

    try:
        os.makedirs(uploads_dir, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
    except Exception as e:
        logger.debug(f"[bridge:inbound-attach] write {out_path} failed: {e}")
        return None

    logger.debug(
        f"[bridge:inbound-attach] resolved {att.file_uuid} -> {out_path} ({len(data)} bytes)"
    )
    return out_path


async def resolve_inbound_attachments(
    attachments: list[InboundAttachment],
    session_id: str,
) -> str:
    """Resolve all attachments to @path refs.

    Args:
        attachments: List of attachments to resolve
        session_id: The session ID

    Returns:
        Space-separated @path refs (quoted form), or empty string if none resolved
    """
    if not attachments:
        return ""

    logger.debug(f"[bridge:inbound-attach] resolving {len(attachments)} attachment(s)")

    tasks = [_resolve_one(att, session_id) for att in attachments]
    paths = await asyncio.gather(*tasks, return_exceptions=True)

    ok_paths = [p for p in paths if isinstance(p, str)]
    if not ok_paths:
        return ""

    # Use quoted form for paths with spaces
    return " ".join(f'@"{p}"' for p in ok_paths) + " "


def prepend_path_refs(
    content: Content,
    prefix: str,
) -> Content:
    """Prepend @path refs to content.

    Prepend path refs to content, whichever form it's in.
    Targets the LAST text block.

    Args:
        content: The content (string or ContentBlock array)
        prefix: The path refs prefix to prepend

    Returns:
        Content with path refs prepended
    """
    if not prefix:
        return content

    if isinstance(content, str):
        return prefix + content

    # Find last text block
    text_index = -1
    for i in range(len(content) - 1, -1, -1):
        if isinstance(content[i], dict) and content[i].get("type") == "text":
            text_index = i
            break

    if text_index != -1:
        block = content[text_index]
        return [
            *content[:text_index],
            {**block, "text": prefix + block.get("text", "")},
            *content[text_index + 1 :],
        ]

    # No text block - append one at the end
    return [*content, {"type": "text", "text": prefix.strip()}]


# Type alias for Content
Content = str | list[dict[str, Any]]


async def resolve_and_prepend(
    msg: dict[str, Any],
    content: Content,
    session_id: str,
) -> Content:
    """Extract, resolve, and prepend attachments from a message.

    Convenience function: extract + resolve + prepend.
    No-op when the message has no file_attachments field.

    Args:
        msg: The message dictionary
        content: The current content
        session_id: The session ID

    Returns:
        Content with path refs prepended
    """
    attachments = extract_inbound_attachments(msg)
    if not attachments:
        return content

    prefix = await resolve_inbound_attachments(attachments, session_id)
    return prepend_path_refs(content, prefix)
