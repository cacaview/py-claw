"""
Message normalization functions for py-claw runtime.

Based on ClaudeCode-main/src/utils/messages.ts - normalizeMessagesForAPI
"""
from __future__ import annotations

from typing import Any

from .constants import NO_CONTENT_MESSAGE, TOOL_REFERENCE_TURN_BOUNDARY
from .types import Message, NormalizedMessage
from .utils import derive_uuid, is_empty_message_text


def normalize_messages(messages: list[Message]) -> list[Message]:
    """
    Normalize messages by splitting multi-block messages.

    Each content block gets its own message with a derived UUID.
    This is used to "denormalize" messages for UI rendering.

    Args:
        messages: List of messages

    Returns:
        List of normalized messages
    """
    normalized: list[Message] = []

    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "assistant":
            content = getattr(msg, "content", None)
            if content and isinstance(content, list):
                for i, block in enumerate(content):
                    if isinstance(block, dict):
                        new_msg = type(msg)(
                            uuid=derive_uuid(getattr(msg, "uuid", "default"), i),
                            parent_uuid=getattr(msg, "uuid", None),
                            timestamp=getattr(msg, "timestamp", None),
                            content=[block],
                        )
                        normalized.append(new_msg)
            else:
                normalized.append(msg)
        elif msg_type == "user":
            content = getattr(msg, "content", None)
            if content and isinstance(content, list):
                for i, block in enumerate(content):
                    if isinstance(block, dict):
                        new_msg = type(msg)(
                            uuid=derive_uuid(getattr(msg, "uuid", "default"), i),
                            parent_uuid=getattr(msg, "uuid", None),
                            timestamp=getattr(msg, "timestamp", None),
                            content=[block],
                            is_meta=getattr(msg, "is_meta", False),
                            is_virtual=getattr(msg, "is_virtual", False),
                            is_compact_summary=getattr(msg, "is_compact_summary", False),
                            tool_use_result=getattr(msg, "tool_use_result", None),
                            origin=getattr(msg, "origin", None),
                        )
                        normalized.append(new_msg)
            else:
                normalized.append(msg)
        else:
            normalized.append(msg)

    return normalized


def filter_unresolved_tool_uses(messages: list[Message]) -> list[Message]:
    """
    Remove assistant messages where ALL tool_use blocks lack matching tool_result.

    Args:
        messages: List of messages

    Returns:
        Filtered messages
    """
    # Build set of tool_use IDs that have results
    result_ids: set[str] = set()
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "user":
            content = getattr(msg, "content", None)
            if content and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id:
                            result_ids.add(tool_use_id)

    # Filter assistant messages
    filtered: list[Message] = []
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "assistant":
            content = getattr(msg, "content", None)
            if content and isinstance(content, list):
                has_tool_use = False
                has_result = False
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            has_tool_use = True
                            block_id = block.get("id")
                            if block_id and block_id in result_ids:
                                has_result = True
                # Keep if has tool use AND at least one has result
                if has_tool_use and has_result:
                    filtered.append(msg)
                elif not has_tool_use:
                    filtered.append(msg)
        else:
            filtered.append(msg)

    return filtered


def filter_whitespace_only_assistant_messages(
    messages: list[Message],
) -> list[Message]:
    """
    Remove assistant messages with only whitespace-only text content.

    Args:
        messages: List of messages

    Returns:
        Filtered messages
    """
    filtered: list[Message] = []
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "assistant":
            content = getattr(msg, "content", None)
            if content and isinstance(content, list):
                # Check if there's any non-whitespace text
                has_text = False
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text and not is_empty_message_text(text):
                            has_text = True
                            break
                if has_text:
                    filtered.append(msg)
                # Don't add whitespace-only assistant messages
            else:
                filtered.append(msg)
        else:
            filtered.append(msg)

    return filtered


