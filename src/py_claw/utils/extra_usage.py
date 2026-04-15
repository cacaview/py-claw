"""
Extra usage billing helpers.

Determines whether usage should be billed as extra usage based on
model, subscription status, and fast mode.

Mirrors TS extraUsage.ts behavior.
"""
from __future__ import annotations

from .auth import is_claude_ai_subscriber
from .env import is_env_truthy


def is_billed_as_extra_usage(
    model: str | None,
    is_fast_mode: bool,
    is_opus_1m_merged: bool,
) -> bool:
    """
    Determine if usage should be billed as extra usage.

    Args:
        model: Model name (e.g., 'opus', 'sonnet-4-6')
        is_fast_mode: Whether fast mode is active
        is_opus_1m_merged: Whether Opus 1M context merge is enabled

    Returns:
        True if usage counts as extra usage billing
    """
    if not is_claude_ai_subscriber():
        return False

    if is_fast_mode:
        return True

    if model is None:
        return False

    # Check if model has 1M context
    if not _has_1m_context(model):
        return False

    # Normalize model name
    m = model.lower().replace("[1m]", "").strip()

    is_opus_46 = m == "opus" or "opus-4-6" in m
    is_sonnet_46 = m == "sonnet" or "sonnet-4-6" in m

    # Opus 4.6 with 1M merge is NOT billed as extra usage
    if is_opus_46 and is_opus_1m_merged:
        return False

    return is_opus_46 or is_sonnet_46


def _has_1m_context(model: str) -> bool:
    """Check if model supports 1M context window."""
    if model is None:
        return False
    # Models with [1m] suffix or opus-4-6-20250514 support 1M context
    m = model.lower()
    if "[1m]" in m:
        return True
    if "opus-4-6" in m:
        return True
    return False
