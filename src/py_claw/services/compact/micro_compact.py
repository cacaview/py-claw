"""
Time-based micro-compaction for tool results.

Clears old tool results when the server-side prompt cache has likely expired,
reducing the amount of content that needs to be rewritten on each API call.

Reference: ClaudeCode-main/src/services/compact/microCompact.ts
Reference: ClaudeCode-main/src/services/compact/timeBasedMCConfig.ts
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.schemas.common import Message

# Inline message for cleared tool results
TIME_BASED_MC_CLEARED_MESSAGE = "[Old tool result content cleared]"

# Token size estimate for images/documents
IMAGE_MAX_TOKEN_SIZE = 2000

# Tools that are eligible for micro-compaction
COMPACTABLE_TOOLS: set[str] = {
    "Bash",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
}


@dataclass
class TimeBasedMCConfig:
    """Configuration for time-based micro-compaction."""

    #: Master switch. When false, time-based micro-compaction is a no-op.
    enabled: bool = False

    #: Trigger when (now - last assistant timestamp) exceeds this many minutes.
    #: 60 is the safe choice: the server's 1h cache TTL is guaranteed expired.
    gap_threshold_minutes: int = 60

    #: Keep this many most-recent compactable tool results.
    #: Older results are cleared.
    keep_recent: int = 5


def get_time_based_mc_config() -> TimeBasedMCConfig:
    """Get the time-based micro-compact configuration.

    Currently returns defaults. In a full implementation, this would
    integrate with GrowthBook or similar feature flag system.
    """
    return TimeBasedMCConfig(
        enabled=True,  # Enable by default for now
        gap_threshold_minutes=60,
        keep_recent=5,
    )


def _calculate_tool_result_tokens(block: dict[str, Any]) -> int:
    """Calculate token count for a tool_result block."""
    content = block.get("content", "")
    if isinstance(content, str):
        return _rough_token_count(content)

    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "text":
                    total += _rough_token_count(item.get("text", ""))
                elif item_type in ("image", "document"):
                    total += IMAGE_MAX_TOKEN_SIZE
        return total

    return 0


def _rough_token_count(text: str) -> int:
    """Rough token count estimation (chars / 4)."""
    return len(text) // 4


def _estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate token count for a single message.

    Handles content blocks including text, tool_result, tool_use, thinking, etc.
    """
    total_tokens = 0

    # Handle both dict and object-style messages
    if isinstance(message, dict):
        msg_type = message.get("type", None)
        content = message.get("message", {}).get("content", [])
    else:
        msg_type = getattr(message, "type", None)
        content = getattr(message, "message", {}).get("content", [])

    if msg_type not in ("user", "assistant"):
        return 0

    if isinstance(content, str):
        return _rough_token_count(content)

    if not isinstance(content, list):
        return 0

    for block in content:
        if isinstance(block, dict):
            block_type = block.get("type")
        else:
            block_type = getattr(block, "type", None)

        if block_type == "text":
            text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            total_tokens += _rough_token_count(text)
        elif block_type == "tool_result":
            total_tokens += _calculate_tool_result_tokens(block)
        elif block_type in ("image", "document"):
            total_tokens += IMAGE_MAX_TOKEN_SIZE
        elif block_type == "thinking":
            # Count only the thinking text
            thinking = block.get("thinking", "") if isinstance(block, dict) else getattr(block, "thinking", "")
            total_tokens += _rough_token_count(thinking)
        elif block_type == "tool_use":
            # Count name + input
            name = block.get("name", "") if isinstance(block, dict) else getattr(block, "name", "")
            input_json = block.get("input", {}) if isinstance(block, dict) else getattr(block, "input", {})
            import json
            total_tokens += _rough_token_count(name + json.dumps(input_json))
        else:
            # server_tool_use, web_search_tool_result, etc.
            import json
            total_tokens += _rough_token_count(json.dumps(block))

    return total_tokens


