"""
Reactive compaction - triggered after an API prompt-too-long error.

This is a "reactive" compaction that runs in response to an actual
PTL error, as opposed to auto-compact which runs proactively based
on token thresholds.
"""
from __future__ import annotations

from typing import Any

from py_claw.services.compact.types import CompactionResult, RecompactionInfo


async def run_reactive_compact(
    messages: list[Any],
    compact_conversation_fn: Any,
    tool_use_context: Any,
    cache_safe_params: Any,
    recompaction_info: RecompactionInfo | None = None,
) -> CompactionResult | None:
    """Run reactive compaction after a prompt-too-long error.

    This is called when the API returns a PTL error, and attempts
    to recover by compacting the conversation and retrying.

    Args:
        messages: Current conversation messages
        compact_conversation_fn: The compact function to call
        tool_use_context: Context for tool use (model, etc.)
        cache_safe_params: Cache-safe parameters for the API call
        recompaction_info: Optional recompaction tracking info

    Returns:
        CompactionResult if successful, None if compaction fails
    """
    if not messages or len(messages) < 2:
        return None

    try:
        result = await compact_conversation_fn(
            messages=messages,
            tool_use_context=tool_use_context,
            cache_safe_params=cache_safe_params,
            suppress_questions=True,
            custom_instructions=None,
            is_auto_compact=False,
            recompaction_info=recompaction_info,
        )
        return result
    except Exception:
        # If reactive compaction also fails, return None
        # The caller should handle the error appropriately
        return None
