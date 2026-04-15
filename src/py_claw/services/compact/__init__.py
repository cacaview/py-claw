"""
Compact module for context window compression.

This module handles compressing long conversations when the context
approaches the model's window limit, summarizing older messages
instead of discarding them.
"""
from __future__ import annotations

from .config import (
    DEFAULT_COMPACT_CONFIG,
    CompactConfig,
    get_compact_config,
    set_compact_config,
)
from .types import (
    AutoCompactTrackingState,
    CompactionResult,
    RecompactionInfo,
)
from .grouping import group_messages_by_api_round, preserve_tool_result_pairs
from .compressor import (
    compact_conversation,
    strip_images_from_messages,
    truncate_head_for_ptl_retry,
    build_post_compact_messages,
)
from .auto_trigger import (
    auto_compact_if_needed,
    compute_effective_threshold,
    should_auto_compact,
    get_compact_levels,
    record_compact_success,
    record_compact_failure,
    is_circuit_breaker_tripped,
    MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES,
)
from .micro_compact import (
    TimeBasedMCConfig,
    get_time_based_mc_config,
    microcompact_messages,
    maybe_time_based_microcompact,
    reset_microcompact_state,
)
from .compact_warning import (
    get_compact_warning_suppressed,
    suppress_compact_warning,
    clear_compact_warning_suppression,
)
from .reactive_compact import run_reactive_compact
from .snip_compact import snip_compact_if_needed
from .session_memory_compact import (
    SessionMemoryCompactConfig,
    get_session_memory_compact_config,
    set_session_memory_compact_config,
    reset_session_memory_compact_config,
    wait_for_session_memory_extraction,
    should_use_session_memory_compaction,
    calculate_messages_to_keep_index,
    adjust_index_to_preserve_api_invariants,
    try_session_memory_compaction,
    session_memory_compact,
)

__all__ = [
    # Config
    "DEFAULT_COMPACT_CONFIG",
    "CompactConfig",
    "get_compact_config",
    "set_compact_config",
    # Types
    "AutoCompactTrackingState",
    "CompactionResult",
    "RecompactionInfo",
    # Grouping
    "group_messages_by_api_round",
    "preserve_tool_result_pairs",
    # Compressor
    "compact_conversation",
    "strip_images_from_messages",
    "truncate_head_for_ptl_retry",
    "build_post_compact_messages",
    # Auto trigger
    "auto_compact_if_needed",
    "compute_effective_threshold",
    "should_auto_compact",
    "get_compact_levels",
    "record_compact_success",
    "record_compact_failure",
    "is_circuit_breaker_tripped",
    "MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES",
    # Micro compact
    "TimeBasedMCConfig",
    "get_time_based_mc_config",
    "microcompact_messages",
    "maybe_time_based_microcompact",
    "reset_microcompact_state",
    # Compact warning
    "get_compact_warning_suppressed",
    "suppress_compact_warning",
    "clear_compact_warning_suppression",
    # Reactive compact
    "run_reactive_compact",
    # Snip compact
    "snip_compact_if_needed",
    # Session memory compact
    "SessionMemoryCompactConfig",
    "get_session_memory_compact_config",
    "set_session_memory_compact_config",
    "reset_session_memory_compact_config",
    "wait_for_session_memory_extraction",
    "should_use_session_memory_compaction",
    "calculate_messages_to_keep_index",
    "adjust_index_to_preserve_api_invariants",
    "try_session_memory_compaction",
    "session_memory_compact",
]
