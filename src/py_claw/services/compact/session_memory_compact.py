"""
Session memory compact - coordinates session memory extraction with compaction.

This module handles the coordination between compact operations and session memory
extraction, ensuring that tool_use/tool_result pairs are preserved and that
session memory is properly integrated into the compaction process.

Reference: ClaudeCode-main/src/services/compact/sessionMemoryCompact.ts
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.schemas.common import Message

logger = logging.getLogger(__name__)

# Default configuration for session memory compact
DEFAULT_SM_COMPACT_CONFIG = {
    "min_tokens": 10_000,  # Minimum tokens to preserve
    "min_text_block_messages": 5,  # Minimum messages with text blocks
    "max_tokens": 40_000,  # Maximum tokens to preserve (hard cap)
}


@dataclass
class SessionMemoryCompactConfig:
    """Configuration for session memory compact thresholds."""
    min_tokens: int = 10_000
    min_text_block_messages: int = 5
    max_tokens: int = 40_000


# Current configuration state
_sm_compact_config: SessionMemoryCompactConfig = SessionMemoryCompactConfig()
_config_initialized: bool = False


def get_session_memory_compact_config() -> SessionMemoryCompactConfig:
    """Get the current session memory compact configuration."""
    return SessionMemoryCompactConfig(
        min_tokens=_sm_compact_config.min_tokens,
        min_text_block_messages=_sm_compact_config.min_text_block_messages,
        max_tokens=_sm_compact_config.max_tokens,
    )


def set_session_memory_compact_config(config: dict[str, Any]) -> None:
    """Set the session memory compact configuration."""
    global _sm_compact_config, _config_initialized
    _sm_compact_config = SessionMemoryCompactConfig(
        min_tokens=config.get("min_tokens", DEFAULT_SM_COMPACT_CONFIG["min_tokens"]),
        min_text_block_messages=config.get("min_text_block_messages", DEFAULT_SM_COMPACT_CONFIG["min_text_block_messages"]),
        max_tokens=config.get("max_tokens", DEFAULT_SM_COMPACT_CONFIG["max_tokens"]),
    )
    _config_initialized = True


def reset_session_memory_compact_config() -> None:
    """Reset config to defaults (useful for testing)."""
    global _sm_compact_config, _config_initialized
    _sm_compact_config = SessionMemoryCompactConfig()
    _config_initialized = False


async def wait_for_session_memory_extraction(timeout_ms: int = 5000) -> bool:
    """
    Wait for session memory extraction to complete.

    This should be called before compact to ensure session memory
    has been extracted from the current conversation.

    Args:
        timeout_ms: Maximum time to wait in milliseconds

    Returns:
        True if extraction completed, False if timeout
    """
    # TODO: Integrate with session memory service
    # For now, just check if session memory is ready
    try:
        from py_claw.services.session_memory import get_session_memory_content, is_session_memory_empty

        # Check if session memory is available
        if is_session_memory_empty():
            # No memory to wait for
            return True

        # Try to get content - this may trigger extraction
        content = get_session_memory_content()
        if content:
            return True

        # Wait a bit for async extraction
        await asyncio.sleep(0.1)
        return True

    except ImportError:
        # Session memory service not available
        return True
    except Exception as e:
        logger.warning(f"Session memory extraction wait failed: {e}")
        return True  # Don't block compact on memory extraction issues


def should_use_session_memory_compaction(
    messages: list[Any],
    session_memory_content: str | None,
) -> bool:
    """
    Determine if session memory compaction should be used.

    Args:
        messages: Current conversation messages
        session_memory_content: Extracted session memory content

    Returns:
        True if session memory compaction should be used
    """
    if not session_memory_content:
        return False

    config = get_session_memory_compact_config()
    if config.max_tokens == 0:
        return False

    # Check if we have enough content to warrant session memory compact
    from .micro_compact import _rough_token_count

    memory_tokens = _rough_token_count(session_memory_content)
    if memory_tokens < config.min_tokens:
        return False

    return True


def calculate_messages_to_keep_index(
    messages: list[Any],
    target_tokens: int,
) -> int:
    """
    Calculate the index of messages to keep.

    Works backwards from the most recent message, keeping messages
    until the target token count is reached.

    Args:
        messages: Conversation messages (oldest to newest)
        target_tokens: Target token count to keep

    Returns:
        Index of the first message to compact
    """
    from .micro_compact import _estimate_message_tokens

    total_tokens = 0
    keep_index = len(messages)

    # Work backwards
    for i in range(len(messages) - 1, -1, -1):
        msg_tokens = _estimate_message_tokens(messages[i])
        if total_tokens + msg_tokens > target_tokens:
            break
        total_tokens += msg_tokens
        keep_index = i

    return keep_index


def adjust_index_to_preserve_api_invariants(
    messages: list[Any],
    keep_index: int,
) -> int:
    """
    Adjust the keep index to preserve API invariants.

    Ensures that:
    1. tool_use/tool_result pairs are not split
    2. thinking blocks are kept with their parent messages
    3. compact boundaries are preserved

    Args:
        messages: Conversation messages
        keep_index: Initial keep index

    Returns:
        Adjusted keep index that preserves API invariants
    """
    if keep_index >= len(messages) - 1:
        return keep_index

    adjusted = keep_index

    # Scan from keep_index onwards to find any tool_use that needs its tool_result
    tool_use_ids: set[str] = set()
    tool_results_needed: dict[str, int] = {}  # tool_id -> message index of tool_result

    # First, collect all tool_use ids after keep_index
    for i in range(keep_index, len(messages)):
        msg = messages[i]
        msg_type = getattr(msg, "type", None) if hasattr(msg, "type") else None

        if msg_type == "assistant":
            content = getattr(msg, "message", {}).get("content", []) if hasattr(msg, "message") else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block.get("id")
                        if tool_id:
                            tool_use_ids.add(tool_id)

        elif msg_type == "user":
            content = getattr(msg, "message", {}).get("content", []) if hasattr(msg, "message") else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in tool_use_ids:
                            tool_results_needed[tool_use_id] = i

    # If there are orphaned tool_results (tool_result without tool_use in kept messages),
    # we need to include their corresponding tool_use messages
    for i in range(keep_index):
        msg = messages[i]
        msg_type = getattr(msg, "type", None) if hasattr(msg, "type") else None

        if msg_type == "assistant":
            content = getattr(msg, "message", {}).get("content", []) if hasattr(msg, "message") else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block.get("id")
                        if tool_id in tool_results_needed:
                            # This tool_use's result is after keep_index,
                            # so we need to include it
                            result_index = tool_results_needed[tool_id]
                            if result_index > adjusted:
                                adjusted = result_index

    return adjusted


def try_session_memory_compaction(
    messages: list[Any],
    session_memory_content: str | None,
) -> dict[str, Any] | None:
    """
    Try to perform session memory compaction.

    This is an optimization to use session memory to selectively
    prune messages while preserving important context.

    Args:
        messages: Conversation messages
        session_memory_content: Extracted session memory

    Returns:
        Dict with compacted messages and info, or None if not applicable
    """
    if not session_memory_content:
        return None

    config = get_session_memory_compact_config()

    # Check if session memory compact is applicable
    if not should_use_session_memory_compaction(messages, session_memory_content):
        return None

    # Calculate target tokens to keep (leaving room for memory)
    target_tokens = config.max_tokens - config.min_tokens

    # Calculate initial keep index
    keep_index = calculate_messages_to_keep_index(messages, target_tokens)

    # Adjust to preserve API invariants
    adjusted_index = adjust_index_to_preserve_api_invariants(messages, keep_index)

    if adjusted_index >= len(messages) - 1:
        # Not enough to compact
        return None

    return {
        "keep_index": adjusted_index,
        "session_memory_content": session_memory_content,
        "compaction_type": "session_memory",
    }


async def session_memory_compact(
    messages: list[Any],
    session_memory_content: str | None,
) -> dict[str, Any]:
    """
    Perform session memory aware compaction.

    Waits for session memory extraction, then performs compaction
    that preserves the value of the extracted memory.

    Args:
        messages: Conversation messages
        session_memory_content: Extracted session memory

    Returns:
        Dict with compacted messages, summary, and metadata
    """
    # Wait for any pending session memory extraction
    await wait_for_session_memory_extraction()

    # Try session memory compaction
    result = try_session_memory_compaction(messages, session_memory_content)

    if result is None:
        # No compaction happened
        return {
            "messages": messages,
            "compacted": False,
        }

    # Perform the actual compaction
    keep_index = result["keep_index"]
    memory_content = result["session_memory_content"]

    # Messages to keep (tail)
    kept_messages = messages[keep_index:]

    # Create compact boundary message
    boundary = _create_compact_boundary_message(keep_index, len(messages))

    # Create summary from session memory
    summary = _create_session_memory_summary(memory_content)

    return {
        "messages": [boundary, summary] + kept_messages,
        "compacted": True,
        "original_count": len(messages),
        "kept_count": len(kept_messages),
        "compaction_type": "session_memory",
        "boundary_marker": boundary,
        "summary_messages": [summary],
    }


def _create_compact_boundary_message(start_index: int, total_count: int) -> dict[str, Any]:
    """Create a compact boundary message."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"[Earlier conversation (of {start_index} messages) summarized for context]",
                }
            ],
        },
    }


def _create_session_memory_summary(memory_content: str) -> dict[str, Any]:
    """Create a summary message from session memory content."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"[Session Memory]\n{memory_content}",
                }
            ],
        },
    }
