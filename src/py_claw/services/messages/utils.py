"""Message utility functions for the Python Claude Code runtime.

Based on ClaudeCode-main/src/utils/messages.ts
"""
from __future__ import annotations

import uuid as uuid_mod
from typing import Any

from .constants import (
    CANCEL_MESSAGE,
    INTERRUPT_MESSAGE,
    INTERRUPT_MESSAGE_FOR_TOOL_USE,
    NO_RESPONSE_REQUESTED,
    REJECT_MESSAGE,
    SYNTHETIC_MESSAGES,
)
from .types import (
    AssistantMessage,
    Message,
    NormalizedMessage,
    SystemMessage,
    UserMessage,
)


def _get_msg_type(message: Message | dict[str, Any]) -> str | None:
    """Get the type from a message (works for both dicts and dataclasses)."""
    if isinstance(message, dict):
        return message.get("type")
    return getattr(message, "type", None)


def _get_msg_field(message: Message | dict[str, Any], field: str, default: Any = None) -> Any:
    """Get a field from a message (works for both dicts and dataclasses)."""
    if isinstance(message, dict):
        return message.get(field, default)
    return getattr(message, field, default)


def derive_short_message_id(uid: str) -> str:
    """Derive a short stable message ID (6-char base36 string) from a UUID.

    Used for snip tool referencing — injected into API-bound messages as [id:...] tags.
    Deterministic: same UUID always produces the same short ID.

    Args:
        uid: Full UUID string.

    Returns:
        6-character base36 string.
    """
    # Take first 10 hex chars from the UUID (skipping dashes)
    hex_part = uid.replace("-", "")[:10]
    # Convert to base36 for shorter representation, take 6 chars
    return str(int(hex_part, 16) // 36)[:6]


def with_memory_correction_hint(message: str, is_auto_memory_enabled: bool = False) -> str:
    """Append a memory correction hint to a rejection/cancellation message.

    Args:
        message: Original message.
        is_auto_memory_enabled: Whether auto-memory is enabled.

    Returns:
        Message with hint appended if auto-memory is enabled.
    """
    if is_auto_memory_enabled:
        from .constants import MEMORY_CORRECTION_HINT

        return message + MEMORY_CORRECTION_HINT
    return message


def is_classifier_denial(content: str) -> bool:
    """Check if a tool result message is a classifier denial.

    Used by the UI to render a short summary instead of the full message.

    Args:
        content: Message content to check.

    Returns:
        True if this is a classifier denial message.
    """
    from .constants import AUTO_MODE_REJECTION_PREFIX

    return content.startswith(AUTO_MODE_REJECTION_PREFIX)


def build_yolo_rejection_message(reason: str) -> str:
    """Build a rejection message for auto mode classifier denials.

    Encourages continuing with other tasks and suggests permission rules.

    Args:
        reason: The classifier's reason for denying the action.

    Returns:
        Formatted rejection message.
    """
    from .constants import AUTO_MODE_REJECTION_PREFIX, DENIAL_WORKAROUND_GUIDANCE

    prefix = AUTO_MODE_REJECTION_PREFIX
    return (
        f"{prefix}{reason}. "
        "If you have other tasks that don't depend on this action, continue working on those. "
        f"{DENIAL_WORKAROUND_GUIDANCE} "
        "To allow this type of action in the future, the user can add a Bash permission rule to their settings."
    )


def build_classifier_unavailable_message(tool_name: str, classifier_model: str) -> str:
    """Build a message for when the auto mode classifier is temporarily unavailable.

    Args:
        tool_name: Name of the tool.
        classifier_model: Name of the classifier model.

    Returns:
        Formatted unavailable message.
    """
    return (
        f"{classifier_model} is temporarily unavailable, so auto mode cannot determine "
        f"the safety of {tool_name} right now. "
        "Wait briefly and then try this action again. "
        "If it keeps failing, continue with other tasks that don't require this action "
        "and come back to it later. "
        "Note: reading files, searching code, and other read-only operations do not require "
        "the classifier and can still be used."
    )


def auto_reject_message(tool_name: str) -> str:
    """Build an auto-reject message for a tool.

    Args:
        tool_name: Name of the rejected tool.

    Returns:
        Auto-reject message.
    """
    from .constants import DENIAL_WORKAROUND_GUIDANCE

    return f"Permission to use {tool_name} has been denied. {DENIAL_WORKAROUND_GUIDANCE}"


def dont_ask_reject_message(tool_name: str) -> str:
    """Build a don't-ask reject message for a tool.

    Args:
        tool_name: Name of the rejected tool.

    Returns:
        Don't-ask reject message.
    """
    from .constants import DENIAL_WORKAROUND_GUIDANCE

    return (
        f"Permission to use {tool_name} has been denied because Claude Code is running "
        f"in don't ask mode. {DENIAL_WORKAROUND_GUIDANCE}"
    )


def is_synthetic_message(message: Message) -> bool:
    """Check if a message is synthetic (system-generated).

    Args:
        message: Message to check.

    Returns:
        True if the message is synthetic.
    """
    if _get_msg_type(message) in ("progress", "attachment", "system"):
        return False

    content = _get_msg_field(message, "message", {}).get("content", [])
    if not isinstance(content, list) or not content:
        return False

    if content[0].get("type") != "text":
        return False

    text = content[0].get("text", "")
    return text in SYNTHETIC_MESSAGES


def get_last_assistant_message(messages: list[Message]) -> AssistantMessage | None:
    """Get the last assistant message from a list.

    Args:
        messages: List of messages.

    Returns:
        Last assistant message or None.
    """
    for msg in reversed(messages):
        if _get_msg_type(msg) == "assistant":
            return msg
    return None


def has_tool_calls_in_last_assistant_turn(messages: list[Message]) -> bool:
    """Check if the last assistant message has tool calls.

    Args:
        messages: List of messages.

    Returns:
        True if the last assistant message contains tool_use blocks.
    """
    last_assistant = get_last_assistant_message(messages)
    if not last_assistant:
        return False

    content = _get_msg_field(last_assistant, "message", {}).get("content", [])
    if not isinstance(content, list):
        return False

    return any(block.get("type") == "tool_use" for block in content)


def is_not_empty_message(message: Message) -> bool:
    """Check if a message is not empty.

    Args:
        message: Message to check.

    Returns:
        True if the message has meaningful content.
    """
    from .constants import NO_CONTENT_MESSAGE

    if _get_msg_type(message) not in ("user", "assistant"):
        return _get_msg_type(message) != "system"

    content = _get_msg_field(message, "message", {}).get("content", [])
    if not content:
        return False

    # Skip multi-block messages for now
    if len(content) > 1:
        return True

    if content[0].get("type") != "text":
        return True

    text = content[0].get("text", "")
    return (
        text.strip() != ""
        and text != NO_CONTENT_MESSAGE
        and text != INTERRUPT_MESSAGE_FOR_TOOL_USE
    )


def derive_uuid(parent_uuid: str, index: int) -> str:
    """Derive a deterministic UUID from a parent UUID and index.

    Produces a stable UUID-shaped string from a parent UUID + content block index
    so that the same input always produces the same key across calls.

    Args:
        parent_uuid: Parent UUID.
        index: Content block index.

    Returns:
        Derived UUID string.
    """
    hex_index = format(index, "012x")
    return f"{parent_uuid[:24]}{hex_index}"


def normalize_messages(messages: list[Message]) -> list[NormalizedMessage]:
    """Split messages so each content block gets its own message.

    When a message has multiple content blocks, it splits into multiple messages,
    each with a single content block.

    Args:
        messages: List of messages to normalize.

    Returns:
        List of normalized messages.
    """
    result: list[NormalizedMessage] = []
    is_new_chain = False

    for message in messages:
        msg_type = _get_msg_type(message)

        if msg_type == "assistant":
            content = _get_msg_field(message, "message", {}).get("content", [])
            if len(content) > 1:
                is_new_chain = True

            for i, block in enumerate(content):
                block_uuid = _get_msg_field(message, "uuid")
                if is_new_chain and block_uuid:
                    block_uuid = derive_uuid(block_uuid, i)
                elif not block_uuid:
                    block_uuid = str(uuid_mod.uuid4())

                result.append(
                    {
                        "type": "assistant",
                        "timestamp": _get_msg_field(message, "timestamp"),
                        "message": {
                            **_get_msg_field(message, "message", {}),
                            "content": [block],
                        },
                        "uuid": block_uuid,
                        "requestId": _get_msg_field(message, "requestId"),
                        "error": _get_msg_field(message, "error"),
                    }
                )

        elif msg_type == "user":
            user_content = _get_msg_field(message, "message", {}).get("content", [])
            if isinstance(user_content, str):
                result.append(
                    {
                        "type": "user",
                        "uuid": _get_msg_field(message, "uuid") or str(uuid_mod.uuid4()),
                        "parentUuid": _get_msg_field(message, "parentUuid"),
                        "timestamp": _get_msg_field(message, "timestamp"),
                        "createdAt": _get_msg_field(message, "createdAt"),
                        "isMeta": _get_msg_field(message, "isMeta", False),
                        "isVirtual": _get_msg_field(message, "isVirtual", False),
                        "isCompactSummary": _get_msg_field(message, "isCompactSummary", False),
                        "origin": _get_msg_field(message, "origin"),
                        "message": {
                            **_get_msg_field(message, "message", {}),
                            "content": [{"type": "text", "text": user_content}],
                        },
                    }
                )
            elif isinstance(user_content, list):
                for i, block in enumerate(user_content):
                    block_uuid = _get_msg_field(message, "uuid")
                    if is_new_chain and block_uuid:
                        block_uuid = derive_uuid(block_uuid, i)
                    elif not block_uuid:
                        block_uuid = str(uuid_mod.uuid4())

                    result.append(
                        {
                            "type": "user",
                            "uuid": block_uuid,
                            "parentUuid": _get_msg_field(message, "parentUuid"),
                            "timestamp": _get_msg_field(message, "timestamp"),
                            "createdAt": _get_msg_field(message, "createdAt"),
                            "isMeta": _get_msg_field(message, "isMeta", False),
                            "isVirtual": _get_msg_field(message, "isVirtual", False),
                            "isCompactSummary": _get_msg_field(message, "isCompactSummary", False),
                            "origin": _get_msg_field(message, "origin"),
                            "message": {
                                **_get_msg_field(message, "message", {}),
                                "content": [block],
                            },
                        }
                    )
            is_new_chain = True

        elif msg_type in ("system", "progress", "attachment"):
            result.append(message)

    return result


def create_user_message(
    content: str | list[dict[str, Any]],
    msg_uuid: str | None = None,
    timestamp: str | None = None,
    is_meta: bool = False,
    is_virtual: bool = False,
    is_compact_summary: bool = False,
    origin: dict[str, Any] | None = None,
) -> UserMessage:
    """Create a user message.

    Args:
        content: Message content (string or content blocks).
        msg_uuid: Optional UUID.
        timestamp: Optional timestamp.
        is_meta: Whether this is a meta message.
        is_virtual: Whether this is a virtual message.
        is_compact_summary: Whether this is a compact summary.
        origin: Optional origin metadata.

    Returns:
        UserMessage instance.
    """
    if isinstance(content, str):
        message_content: dict[str, Any] = {"content": [{"type": "text", "text": content}]}
    else:
        message_content = {"content": content}

    return UserMessage(
        type="user",
        message=message_content,
        uuid=msg_uuid or str(uuid_mod.uuid4()),
        timestamp=timestamp,
        isMeta=is_meta,
        isVirtual=is_virtual,
        isCompactSummary=is_compact_summary,
        origin=origin,
    )


def create_assistant_message(
    content: str | list[dict[str, Any]],
    msg_uuid: str | None = None,
    timestamp: str | None = None,
    is_virtual: bool = False,
) -> AssistantMessage:
    """Create an assistant message.

    Args:
        content: Message content (string or content blocks).
        msg_uuid: Optional UUID.
        timestamp: Optional timestamp.
        is_virtual: Whether this is a virtual message.

    Returns:
        AssistantMessage instance.
    """
    from .constants import NO_CONTENT_MESSAGE

    if isinstance(content, str):
        message_content: list[dict[str, Any]] = [
            {"type": "text", "text": content if content != "" else NO_CONTENT_MESSAGE}
        ]
    else:
        message_content = content

    return AssistantMessage(
        type="assistant",
        message={"content": message_content},
        uuid=msg_uuid or str(uuid_mod.uuid4()),
        timestamp=timestamp,
        isVirtual=is_virtual,
    )


def create_progress_message(
    progress: dict[str, Any],
    msg_uuid: str | None = None,
) -> dict[str, Any]:
    """Create a progress message.

    Args:
        progress: Progress data.
        msg_uuid: Optional UUID.

    Returns:
        Progress message dict.
    """
    return {
        "type": "progress",
        "progress": progress,
        "uuid": msg_uuid or str(uuid_mod.uuid4()),
    }


def create_interrupt_message() -> UserMessage:
    """Create a user interrupt message.

    Returns:
        UserMessage with interrupt content.
    """
    return create_user_message(content=INTERRUPT_MESSAGE)


def create_cancel_message() -> UserMessage:
    """Create a cancel message.

    Returns:
        UserMessage with cancel content.
    """
    return create_user_message(content=CANCEL_MESSAGE)


def create_reject_message(reason: str | None = None) -> UserMessage:
    """Create a reject message.

    Args:
        reason: Optional rejection reason.

    Returns:
        UserMessage with reject content.
    """
    from .constants import REJECT_MESSAGE_WITH_REASON_PREFIX

    if reason:
        content = REJECT_MESSAGE_WITH_REASON_PREFIX + reason
    else:
        content = REJECT_MESSAGE
    return create_user_message(content=content)


def is_tool_use_request_message(message: Message) -> bool:
    """Check if a message is a tool use request.

    Args:
        message: Message to check.

    Returns:
        True if this is a tool use request.
    """
    if _get_msg_type(message) != "assistant":
        return False

    content = _get_msg_field(message, "message", {}).get("content", [])
    return any(block.get("type") == "tool_use" for block in content)


def is_tool_use_result_message(message: Message) -> bool:
    """Check if a message is a tool use result.

    Args:
        message: Message to check.

    Returns:
        True if this is a tool use result.
    """
    if _get_msg_type(message) != "user":
        return False

    content = _get_msg_field(message, "message", {}).get("content", [])
    return any(block.get("type") == "tool_result" for block in content)


def get_tool_use_ids(messages: list[NormalizedMessage]) -> list[str]:
    """Extract tool use IDs from messages.

    Args:
        messages: List of normalized messages.

    Returns:
        List of tool use IDs.
    """
    ids: list[str] = []
    for message in messages:
        if _get_msg_type(message) != "assistant":
            continue
        content = _get_msg_field(message, "message", {}).get("content", [])
        for block in content:
            if block.get("type") == "tool_use":
                tool_id = block.get("id")
                if tool_id:
                    ids.append(tool_id)
    return ids


def get_tool_result_ids(messages: list[NormalizedMessage]) -> list[str]:
    """Extract tool result IDs from messages.

    Args:
        messages: List of normalized messages.

    Returns:
        List of tool result IDs.
    """
    ids: list[str] = []
    for message in messages:
        if _get_msg_type(message) != "user":
            continue
        content = _get_msg_field(message, "message", {}).get("content", [])
        for block in content:
            if block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id")
                if tool_use_id:
                    ids.append(tool_use_id)
    return ids


def build_message_lookups(messages: list[NormalizedMessage]) -> dict[str, Any]:
    """Build lookup structures for messages.

    Args:
        messages: List of normalized messages.

    Returns:
        Dictionary with message lookups.
    """
    tool_use_ids: list[str] = []
    tool_result_ids: list[str] = []
    progress_messages: list[dict[str, Any]] = []

    for message in messages:
        msg_type = _get_msg_type(message)

        if msg_type == "assistant":
            content = _get_msg_field(message, "message", {}).get("content", [])
            for block in content:
                if block.get("type") == "tool_use":
                    tool_id = block.get("id")
                    if tool_id:
                        tool_use_ids.append(tool_id)
                elif block.get("type") == "thinking":
                    pass  # Handle thinking blocks if needed

        elif msg_type == "user":
            content = _get_msg_field(message, "message", {}).get("content", [])
            for block in content:
                if block.get("type") == "tool_result":
                    tool_use_id = block.get("tool_use_id")
                    if tool_use_id:
                        tool_result_ids.append(tool_use_id)

        elif msg_type == "progress":
            progress_messages.append(message)

    return {
        "toolUseIds": tool_use_ids,
        "toolResultIds": tool_result_ids,
        "progressMessages": progress_messages,
    }
