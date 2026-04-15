"""
AutoDream service.

Background memory consolidation service that triggers /dream prompt
for reflecting on session state and integrating learnings.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from py_claw.services.auto_dream.config import (
    DEFAULT_DREAM_PROMPT,
    get_auto_dream_config,
)

from .types import DreamResult, DreamState, DreamStatus, get_dream_state

if TYPE_CHECKING:
    from py_claw.services.api import AnthropicAPIClient


async def should_trigger_dream(
    messages_count: int,
    token_count: int,
) -> tuple[bool, str]:
    """Determine if auto dream should be triggered.

    Args:
        messages_count: Number of messages since last dream
        token_count: Token count since last dream

    Returns:
        Tuple of (should_trigger, reason)
    """
    config = get_auto_dream_config()

    if not config.enabled:
        return False, "disabled"

    state = get_dream_state()

    # Check consecutive failures (circuit breaker)
    if state.consecutive_failures >= 3:
        return False, "circuit_breaker"

    # Check minimum thresholds
    if messages_count < config.min_messages:
        return False, f"min_messages_not_met ({messages_count}/{config.min_messages})"

    if token_count < config.min_tokens:
        return False, f"min_tokens_not_met ({token_count}/{config.min_tokens})"

    return True, "thresholds_met"


async def trigger_dream(
    api_client: AnthropicAPIClient | None = None,
    prompt: str | None = None,
) -> DreamResult:
    """Trigger a dream operation.

    Args:
        api_client: Optional API client for dream generation
        prompt: Optional custom prompt (defaults to DEFAULT_DREAM_PROMPT)

    Returns:
        DreamResult with operation details
    """
    state = get_dream_state()
    config = get_auto_dream_config()

    if prompt is None:
        prompt = config.prompt_template or DEFAULT_DREAM_PROMPT

    start_time = time.time()

    try:
        if api_client is not None:
            # Use API client for dream generation
            from py_claw.services.api import MessageCreateParams, MessageParam

            response = api_client.create_message(
                MessageCreateParams(
                    model="claude-sonnet-4-20250514",
                    messages=[MessageParam(role="user", content=prompt)],
                    max_tokens=2048,
                )
            )

            if hasattr(response, "__await__"):
                response = await response

            tokens = getattr(response, "usage", {}).get("input_tokens", 0) if hasattr(response, "usage") else 0
        else:
            # No API client - just simulate dream
            tokens = len(prompt) // 4  # Rough token estimate

        duration = time.time() - start_time
        state.record_dream(duration, tokens)

        return DreamResult(
            status=DreamStatus.COMPLETED,
            message="Dream completed successfully",
            duration_seconds=duration,
            tokens_processed=tokens,
        )

    except Exception as e:
        duration = time.time() - start_time
        state.record_failure()

        return DreamResult(
            status=DreamStatus.FAILED,
            message=f"Dream failed: {e}",
            duration_seconds=duration,
            error=str(e),
        )


async def check_and_trigger_dream(
    messages_count: int,
    token_count: int,
    api_client: AnthropicAPIClient | None = None,
) -> DreamResult:
    """Check if dream should trigger and execute if so.

    Args:
        messages_count: Number of messages since last dream
        token_count: Token count since last dream
        api_client: Optional API client for dream generation

    Returns:
        DreamResult with operation details
    """
    should, reason = await should_trigger_dream(messages_count, token_count)

    if not should:
        return DreamResult(
            status=DreamStatus.SKIPPED,
            message=f"Dream skipped: {reason}",
        )

    return await trigger_dream(api_client)


def get_dream_stats() -> dict:
    """Get dream statistics.

    Returns:
        Dictionary with dream statistics
    """
    state = get_dream_state()
    config = get_auto_dream_config()

    return {
        "enabled": config.enabled,
        "total_dreams": state.total_dreams,
        "failed_dreams": state.failed_dreams,
        "consecutive_failures": state.consecutive_failures,
        "last_dream_at": state.last_dream_at.isoformat() if state.last_dream_at else None,
        "last_dream_duration_seconds": state.last_dream_duration,
        "messages_since_last_dream": state.messages_since_last_dream,
        "tokens_since_last_dream": state.tokens_since_last_dream,
    }
