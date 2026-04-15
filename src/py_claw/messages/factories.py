"""
Message factory functions for py-claw runtime.

Based on ClaudeCode-main/src/utils/messages.ts
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from .constants import (
    CANCEL_MESSAGE,
    INTERRUPT_MESSAGE,
    REJECT_MESSAGE,
    SUBAGENT_REJECT_MESSAGE,
)
from .types import (
    AssistantMessage,
    ContentBlock,
    ContentBlockType,
    HookResultMessage,
    Message,
    ProgressMessage,
    SystemMessage,
    SystemMessageSubtype,
    TombstoneMessage,
    ToolUseSummaryMessage,
    UserMessage,
)


def create_uuid() -> str:
    """Create a new UUID string."""
    return str(uuid.uuid4())


def create_timestamp() -> str:
    """Create an ISO timestamp string."""
    return datetime.utcnow().isoformat() + "Z"


def create_user_message(
    content: str | list[ContentBlock],
    *,
    uuid: str | None = None,
    timestamp: str | None = None,
    is_meta: bool = False,
    is_virtual: bool = False,
    is_compact_summary: bool = False,
    tool_use_result: str | None = None,
    origin: str | None = None,
) -> UserMessage:
    """
    Create a user message.

    Args:
        content: Message content (text or content blocks)
        uuid: Optional UUID (generated if not provided)
        timestamp: Optional timestamp (generated if not provided)
        is_meta: Whether this is a meta message
        is_virtual: Whether this is a virtual message (not sent to API)
        is_compact_summary: Whether this is a compact summary
        tool_use_result: Tool use result identifier
        origin: Message origin
    """
    return UserMessage(
        uuid=uuid or create_uuid(),
        timestamp=timestamp or create_timestamp(),
        content=content,
        is_meta=is_meta,
        is_virtual=is_virtual,
        is_compact_summary=is_compact_summary,
        tool_use_result=tool_use_result,
        origin=origin,
    )


def create_assistant_message(
    content: list[ContentBlock] | None = None,
    *,
    uuid: str | None = None,
    timestamp: str | None = None,
    is_virtual: bool = False,
    error: str | None = None,
) -> AssistantMessage:
    """
    Create an assistant message.

    Args:
        content: Message content blocks
        uuid: Optional UUID (generated if not provided)
        timestamp: Optional timestamp (generated if not provided)
        is_virtual: Whether this is a virtual message
        error: Error type if this is an error message
    """
    return AssistantMessage(
        uuid=uuid or create_uuid(),
        timestamp=timestamp or create_timestamp(),
        content=content,
        is_virtual=is_virtual,
        error=error,
    )


def create_system_message(
    content: str,
    subtype: SystemMessageSubtype | None = None,
    *,
    level: str | None = None,
    uuid: str | None = None,
    timestamp: str | None = None,
) -> SystemMessage:
    """
    Create a system message.

    Args:
        content: Message content
        subtype: System message subtype
        level: Message level
        uuid: Optional UUID
        timestamp: Optional timestamp
    """
    return SystemMessage(
        uuid=uuid or create_uuid(),
        timestamp=timestamp or create_timestamp(),
        subtype=subtype,
        level=level,
        content=content,
    )


def create_progress_message(
    tool_use_id: str,
    data: dict[str, Any],
    *,
    parent_tool_use_id: str | None = None,
    uuid: str | None = None,
    timestamp: str | None = None,
) -> ProgressMessage:
    """
    Create a progress message for streaming tool updates.

    Args:
        tool_use_id: The tool use ID this progress belongs to
        data: Progress data
        parent_tool_use_id: Parent tool use ID if nested
        uuid: Optional UUID
        timestamp: Optional timestamp
    """
    return ProgressMessage(
        uuid=uuid or create_uuid(),
        timestamp=timestamp or create_timestamp(),
        progress={
            "tool_use_id": tool_use_id,
            "parent_tool_use_id": parent_tool_use_id,
            "data": data,
        },
    )


def create_user_interruption_message(
    tool_use_id: str | None = None,
) -> UserMessage:
    """
    Create a user interruption message.

    Args:
        tool_use_id: Optional tool use ID being interrupted
    """
    content = INTERRUPT_MESSAGE if not tool_use_id else INTERRUPT_MESSAGE
    msg = create_user_message(content)
    if tool_use_id:
        msg.tool_use_result = tool_use_id
    return msg


def create_rejection_message(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
) -> UserMessage:
    """
    Create a tool use rejection message.

    Args:
        tool_name: Name of the rejected tool
        tool_input: Tool input that was rejected
    """
    msg = create_user_message(REJECT_MESSAGE)
    msg.tool_use_result = f"rejected:{tool_name}"
    return msg


def create_subagent_rejection_message(
    tool_name: str,
) -> UserMessage:
    """
    Create a subagent permission denial message.

    Args:
        tool_name: Name of the tool
    """
    msg = create_user_message(SUBAGENT_REJECT_MESSAGE)
    msg.tool_use_result = f"subagent_denied:{tool_name}"
    return msg


def create_cancellation_message(
    tool_use_id: str,
) -> UserMessage:
    """
    Create a tool use cancellation message.

    Args:
        tool_use_id: ID of the cancelled tool use
    """
    msg = create_user_message(CANCEL_MESSAGE)
    msg.tool_use_result = f"cancelled:{tool_use_id}"
    return msg


def create_tool_use_summary_message(
    summary: str,
    preceding_tool_use_ids: list[str],
    *,
    uuid: str | None = None,
    timestamp: str | None = None,
) -> ToolUseSummaryMessage:
    """
    Create a tool use summary message.

    Args:
        summary: Summary text
        preceding_tool_use_ids: IDs of preceding tool uses
        uuid: Optional UUID
        timestamp: Optional timestamp
    """
    return ToolUseSummaryMessage(
        uuid=uuid or create_uuid(),
        timestamp=timestamp or create_timestamp(),
        summary=summary,
        preceding_tool_use_ids=preceding_tool_use_ids,
    )


def create_hook_result_message(
    hook_id: str,
    hook_name: str,
    hook_event: str,
    result: Any,
    *,
    uuid: str | None = None,
    timestamp: str | None = None,
) -> HookResultMessage:
    """
    Create a hook result message.

    Args:
        hook_id: Hook ID
        hook_name: Hook name
        hook_event: Hook event name
        result: Hook result
        uuid: Optional UUID
        timestamp: Optional timestamp
    """
    return HookResultMessage(
        uuid=uuid or create_uuid(),
        timestamp=timestamp or create_timestamp(),
        hook_id=hook_id,
        hook_name=hook_name,
        hook_event=hook_event,
        result=result,
    )


def create_tombstone_message(
    original_uuid: str,
    content: str | None = None,
    *,
    timestamp: str | None = None,
) -> TombstoneMessage:
    """
    Create a tombstone message for deleted content.

    Args:
        original_uuid: UUID of the original message
        content: Optional content to preserve
        timestamp: Optional timestamp
    """
    return TombstoneMessage(
        uuid=create_uuid(),
        timestamp=timestamp or create_timestamp(),
        content=content,
    )


def create_permission_retry_message(
    commands: list[str],
) -> SystemMessage:
    """
    Create a permission retry system message.

    Args:
        commands: Commands that need permission
    """
    return create_system_message(
        content=f"Permission required for: {', '.join(commands)}",
        subtype="permission_retry",
    )


def create_stop_hook_summary_message(
    hook_name: str,
    tool_uses: int,
    duration_ms: float,
) -> SystemMessage:
    """
    Create a stop hook summary message.

    Args:
        hook_name: Name of the stop hook
        tool_uses: Number of tool uses in the turn
        duration_ms: Duration in milliseconds
    """
    return create_system_message(
        content=f"Stop hook '{hook_name}' completed: {tool_uses} tool uses in {duration_ms:.0f}ms",
        subtype="stop_hook_summary",
    )


def create_turn_duration_message(
    duration_ms: float,
    budget: int | None = None,
    message_count: int | None = None,
) -> SystemMessage:
    """
    Create a turn duration message.

    Args:
        duration_ms: Turn duration in milliseconds
        budget: Optional token budget
        message_count: Optional message count
    """
    content = f"Turn completed in {duration_ms:.0f}ms"
    if budget:
        content += f" (budget: {budget} tokens)"
    if message_count is not None:
        content += f" - {message_count} messages"
    return create_system_message(content, subtype="turn_duration")


def create_compact_boundary_message(
    trigger: str,
    pre_tokens: int,
    preserved_segment: dict[str, Any] | None = None,
) -> SystemMessage:
    """
    Create a compact boundary system message.

    Args:
        trigger: Compact trigger type
        pre_tokens: Tokens before compaction
        preserved_segment: Preserved segment info
    """
    return create_system_message(
        content=f"Compaction boundary (trigger: {trigger}, pre_tokens: {pre_tokens})",
        subtype="compact_boundary",
    )
