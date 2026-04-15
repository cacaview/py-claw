"""
Core compression logic for compact subsystem.

Handles the main compaction flow including message
normalization, image stripping, and boundary creation.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from .types import (
    CompactionResult,
    ERROR_MESSAGE_NOT_ENOUGH_MESSAGES,
    ERROR_MESSAGE_INCOMPLETE_RESPONSE,
)
from .grouping import group_messages_by_api_round

if TYPE_CHECKING:
    from py_claw.services.api.types import Message

# PTL retry marker for truncating during PTL recovery
PTL_RETRY_MARKER = "[earlier conversation truncated for compaction retry]"


def strip_images_from_messages(messages: list[Any]) -> list[Any]:
    """Strip image blocks from messages before sending for compaction.

    Images are not needed for generating a conversation summary and can
    cause the compaction API call itself to hit the prompt-too-long limit.

    Replaces image blocks with a text marker so the summary still notes
    that an image was shared.

    Args:
        messages: List of conversation messages

    Returns:
        Messages with images replaced by [image] markers
    """
    result: list[Any] = []

    for msg in messages:
        msg_type = getattr(msg, "type", None)

        if msg_type != "user":
            result.append(msg)
            continue

        # Handle both dict and object-style messages
        msg_dict = dict(msg) if not isinstance(msg, dict) else msg
        message_obj = msg_dict.get("message", {})
        if isinstance(message_obj, dict):
            content = message_obj.get("content", [])
        else:
            content = getattr(message_obj, "content", [])

        if not isinstance(content, list):
            result.append(msg)
            continue

        new_content: list[Any] = []
        has_media = False

        for block in content:
            # Handle both dict and object-style blocks
            if isinstance(block, dict):
                block_type = block.get("type")
            else:
                block_type = getattr(block, "type", None)

            if block_type in ("image", "document"):
                has_media = True
                new_content.append({"type": "text", "text": f"[{block_type}]"})
            elif block_type == "tool_result":
                block_dict = dict(block) if not isinstance(block, dict) else block
                block_content = block_dict.get("content")
                if isinstance(block_content, list):
                    # Also strip images from tool_result content
                    new_tool_content: list[Any] = []
                    tool_has_media = False
                    for item in block_content:
                        if isinstance(item, dict):
                            item_type = item.get("type")
                        else:
                            item_type = getattr(item, "type", None)

                        if item_type in ("image", "document"):
                            tool_has_media = True
                            new_tool_content.append({"type": "text", "text": f"[{item_type}]"})
                        else:
                            new_tool_content.append(item)
                    if tool_has_media:
                        has_media = True
                        new_content.append({**block_dict, "content": new_tool_content})
                    else:
                        new_content.append(block)
                else:
                    new_content.append(block)
            else:
                new_content.append(block)

        if has_media:
            # Create a new message with stripped content
            new_msg = dict(msg) if not isinstance(msg, dict) else dict(msg)
            if "message" in new_msg and isinstance(new_msg["message"], dict):
                new_msg["message"] = dict(new_msg["message"])
                new_msg["message"]["content"] = new_content
            result.append(new_msg)
        else:
            result.append(msg)

    return result


def truncate_head_for_ptl_retry(
    messages: list[Any],
    ptl_response: Any,
    token_estimator: Any,
) -> list[Any] | None:
    """Drop oldest API-round groups to make room for PTL retry.

    This is the fallback escape hatch when the compact request itself
    hits prompt-too-long. Without this, the user would be stuck.

    Args:
        messages: Original message list
        ptl_response: The PTL error response
        token_estimator: Function to estimate tokens

    Returns:
        Truncated message list, or None if nothing can be dropped
    """
    # Strip any previous retry marker
    if messages and getattr(messages[0], "is_meta", False):
        first_content = getattr(messages[0], "message", {}).get("content", "")
        if first_content == PTL_RETRY_MARKER:
            messages = messages[1:]

    groups = group_messages_by_api_round(messages)
    if len(groups) < 2:
        return None

    # Calculate token gap from PTL response if available
    token_gap: int | None = None
    if hasattr(ptl_response, "error"):
        error = ptl_response.error
        if isinstance(error, dict):
            token_str = str(error.get("message", ""))
            # Try to extract token count from error message
            import re
            match = re.search(r"(\d+)\s*tokens?", token_str)
            if match:
                token_gap = int(match.group(1))

    if token_gap is not None:
        # Drop groups until we cover the gap
        acc = 0
        drop_count = 0
        for group in groups:
            acc += token_estimator(group)
            drop_count += 1
            if acc >= token_gap:
                break
    else:
        # Fallback: drop 20% of groups
        drop_count = max(1, len(groups) // 5)

    # Keep at least one group
    drop_count = min(drop_count, len(groups) - 1)
    if drop_count < 1:
        return None

    kept_messages = [msg for group in groups[drop_count:] for msg in group]

    # If the kept messages start with assistant, prepend a user marker
    # (API requires first message to be user role)
    if kept_messages and getattr(kept_messages[0], "type", None) == "assistant":
        marker_msg = {
            "type": "user",
            "is_meta": True,
            "message": {
                "role": "user",
                "content": PTL_RETRY_MARKER,
            },
        }
        kept_messages = [marker_msg] + kept_messages

    return kept_messages


def build_post_compact_messages(result: CompactionResult) -> list[Any]:
    """Build the final message list from a CompactionResult.

    Order: boundary marker, summary messages, messages to keep,
    attachments, hook results.

    Args:
        result: The compaction result

    Returns:
        Flattened message list for post-compaction state
    """
    messages: list[Any] = []

    # Boundary marker
    if result.boundary_marker:
        messages.append(result.boundary_marker)

    # Summary messages
    messages.extend(result.summary_messages)

    # Messages to keep
    if result.messages_to_keep:
        messages.extend(result.messages_to_keep)

    # Attachments
    messages.extend(result.attachments)

    # Hook results
    messages.extend(result.hook_results)

    return messages


async def compact_conversation(
    messages: list[Any],
    token_counter: Any,
    api_client: Any = None,
    suppress_follow_up_questions: bool = False,
    custom_instructions: str | None = None,
    is_auto_compact: bool = False,
) -> CompactionResult:
    """Compact a conversation by summarizing older messages.

    This is the main entry point for the compaction flow.
    It handles:
    1. Validating there's enough to compact
    2. Stripping images
    3. Determining what to keep
    4. Calling the API to summarize
    5. Building the result with boundary markers

    Args:
        messages: Conversation messages to compact
        token_counter: Function to count tokens in messages
        api_client: Optional API client for making the summary call
        suppress_follow_up_questions: Whether to suppress follow-up questions
        custom_instructions: Optional custom instructions for summarization
        is_auto_compact: Whether this is an automatic compaction

    Returns:
        CompactionResult with boundary marker and summary messages

    Raises:
        ValueError: If not enough messages to compact
    """
    if len(messages) == 0:
        raise ValueError(ERROR_MESSAGE_NOT_ENOUGH_MESSAGES)

    # Strip images before summarization
    stripped_messages = strip_images_from_messages(messages)

    # Group messages by API round to find natural truncation points
    groups = group_messages_by_api_round(stripped_messages)

    if len(groups) < 2:
        raise ValueError(ERROR_MESSAGE_NOT_ENOUGH_MESSAGES)

    # Determine what to keep vs summarize
    # Keep the most recent N groups (where N is determined by token budget)
    recent_groups = groups[-1:]  # Always keep at least the last group
    older_groups = groups[:-1]

    messages_to_keep = [msg for group in recent_groups for msg in group]
    messages_to_summarize = [msg for group in older_groups for msg in group]

    # Calculate token counts
    pre_compact_count = token_counter(messages)
    post_compact_count = token_counter(messages_to_keep)
    summarized_count = token_counter(messages_to_summarize)

    # Create boundary marker
    boundary_marker = {
        "type": "system",
        "subtype": "compact_boundary",
        "compact_metadata": {
            "preserved_segment": {
                "head_uuid": messages_to_keep[0].get("uuid") if messages_to_keep else None,
                "tail_uuid": messages_to_keep[-1].get("uuid") if messages_to_keep else None,
            },
            "summarized_count": len(messages_to_summarize),
            "summarized_tokens": summarized_count,
        },
    }

    # Generate summary via API if client is available
    summary_messages: list[Any] = []

    if api_client is not None:
        # Build summarization prompt
        summary_prompt = _build_summary_prompt(
            messages_to_summarize,
            messages_to_keep,
            custom_instructions,
        )
        try:
            summary_response = await api_client.create_message(
                messages=[{"role": "user", "content": summary_prompt}],
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
            )
            summary_text = summary_response.content[0].text
            summary_messages = [
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": summary_text,
                    },
                }
            ]
        except Exception:
            # If summarization fails, continue with empty summary
            summary_messages = []

    result = CompactionResult(
        boundary_marker=boundary_marker,
        summary_messages=summary_messages,
        messages_to_keep=messages_to_keep,
        pre_compact_token_count=pre_compact_count,
        post_compact_token_count=post_compact_count + (token_counter(summary_messages) if summary_messages else 0),
        true_post_compact_token_count=post_compact_count,
    )

    return result


def _build_summary_prompt(
    messages_to_summarize: list[Any],
    messages_to_keep: list[Any],
    custom_instructions: str | None = None,
) -> str:
    """Build the prompt for summarizing older messages.

    Args:
        messages_to_summarize: Messages to summarize
        messages_to_keep: Messages that will be kept after compaction
        custom_instructions: Optional custom instructions

    Returns:
        Prompt string for the summarization API
    """
    # Format the messages as a conversation string
    conversation_parts: list[str] = []

    for msg in messages_to_summarize:
        role = getattr(msg, "type", "unknown")
        content = _get_message_text(msg)
        conversation_parts.append(f"{role}: {content}")

    conversation = "\n\n".join(conversation_parts)

    # Build the prompt
    prompt = f"""Please summarize the following conversation concisely. Focus on:
- Key decisions made
- Important information discovered
- Current state of work
- Any errors encountered and how they were resolved

Keep the summary brief but informative - it will replace the original messages to save context space.

CONVERSATION TO SUMMARIZE:
{conversation}
"""

    if custom_instructions:
        prompt += f"\n\nADDITIONAL INSTRUCTIONS:\n{custom_instructions}"

    return prompt


def _get_message_text(message: Any) -> str:
    """Extract text content from a message."""
    content = getattr(message, "message", {}).get("content", "")
    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", ""))
        content = " ".join(text_parts)
    return str(content) if content else ""
