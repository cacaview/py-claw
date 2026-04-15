"""
Snip compact - lightweight context truncation based on message boundaries.

This is a lightweight compaction strategy that removes older messages
while preserving the structure of recent conversation turns. Unlike
full summarization-based compaction, snip compact works by finding
appropriate message boundaries and trimming the conversation.
"""
from __future__ import annotations

from typing import Any


def snip_compact_if_needed(
    messages: list[Any],
    options: dict[str, Any] | None = None,
) -> tuple[list[Any], bool]:
    """Check if snip compaction should run and perform it if needed.

    Snip compaction is a lightweight truncation strategy that removes
    older messages at natural boundary points (user message starts)
    to reduce context length without full summarization.

    Args:
        messages: Current conversation messages
        options: Optional snip options (target_tokens, etc.)

    Returns:
        Tuple of (potentially modified messages, whether changes were made)
    """
    if options is None:
        options = {}

    target_tokens = options.get("target_tokens")
    if target_tokens is None:
        return messages, False

    # Find natural boundary points (user message starts)
    boundaries = _find_snip_boundaries(messages)
    if not boundaries:
        return messages, False

    # Try removing from oldest boundaries until we're under target
    result_messages = list(messages)
    for boundary_idx in reversed(boundaries):
        if _estimate_tokens(result_messages) <= target_tokens:
            break
        # Remove messages from start to this boundary
        result_messages = result_messages[boundary_idx:]

    changed = len(result_messages) != len(messages)
    return result_messages, changed


def _find_snip_boundaries(messages: list[Any]) -> list[int]:
    """Find natural boundary indices where we can snip.

    Returns indices where a new user turn begins - these are safe
    points to truncate the conversation without breaking message pairs.
    """
    boundaries = []
    last_was_user = False

    for i, msg in enumerate(messages):
        msg_type = getattr(msg, "type", None)
        is_user = msg_type == "user"

        # A new user turn starts after an assistant message
        if is_user and last_was_user is False and boundaries:
            boundaries.append(i)
        elif is_user:
            boundaries.append(i)

        last_was_user = is_user

    return boundaries


def _estimate_tokens(messages: list[Any]) -> int:
    """Estimate token count for messages (rough approximation)."""
    total = 0
    for msg in messages:
        content = getattr(msg, "content", None)
        if content is None:
            continue
        if isinstance(content, str):
            # Rough estimate: 4 chars per token
            total += len(content) // 4
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                elif hasattr(block, "text"):
                    text = block.text
                else:
                    text = str(block)
                total += len(text) // 4
    return total


def is_snip_boundary_message(msg: Any) -> bool:
    """Check if a message is a safe snip boundary.

    A boundary message is one where truncation won't break
    tool_use/tool_result pairs or other structured content.
    """
    msg_type = getattr(msg, "type", None)
    if msg_type != "user":
        return False

    content = getattr(msg, "content", None)
    if content is None:
        return True

    # If content is just text, it's a safe boundary
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                # tool_use blocks mean NOT a boundary (would orphan tool_result)
                if block.get("type") == "tool_use":
                    return False
            elif hasattr(block, "type"):
                if getattr(block, "type", None) == "tool_use":
                    return False
    return True
