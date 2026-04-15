"""
Context Collapse service.

Collapses context windows while preserving key information using
importance scoring and summarization.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from py_claw.services.context_collapse.config import (
    get_context_collapse_config,
)

from .types import (
    CollapseStrategy,
    CollapsedChunk,
    CollapseResult,
    CollapseState,
    CollapseStatus,
    get_collapse_state,
)

if TYPE_CHECKING:
    from py_claw.services.api import AnthropicAPIClient


def _score_message_importance(message: dict[str, Any]) -> float:
    """Score a message by importance.

    Higher scores = more important to preserve.

    Returns a score between 0.0 and 1.0.
    """
    # Base score
    score = 0.5

    # Tool results are generally less important
    if message.get("type") == "tool_result":
        score -= 0.2

    # User messages are important
    if message.get("role") == "user":
        score += 0.2

    # Assistant reasoning is moderately important
    if message.get("type") == "thinking":
        score += 0.1

    # Error messages are important
    if message.get("type") == "error":
        score += 0.3

    # Decisions and conclusions are important
    content = str(message.get("content", "")).lower()
    if any(kw in content for kw in ["decided", "conclusion", "summary", "final", "important"]):
        score += 0.2

    return max(0.0, min(1.0, score))


def _estimate_tokens(text: str) -> int:
    """Rough token estimation."""
    return len(text) // 4


def should_collapse_context(
    messages: list[dict[str, Any]],
    token_count: int,
) -> tuple[bool, str]:
    """Determine if context should be collapsed.

    Args:
        messages: List of conversation messages
        token_count: Current token count

    Returns:
        Tuple of (should_collapse, reason)
    """
    config = get_context_collapse_config()

    if not config.enabled:
        return False, "disabled"

    state = get_collapse_state()

    # Circuit breaker
    if state.consecutive_failures >= 3:
        return False, "circuit_breaker"

    # Check minimum threshold
    if token_count < config.min_tokens:
        return False, f"min_tokens_not_met ({token_count}/{config.min_tokens})"

    return True, "threshold_met"


def collapse_context_by_boundary(
    messages: list[dict[str, Any]],
    preserve_recent: int = 5,
) -> tuple[list[dict[str, Any]], list[CollapsedChunk]]:
    """Collapse context at message boundaries.

    Preserves the most recent N messages and collapses older ones.
    """
    if len(messages) <= preserve_recent:
        return messages, []

    recent = messages[-preserve_recent:]
    older = messages[:-preserve_recent]

    # Create a collapsed chunk from older messages
    older_ids = [m.get("id", str(i)) for i, m in enumerate(older)]
    older_content = "\n".join(str(m.get("content", "")) for m in older)

    chunk = CollapsedChunk(
        id=str(uuid.uuid4())[:8],
        original_message_ids=older_ids,
        summary=f"[{len(older)} messages collapsed]",
        importance_score=0.5,
        token_count=_estimate_tokens(older_content),
    )

    return recent, [chunk]


def collapse_context_by_importance(
    messages: list[dict[str, Any]],
    target_tokens: int,
    threshold: float = 0.5,
) -> tuple[list[dict[str, Any]], list[CollapsedChunk]]:
    """Collapse context by importance scoring.

    Keeps messages above importance threshold and collapses others.
    """
    # Score all messages
    scored = []
    for i, msg in enumerate(messages):
        score = _score_message_importance(msg)
        scored.append((i, msg, score))

    # Sort by importance descending
    scored.sort(key=lambda x: x[2], reverse=True)

    # Select messages to preserve
    preserved: list[tuple[int, dict[str, Any]]] = []
    collapsed_ids: list[str] = []
    total_tokens = 0

    for i, msg, score in scored:
        msg_tokens = _estimate_tokens(str(msg.get("content", "")))
        if total_tokens + msg_tokens <= target_tokens and score >= threshold:
            preserved.append((i, msg))
            total_tokens += msg_tokens
        else:
            collapsed_ids.append(msg.get("id", str(i)))

    # Sort preserved by original index to maintain order
    preserved.sort(key=lambda x: x[0])
    preserved_messages = [msg for _, msg in preserved]

    # Create collapsed chunk
    chunks: list[CollapsedChunk] = []
    if collapsed_ids:
        collapsed_content = "\n".join(
            str(m.get("content", "")) for _, m in scored if m.get("id", "") in collapsed_ids or str(scored.index((0, m, 0))) in collapsed_ids
        )
        chunks.append(CollapsedChunk(
            id=str(uuid.uuid4())[:8],
            original_message_ids=collapsed_ids,
            summary=f"[{len(collapsed_ids)} messages collapsed by importance]",
            importance_score=0.5,
            token_count=_estimate_tokens(collapsed_content),
        ))

    return preserved_messages, chunks


def collapse_context_hybrid(
    messages: list[dict[str, Any]],
    preserve_recent: int = 5,
    target_tokens: int = 4000,
    threshold: float = 0.5,
) -> tuple[list[dict[str, Any]], list[CollapsedChunk]]:
    """Collapse context using hybrid strategy.

    First preserves recent messages, then applies importance scoring
    to the rest to fit within target tokens.
    """
    if len(messages) <= preserve_recent:
        return messages, []

    # First pass: boundary-based preservation of recent messages
    recent = messages[-preserve_recent:]
    older = messages[:-preserve_recent]

    # Second pass: importance-based selection from older messages
    remaining_tokens = target_tokens - sum(
        _estimate_tokens(str(m.get("content", ""))) for m in recent
    )

    scored = [(i, msg, _score_message_importance(msg)) for i, msg in enumerate(older)]
    scored.sort(key=lambda x: x[2], reverse=True)

    preserved: list[dict[str, Any]] = list(recent)
    collapsed_ids: list[str] = []
    total_tokens = 0

    for i, msg, score in scored:
        msg_tokens = _estimate_tokens(str(msg.get("content", "")))
        if total_tokens + msg_tokens <= remaining_tokens and score >= threshold:
            preserved.append(msg)
            total_tokens += msg_tokens
        else:
            collapsed_ids.append(msg.get("id", str(i)))

    # Sort preserved by original index
    preserved_ids = set(m.get("id", str(i)) for i, m in enumerate(messages) if m not in collapsed_ids)
    preserved = [m for i, m in enumerate(messages) if m.get("id", str(i)) in preserved_ids]

    # Create chunk for collapsed messages
    chunks: list[CollapsedChunk] = []
    if collapsed_ids:
        collapsed_msgs = [m for i, m in enumerate(older) if m.get("id", str(i)) in collapsed_ids]
        collapsed_content = "\n".join(str(m.get("content", "")) for m in collapsed_msgs)
        chunks.append(CollapsedChunk(
            id=str(uuid.uuid4())[:8],
            original_message_ids=collapsed_ids,
            summary=f"[{len(collapsed_ids)} messages collapsed (hybrid)]",
            importance_score=0.5,
            token_count=_estimate_tokens(collapsed_content),
        ))

    return preserved, chunks


async def execute_context_collapse(
    messages: list[dict[str, Any]],
    token_count: int,
    api_client: AnthropicAPIClient | None = None,
) -> CollapseResult:
    """Execute context collapse operation.

    Args:
        messages: List of conversation messages
        token_count: Current token count
        api_client: Optional API client for summarization

    Returns:
        CollapseResult with collapsed messages and chunks
    """
    config = get_context_collapse_config()
    state = get_collapse_state()

    should, reason = should_collapse_context(messages, token_count)

    if not should:
        return CollapseResult(
            status=CollapseStatus.SKIPPED,
            original_token_count=token_count,
            collapsed_token_count=token_count,
            chunks=[],
            preserved_message_count=len(messages),
            collapsed_message_count=0,
            strategy_used=CollapseStrategy.HYBRID,
            message=f"Collapse skipped: {reason}",
        )

    # Select strategy
    if config.strategy == "boundary":
        collapsed_messages, chunks = collapse_context_by_boundary(
            messages, config.preserve_recent_messages
        )
    elif config.strategy == "importance":
        collapsed_messages, chunks = collapse_context_by_importance(
            messages, config.target_tokens, config.importance_threshold
        )
    else:  # hybrid
        collapsed_messages, chunks = collapse_context_hybrid(
            messages, config.preserve_recent_messages, config.target_tokens, config.importance_threshold
        )

    # Calculate new token count
    new_token_count = sum(
        _estimate_tokens(str(m.get("content", ""))) for m in collapsed_messages
    )

    # Apply summarization if enabled and api_client available
    if config.use_summarization and api_client and chunks:
        # Summarization would be applied here
        pass

    # Record successful collapse
    tokens_saved = token_count - new_token_count
    state.record_collapse(tokens_saved)

    return CollapseResult(
        status=CollapseStatus.COMPLETED,
        original_token_count=token_count,
        collapsed_token_count=new_token_count,
        chunks=chunks,
        preserved_message_count=len(collapsed_messages),
        collapsed_message_count=len(messages) - len(collapsed_messages),
        strategy_used=CollapseStrategy(config.strategy),
        message=f"Collapsed {len(messages) - len(collapsed_messages)} messages, saved ~{tokens_saved} tokens",
    )


def get_collapse_stats() -> dict[str, Any]:
    """Get context collapse statistics."""
    state = get_collapse_state()
    config = get_context_collapse_config()

    return {
        "enabled": config.enabled,
        "strategy": config.strategy,
        "total_collapses": state.total_collapses,
        "total_tokens_saved": state.total_tokens_saved,
        "consecutive_failures": state.consecutive_failures,
        "last_collapse_at": state.last_collapse_at.isoformat() if state.last_collapse_at else None,
    }
