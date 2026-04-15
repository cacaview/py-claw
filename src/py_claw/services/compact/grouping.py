"""
Message grouping for compact operations.

Groups messages at API-round boundaries for truncation
at natural conversation boundaries.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.schemas.common import Message


def group_messages_by_api_round(messages: list[Any]) -> list[list[Any]]:
    """Group messages at API-round boundaries.

    One group per API round-trip. A boundary fires when a NEW
    assistant response begins (different message.id from the prior
    assistant).

    This is the key algorithm for ensuring PTL truncation happens at
    natural boundaries - the API contract guarantees every tool_use
    is resolved before the next assistant turn, so pairing validity
    falls out of the assistant-id boundary.

    Args:
        messages: List of conversation messages

    Returns:
        List of message groups, each representing one API round
    """
    groups: list[list[Any]] = []
    current: list[Any] = []
    last_assistant_id: str | None = None

    for msg in messages:
        # Check if this is a new assistant message with a different ID
        # If so and we have content, start a new group
        msg_id = getattr(msg, "id", None) or getattr(msg, "message", {}).get("id", None)

        is_new_assistant = (
            getattr(msg, "type", None) == "assistant"
            and msg_id != last_assistant_id
            and len(current) > 0
        )

        if is_new_assistant:
            groups.append(current)
            current = [msg]
        else:
            current.append(msg)

        if getattr(msg, "type", None) == "assistant":
            last_assistant_id = msg_id

    # Don't forget the last group
    if current:
        groups.append(current)

    return groups


def count_message_groups(messages: list[Any]) -> int:
    """Count the number of API round groups in messages."""
    return len(group_messages_by_api_round(messages))


def get_oldest_group_index(messages: list[Any]) -> int:
    """Get the index of the oldest non-empty group.

    Returns 0 if all groups should be kept (nothing to compact).
    """
    groups = group_messages_by_api_round(messages)
    if len(groups) <= 1:
        return 0
    # Keep at least one group
    return len(groups) - 1


def truncate_by_token_budget(
    messages: list[Any],
    max_tokens: int,
    token_counter: Any,
) -> list[Any]:
    """Truncate messages to fit within a token budget.

    Drops oldest message groups until the token count is within budget.

    Args:
        messages: List of messages to truncate
        max_tokens: Maximum tokens allowed
        token_counter: Function that estimates tokens for a list of messages

    Returns:
        Truncated message list
    """
    if not messages:
        return []

    groups = group_messages_by_api_round(messages)
    if len(groups) <= 1:
        return messages

    # Try dropping from the oldest
    for drop_count in range(1, len(groups)):
        kept_groups = groups[drop_count:]
        kept_messages = [msg for group in kept_groups for msg in group]
        token_count = token_counter(kept_messages)
        if token_count <= max_tokens:
            return kept_messages

    # If we can't truncate enough, return just the last group
    return groups[-1] if groups else []


def preserve_tool_result_pairs(messages: list[Any]) -> list[Any]:
    """Ensure tool_use and tool_result pairs are not separated.

    When truncating, we need to ensure that if a tool_use exists,
    its corresponding tool_result is also kept (or both are dropped).

    This is a safety check after truncation to fix any orphaned pairs.
    """
    tool_use_messages: dict[str, int] = {}
    tool_result_messages: dict[str, int] = {}

    for index, msg in enumerate(messages):
        msg_type = _message_value(msg, "type")
        message = _message_value(msg, "message", {})
        content = _message_value(message, "content", [])
        if msg_type == "assistant":
            for block in _iter_blocks(content):
                if _block_value(block, "type") == "tool_use":
                    tool_id = _block_value(block, "id")
                    if isinstance(tool_id, str) and tool_id:
                        tool_use_messages[tool_id] = index
        elif msg_type == "user":
            for block in _iter_blocks(content):
                if _block_value(block, "type") == "tool_result":
                    tool_id = _block_value(block, "tool_use_id")
                    if isinstance(tool_id, str) and tool_id:
                        tool_result_messages[tool_id] = index

    orphaned_message_indexes: set[int] = set()
    for tool_id, use_index in tool_use_messages.items():
        if tool_id not in tool_result_messages:
            orphaned_message_indexes.add(use_index)
    for tool_id, result_index in tool_result_messages.items():
        if tool_id not in tool_use_messages:
            orphaned_message_indexes.add(result_index)

    if not orphaned_message_indexes:
        return messages
    return [msg for index, msg in enumerate(messages) if index not in orphaned_message_indexes]



def _message_value(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)



def _block_value(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)



def _iter_blocks(content: Any) -> list[Any]:
    if isinstance(content, list):
        return content
    return []