def _collect_compactable_tool_results(messages: list[Any]) -> list[tuple[int, str, dict[str, Any]]]:
    """Collect tool_result blocks from compactable tools.

    Returns list of (message_index, tool_use_id, tool_result_block) tuples
    in encounter order.
    """
    results: list[tuple[int, str, dict[str, Any]]] = []
    tool_use_ids: set[str] = set()

    for msg_idx, msg in enumerate(messages):
        msg_type = getattr(msg, "type", None)

        if msg_type == "assistant":
            content = getattr(msg, "message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        if tool_name in COMPACTABLE_TOOLS:
                            tool_id = block.get("id", "")
                            if tool_id:
                                tool_use_ids.add(tool_id)

        elif msg_type == "user":
            content = getattr(msg, "message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")
                        if tool_use_id in tool_use_ids:
                            results.append((msg_idx, tool_use_id, block))

    return results


def _get_last_assistant_timestamp(messages: list[Any]) -> float | None:
    """Get the timestamp of the last assistant message.

    Looks for __cas_context_timestamp metadata on messages.
    Returns None if no timestamp found.
    """
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "assistant":
            # Check for timestamp metadata
            if hasattr(msg, "__cas_context_timestamp"):
                return getattr(msg, "__cas_context_timestamp")
            # Check in message dict
            msg_dict = dict(msg) if not isinstance(msg, dict) else msg
            ts = msg_dict.get("__cas_context_timestamp")
            if ts is not None:
                return float(ts)
    return None


def _clear_tool_results(
    messages: list[Any],
    tool_use_ids_to_clear: set[str],
) -> list[Any]:
    """Create new messages with specified tool results cleared.

    Replaces tool_result content with a placeholder message.
    """
    result: list[Any] = []

    for msg in messages:
        msg_type = getattr(msg, "type", None)

        if msg_type == "user":
            # Check if this message has tool_results to clear
            # Handle both dict and object-style messages
            if isinstance(msg, dict):
                msg_dict = dict(msg)
                content = msg_dict.get("message", {}).get("content", [])
            else:
                msg_dict = {}
                msg_dict["type"] = getattr(msg, "type", None)
                msg_dict["id"] = getattr(msg, "id", None)
                msg_dict["message"] = dict(getattr(msg, "message", {}))
                content = msg_dict["message"].get("content", [])

            if isinstance(content, list):
                new_content: list[Any] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")
                        if tool_use_id in tool_use_ids_to_clear:
                            # Replace with cleared message
                            new_content.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": TIME_BASED_MC_CLEARED_MESSAGE,
                            })
                        else:
                            new_content.append(block)
                    else:
                        new_content.append(block)

                # Create new message with cleared content
                if isinstance(msg, dict):
                    new_msg = dict(msg)
                    if "message" in new_msg:
                        new_msg["message"] = dict(new_msg["message"])
                        new_msg["message"]["content"] = new_content
                else:
                    new_msg = {
                        "type": getattr(msg, "type", None),
                        "id": getattr(msg, "id", None),
                        "message": {
                            "role": getattr(msg, "message", {}).get("role", None),
                            "content": new_content,
                        },
                    }
                result.append(new_msg)
            else:
                result.append(msg)
        else:
            result.append(msg)

    return result


def maybe_time_based_microcompact(
    messages: list[Any],
    config: TimeBasedMCConfig | None = None,
) -> dict[str, Any] | None:
    """Check if time-based micro-compaction should run.

    Returns a dict with microcompact result if triggered, None otherwise.

    Time-based micro-compaction fires when:
    1. Config is enabled
    2. The gap since the last assistant message exceeds gap_threshold_minutes

    When triggered, it clears old tool results before the API call because
    the server-side prompt cache has likely expired.
    """
    if config is None:
        config = get_time_based_mc_config()

    if not config.enabled:
        return None

    # Get last assistant timestamp
    last_ts = _get_last_assistant_timestamp(messages)
    if last_ts is None:
        return None

    # Calculate time gap in minutes
    current_time = time.time()
    gap_minutes = (current_time - last_ts) / 60.0

    if gap_minutes < config.gap_threshold_minutes:
        return None

    # Collect compactable tool results
    tool_results = _collect_compactable_tool_results(messages)
    if len(tool_results) <= config.keep_recent:
        return None

    # Keep only the most recent N tool results
    to_clear = tool_results[:-config.keep_recent]
    tool_use_ids_to_clear = {tool_id for _, tool_id, _ in to_clear}

    # Clear the old tool results
    cleared_messages = _clear_tool_results(messages, tool_use_ids_to_clear)

    return {
        "messages": cleared_messages,
        "compaction_info": {
            "type": "time_based",
            "gap_minutes": gap_minutes,
            "cleared_count": len(tool_use_ids_to_clear),
            "kept_count": config.keep_recent,
        },
    }


def microcompact_messages(
    messages: list[Any],
    config: TimeBasedMCConfig | None = None,
) -> dict[str, Any]:
    """Run micro-compaction on messages.

    Time-based micro-compaction clears old tool results when the
    server-side prompt cache has likely expired.

    Args:
        messages: Conversation messages
        config: Optional micro-compact configuration

    Returns:
        Dict with 'messages' (possibly compacted) and 'compaction_info' if compaction occurred
    """
    # Try time-based microcompact first
    time_based_result = maybe_time_based_microcompact(messages, config)
    if time_based_result is not None:
        return time_based_result

    # No compaction happened
    return {"messages": messages}


def reset_microcompact_state() -> None:
    """Reset any micro-compact state.

    Currently a no-op since we don't maintain persistent state,
    but included for API compatibility with TypeScript reference.
    """
    pass
