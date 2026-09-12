"""Auto-compact integration for the query engine.

Wires the compact service into the turn loop to automatically
compress context when approaching token limits.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState

logger = logging.getLogger(__name__)


def check_and_trigger_auto_compact(
    state: RuntimeState,
    *,
    token_counter: callable | None = None,
) -> tuple[bool, str]:
    """Check if auto-compact should be triggered and attempt it.

    Args:
        state: Runtime state with session token counts
        token_counter: Optional callable returning current total token count

    Returns:
        (triggered, message) tuple
    """
    try:
        from py_claw.services.compact.auto_trigger import (
            should_auto_compact,
            _context_window_for_model,
        )

        model = state.model or "claude-sonnet-4-20250514"

        # Get current token count
        if token_counter is not None:
            total_tokens = token_counter()
        else:
            total_tokens = state.session_input_tokens + state.session_output_tokens

        # Check if we should compact
        result = should_auto_compact(current_token_count=total_tokens, model=model)
        if not result.should_trigger:
            return False, ""

        threshold_info = result.threshold_info
        threshold_tokens = (
            threshold_info.effective_threshold if threshold_info else 0
        )
        logger.info(
            "Auto-compact triggered: %d tokens, threshold=%d",
            total_tokens,
            threshold_tokens,
        )

        # For now, return that compact should be triggered.
        # The actual compaction is handled by the compact service.
        return (
            True,
            f"Auto-compact recommended at {total_tokens} tokens "
            f"(threshold: {threshold_tokens})",
        )

    except ImportError:
        return False, ""
    except Exception as e:
        logger.warning("Auto-compact check failed: %s", e)
        return False, ""


def get_context_usage_percentage(state: RuntimeState) -> float | None:
    """Get current context usage as a percentage of the context window.

    Returns None if model context window is unknown.
    """
    try:
        from py_claw.services.compact.auto_trigger import _context_window_for_model

        model = state.model or "claude-sonnet-4-20250514"
        window = _context_window_for_model(model)
        if window <= 0:
            return None
        total_tokens = state.session_input_tokens + state.session_output_tokens
        return (total_tokens / window) * 100.0
    except Exception:
        return None
