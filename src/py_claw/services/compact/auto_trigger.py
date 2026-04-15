"""
Auto-compaction trigger logic.

Determines when to automatically trigger compaction
based on context window usage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import get_compact_config, CompactConfig
from .types import AutoCompactTrackingState, CompactThresholdInfo, CompactTriggerReason

# Stop trying auto-compact after this many consecutive failures.
# Without this, sessions where context is irrecoverably over the limit
# hammer the API with doomed compaction attempts on every turn.
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3

# Token buffers for threshold zones
AUTOCOMPACT_BUFFER_TOKENS = 13_000
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
ERROR_THRESHOLD_BUFFER_TOKENS = 20_000
MANUAL_COMPACT_BUFFER_TOKENS = 3_000

# Default effective context windows by model
DEFAULT_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
}

# Known model context windows (tokens)
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
}


@dataclass
class AutoCompactThresholdResult:
    """Result of computing auto-compact threshold."""

    #: Whether auto-compact should trigger.
    should_trigger: bool

    #: Reason for the decision.
    reason: CompactTriggerReason | None

    #: Detailed threshold information.
    threshold_info: CompactThresholdInfo | None


def compute_effective_threshold(
    model: str,
    context_window: int | None = None,
    config: CompactConfig | None = None,
) -> CompactThresholdInfo:
    """Compute the effective auto-compact threshold.

    The effective threshold is context_window - compact_token_reserve.
    Compaction triggers when usage approaches this threshold.

    Args:
        model: Model name
        context_window: Optional explicit context window size
        config: Optional compact configuration

    Returns:
        CompactThresholdInfo with threshold details
    """
    if config is None:
        config = get_compact_config()

    # Determine context window
    if context_window is None:
        context_window = MODEL_CONTEXT_WINDOWS.get(
            model,
            DEFAULT_CONTEXT_WINDOWS.get(model, 200_000),
        )

    effective_threshold = context_window - config.compact_token_reserve

    return CompactThresholdInfo(
        effective_threshold=effective_threshold,
        context_window=context_window,
        reserve=config.compact_token_reserve,
        auto_compact_enabled=True,
        blocking_enabled=True,
    )


def should_auto_compact(
    current_token_count: int,
    model: str,
    context_window: int | None = None,
) -> AutoCompactThresholdResult:
    """Determine if auto-compaction should be triggered.

    Args:
        current_token_count: Current token usage
        model: Model name
        context_window: Optional explicit context window size

    Returns:
        AutoCompactThresholdResult with decision and details
    """
    threshold_info = compute_effective_threshold(model, context_window)

    # Check if we're in the warning zone (80-100% of threshold)
    warning_threshold = int(threshold_info.effective_threshold * 0.8)
    error_threshold = int(threshold_info.effective_threshold * 0.95)

    if current_token_count >= threshold_info.effective_threshold:
        return AutoCompactThresholdResult(
            should_trigger=True,
            reason=CompactTriggerReason(
                type="auto",
                description="Token count exceeded effective threshold",
            ),
            threshold_info=threshold_info,
        )
    elif current_token_count >= error_threshold:
        return AutoCompactThresholdResult(
            should_trigger=False,
            reason=CompactTriggerReason(
                type="error",
                description="Token count in error zone - manual compact recommended",
            ),
            threshold_info=threshold_info,
        )
    elif current_token_count >= warning_threshold:
        return AutoCompactThresholdResult(
            should_trigger=False,
            reason=CompactTriggerReason(
                type="warning",
                description="Token count in warning zone - consider compacting",
            ),
            threshold_info=threshold_info,
        )
    else:
        return AutoCompactThresholdResult(
            should_trigger=False,
            reason=None,
            threshold_info=threshold_info,
        )


def get_compact_levels(
    current_token_count: int,
    model: str,
    context_window: int | None = None,
) -> dict[str, Any]:
    """Get different compact threshold levels for UI feedback.

    Returns warning, error, and blocking thresholds for UI display.
    """
    threshold_info = compute_effective_threshold(model, context_window)

    warning_threshold = int(threshold_info.effective_threshold * 0.8)
    error_threshold = int(threshold_info.effective_threshold * 0.95)

    return {
        "warning_threshold": warning_threshold,
        "error_threshold": error_threshold,
        "blocking_threshold": threshold_info.effective_threshold,
        "current_tokens": current_token_count,
        "context_window": threshold_info.context_window,
        "percent_used": (
            (current_token_count / threshold_info.context_window * 100)
            if threshold_info.context_window > 0
            else 0
        ),
        "percent_of_effective": (
            (current_token_count / threshold_info.effective_threshold * 100)
            if threshold_info.effective_threshold > 0
            else 0
        ),
    }


async def auto_compact_if_needed(
    messages: list[Any],
    current_token_count: int,
    model: str,
    token_counter: Any,
    context_window: int | None = None,
    tracking: AutoCompactTrackingState | None = None,
) -> tuple[bool, AutoCompactThresholdResult, AutoCompactTrackingState | None]:
    """Check if auto-compaction should be triggered.

    Implements circuit breaker: stops retrying after MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES
    consecutive failures. Without this, sessions where context is irrecoverably over
    the limit would hammer the API with doomed compaction attempts on every turn.

    Args:
        messages: Current conversation messages
        current_token_count: Current token usage
        model: Model name
        token_counter: Function to count tokens
        context_window: Optional explicit context window
        tracking: Optional auto-compact tracking state with consecutive failure count

    Returns:
        Tuple of (should_compact, result, updated_tracking)
    """
    # Circuit breaker: skip if we've had too many consecutive failures
    if tracking is not None and tracking.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        result = should_auto_compact(current_token_count, model, context_window)
        return False, result, tracking

    result = should_auto_compact(current_token_count, model, context_window)

    if result.should_trigger:
        # Additional check: make sure there's enough to compact
        groups = _group_messages_by_api_round_simple(messages)
        if len(groups) < 2:
            return False, result, tracking

        # Check if we have enough tokens to make compaction worthwhile
        oldest_group_tokens = token_counter(groups[0]) if groups else 0
        if oldest_group_tokens < 1000:  # Less than 1K tokens in oldest group
            return False, result, tracking

    return result.should_trigger, result, tracking


def record_compact_success(tracking: AutoCompactTrackingState | None) -> AutoCompactTrackingState | None:
    """Record a successful compaction and reset failure count.

    Call this after a successful compaction to reset the circuit breaker.
    """
    if tracking is None:
        return None
    tracking.compacted = True
    tracking.consecutive_failures = 0
    tracking.turn_counter += 1
    return tracking


def record_compact_failure(tracking: AutoCompactTrackingState | None) -> AutoCompactTrackingState | None:
    """Record a failed compaction attempt.

    Call this after a failed compaction to increment the failure counter.
    Returns the updated tracking state (may be None if circuit breaker was tripped).
    """
    if tracking is None:
        return AutoCompactTrackingState(consecutive_failures=1)
    tracking.consecutive_failures += 1
    return tracking


def is_circuit_breaker_tripped(tracking: AutoCompactTrackingState | None) -> bool:
    """Check if the auto-compact circuit breaker has tripped.

    When the circuit breaker trips, auto-compact is skipped for the rest of the session.
    """
    if tracking is None:
        return False
    return tracking.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES


def _group_messages_by_api_round_simple(messages: list[Any]) -> list[list[Any]]:
    """Simple message grouping by assistant message boundaries.

    This is a simplified version that doesn't track full message objects.
    """
    groups: list[list[Any]] = []
    current: list[Any] = []
    last_was_assistant = False

    for msg in messages:
        is_assistant = getattr(msg, "type", None) == "assistant"
        if is_assistant and last_was_assistant and current:
            groups.append(current)
            current = []
        current.append(msg)
        last_was_assistant = is_assistant

    if current:
        groups.append(current)

    return groups
