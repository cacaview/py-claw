"""Speculation analytics — mirrors TS logSpeculation() in speculation.ts."""

from __future__ import annotations

from typing import Any


def log_speculation(
    speculation_id: str,
    outcome: str,
    duration_ms: int,
    suggestion_length: int,
    message_count: int,
    boundary_type: str | None,
    **extras: Any,
) -> None:
    """Log a tengu_speculation analytics event.

    Mirrors ClaudeCode-main/src/services/PromptSuggestion/speculation.ts logSpeculation().

    Args:
        speculation_id: Short UUID for the speculation run
        outcome: 'accepted' | 'aborted' | 'completed' | 'error'
        duration_ms: Wall-clock time of the speculation
        suggestion_length: Length of the suggested text
        message_count: Number of messages in the speculation
        boundary_type: 'complete' | 'bash' | 'edit' | 'denied_tool' | None
        **extras: Additional fields to include in the event
    """
    try:
        from py_claw.services.analytics.service import get_analytics_service

        service = get_analytics_service()
        service.log_event("tengu_speculation", {
            "speculation_id": speculation_id,
            "outcome": outcome,
            "duration_ms": duration_ms,
            "suggestion_length": suggestion_length,
            "tools_executed": message_count,
            "boundary_type": boundary_type,
            **extras,
        })
    except Exception:
        # Analytics failures should never crash speculation
        pass
