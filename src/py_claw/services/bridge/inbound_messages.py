"""Inbound message processing for bridge.

Processes inbound user messages from the bridge, extracting content
and UUID for enqueueing. Supports both string content and
ContentBlockParam[] (e.g. messages containing images).

Normalizes image blocks from bridge clients that may use camelCase
`mediaType` instead of snake_case `media_type` (mobile-apps#5825).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Union

logger = logging.getLogger(__name__)


# Type aliases for message content
ContentBlock = dict[str, Any]
Content = Union[str, list[ContentBlock]]


@dataclass
class InboundMessageFields:
    """Extracted fields from an inbound message."""

    content: Content
    uuid: str | None = None


def extract_inbound_message_fields(
    msg: dict[str, Any],
) -> InboundMessageFields | None:
    """Extract inbound message fields from a bridge message.

    Process an inbound user message from the bridge, extracting content
    and UUID for enqueueing. Supports both string content and
    ContentBlockParam[] (e.g. messages containing images).

    Args:
        msg: The SDK message dictionary

    Returns:
        InboundMessageFields if valid, None if should be skipped
        (non-user type, missing/empty content)
    """
    msg_type = msg.get("type")
    if msg_type != "user":
        return None

    message = msg.get("message")
    if not message:
        return None

    content = message.get("content")
    if not content:
        return None

    # Handle empty array
    if isinstance(content, list) and len(content) == 0:
        return None

    # Extract UUID if present
    uuid = None
    if "uuid" in msg and isinstance(msg["uuid"], str):
        uuid = msg["uuid"]

    # Normalize image blocks if content is an array
    if isinstance(content, list):
        content = _normalize_image_blocks(content)

    return InboundMessageFields(content=content, uuid=uuid)


def _is_malformed_base64_image(block: ContentBlock) -> bool:
    """Check if an image block is malformed (missing media_type).

    Args:
        block: The content block to check

    Returns:
        True if the block is a malformed base64 image
    """
    if block.get("type") != "image":
        return False
    source = block.get("source")
    if not source or source.get("type") != "base64":
        return False
    # Check if media_type is missing (malformed)
    return "media_type" not in source and "media_type" not in source


def _detect_image_format_from_base64(data: str) -> str:
    """Detect image format from base64 data.

    Args:
        data: Base64 encoded image data

    Returns:
        Detected MIME type
    """
    # Common image format magic bytes
    SIGNATURES = {
        "/9j/": "image/jpeg",
        "iVBOR": "image/png",
        "R0lGO": "image/gif",
        "UklGR": "image/webp",
    }

    for sig, mime in SIGNATURES.items():
        if data.startswith(sig):
            return mime

    return "image/jpeg"  # Default


def _normalize_image_blocks(
    blocks: list[ContentBlock],
) -> list[ContentBlock]:
    """Normalize image content blocks from bridge clients.

    iOS/web clients may send `mediaType` (camelCase) instead of
    `media_type` (snake_case), or omit the field entirely.

    Args:
        blocks: List of content blocks

    Returns:
        Normalized content blocks (may be the same object if no normalization needed)
    """
    # Fast path: check if any blocks need normalization
    needs_normalization = any(_is_malformed_base64_image(b) for b in blocks)
    if not needs_normalization:
        return blocks

    # Normalize malformed blocks
    result = []
    for block in blocks:
        if not _is_malformed_base64_image(block):
            result.append(block)
            continue

        # Get source (guaranteed to exist and be base64 at this point)
        source = block["source"]

        # Determine media type
        media_type = source.get("mediaType")  # camelCase from client
        if not media_type:
            # Try to detect from base64 data
            data = source.get("data", "")
            media_type = _detect_image_format_from_base64(data)

        # Normalize to snake_case
        normalized_block = {
            **block,
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": source.get("data", ""),
            },
        }
        result.append(normalized_block)

    return result