def merge_user_messages(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """
    Merge two consecutive user messages.

    Concatenates content blocks, inserting newline between text.
    Handles is_meta semantics for snip tool.

    Args:
        a: First user message
        b: Second user message

    Returns:
        Merged user message
    """
    # Extract content from both
    a_content = a.get("content", "")
    b_content = b.get("content", "")

    if isinstance(a_content, str) and isinstance(b_content, str):
        # Simple string concatenation
        if a_content and b_content:
            merged = f"{a_content}\n{b_content}"
        else:
            merged = a_content or b_content
    elif isinstance(a_content, list) and isinstance(b_content, list):
        # List concatenation with newline between
        merged = a_content + [{"type": "text", "text": "\n"}] + b_content
    elif isinstance(a_content, list):
        merged = a_content + [{"type": "text", "text": b_content}]
    elif isinstance(b_content, list):
        merged = [{"type": "text", "text": a_content}] + b_content
    else:
        merged = a_content or b_content

    return {
        **a,
        "content": merged,
        "uuid": a.get("uuid") or b.get("uuid"),
    }


def merge_assistant_messages(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """
    Merge two consecutive assistant messages.

    Args:
        a: First assistant message
        b: Second assistant message

    Returns:
        Merged assistant message
    """
    a_content = a.get("content", [])
    b_content = b.get("content", [])

    if isinstance(a_content, list) and isinstance(b_content, list):
        merged = a_content + b_content
    else:
        merged = a_content or b_content

    return {
        **a,
        "content": merged,
        "uuid": a.get("uuid") or b.get("uuid"),
    }


def normalize_messages_for_api(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Normalize messages for API submission.

    This is a multi-pass normalization pipeline that:
    1. Filters virtual messages
    2. Merges consecutive user messages
    3. Normalizes tool inputs
    4. Filters orphaned thinking-only messages
    5. Filters trailing thinking from last assistant
    6. Filters whitespace-only assistant messages
    7. Ensures non-empty assistant content

    Args:
        messages: List of messages
        tools: Optional list of tools for normalization

    Returns:
        Normalized messages for API
    """
    result = messages[:]

    # 1. Filter virtual messages
    result = [msg for msg in result if not msg.get("is_virtual", False)]

    # 2. Merge consecutive user messages
    merged: list[dict[str, Any]] = []
    for msg in result:
        if merged and merged[-1].get("type") == "user" and msg.get("type") == "user":
            merged[-1] = merge_user_messages(merged[-1], msg)
        else:
            merged.append(msg)
    result = merged

    # 3. Filter orphaned thinking-only messages
    result = _filter_orphaned_thinking_messages(result)

    # 4. Filter trailing thinking from last assistant
    result = _filter_trailing_thinking(result)

    # 5. Filter whitespace-only assistant messages
    result = _filter_whitespace_only(result)

    # 6. Ensure non-empty assistant content
    result = _ensure_nonempty_content(result)

    return result


def _filter_orphaned_thinking_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filter thinking-only messages that have no sibling with non-thinking content.

    Args:
        messages: List of messages

    Returns:
        Filtered messages
    """
    # Build map of message UUIDs to their content types
    uuid_to_has_non_thinking: dict[str, bool] = {}

    for msg in messages:
        msg_uuid = msg.get("uuid")
        if not msg_uuid:
            continue

        content = msg.get("content", [])
        has_non_thinking = False

        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type and block_type not in ("thinking", "redacted_thinking"):
                        has_non_thinking = True
                        break

        uuid_to_has_non_thinking[msg_uuid] = has_non_thinking

    # Filter messages
    filtered: list[dict[str, Any]] = []
    for msg in messages:
        msg_uuid = msg.get("uuid", "")
        content = msg.get("content", [])

        if msg.get("type") == "assistant" and isinstance(content, list):
            # Check if all blocks are thinking-only
            all_thinking = all(
                isinstance(block, dict) and block.get("type") in ("thinking", "redacted_thinking")
                for block in content
                if isinstance(block, dict)
            )

            if all_thinking:
                # Check if there's a sibling message with same UUID having non-thinking
                if uuid_to_has_non_thinking.get(msg_uuid, False):
                    # Has non-thinking sibling, keep this one
                    filtered.append(msg)
                # Otherwise skip this thinking-only message
            else:
                filtered.append(msg)
        else:
            filtered.append(msg)

    return filtered


def _filter_trailing_thinking(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filter trailing thinking/redacted_thinking blocks from last assistant message.

    Args:
        messages: List of messages

    Returns:
        Messages with trailing thinking removed
    """
    if not messages:
        return messages

    result = messages[:-1]
    last = messages[-1]

    if last.get("type") == "assistant":
        content = last.get("content", [])
        if isinstance(content, list):
            # Filter trailing thinking blocks
            filtered_content = []
            trailing_thinking = True

            for block in reversed(content):
                if isinstance(block, dict):
                    block_type = block.get("type")
                    if trailing_thinking and block_type in ("thinking", "redacted_thinking"):
                        continue  # Skip trailing thinking
                    trailing_thinking = False
                    filtered_content.insert(0, block)

            if filtered_content:
                last = {**last, "content": filtered_content}

    result.append(last)
    return result


def _filter_whitespace_only(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Filter assistant messages with only whitespace content.

    Args:
        messages: List of messages

    Returns:
        Filtered messages
    """
    filtered: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("type") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                if not is_empty_message_text(content):
                    filtered.append(msg)
            elif isinstance(content, list):
                # Check if there's any non-empty text
                has_text = any(
                    isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
                    for b in content
                    if isinstance(b, dict)
                )
                if has_text:
                    filtered.append(msg)
            else:
                filtered.append(msg)
        else:
            filtered.append(msg)
    return filtered


def _ensure_nonempty_content(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Ensure assistant messages have non-empty content.

    Args:
        messages: List of messages

    Returns:
        Messages with content ensured
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("type") == "assistant":
            content = msg.get("content")
            if not content or (isinstance(content, list) and len(content) == 0):
                # Replace with placeholder
                msg = {**msg, "content": [{"type": "text", "text": NO_CONTENT_MESSAGE}]}
        result.append(msg)
    return result


def reorder_attachments_for_api(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Reorder attachments to bubble them up to stopping points.

    Bottom-up scan; attachments collected until a stopping point
    (assistant message or user message with tool_result), then
    emitted after the stopping point.

    Args:
        messages: List of messages

    Returns:
        Reordered messages
    """
    result: list[dict[str, Any]] = []
    pending_attachments: list[dict[str, Any]] = []

    for msg in reversed(messages):
        msg_type = msg.get("type")

        # Check if this is a stopping point
        is_stopping = False
        if msg_type == "assistant":
            is_stopping = True
        elif msg_type == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        is_stopping = True
                        break

        if is_stopping:
            # Emit pending attachments first
            result = pending_attachments + result
            pending_attachments = []

        # Check if this is an attachment
        if msg_type == "attachment":
            pending_attachments.insert(0, msg)
        else:
            result.insert(0, msg)

    # Handle remaining pending attachments
    if pending_attachments:
        result = pending_attachments + result

    return result
