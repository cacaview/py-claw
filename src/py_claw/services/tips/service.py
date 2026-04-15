"""
Tips service implementation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .tip_history import get_sessions_since_last_shown, record_tip_shown
from .tip_registry import get_relevant_tips
from .types import Tip, TipContext

if TYPE_CHECKING:
    pass


class TipsService:
    """Service for managing and displaying contextual tips."""

    def __init__(self) -> None:
        self._current_session: int = 0

    def set_current_session(self, session_num: int) -> None:
        """Set the current session number for cooldown tracking."""
        self._current_session = session_num

    async def get_tip_to_show(self, context: TipContext | None = None) -> Tip | None:
        """
        Get the best tip to show based on relevance and cooldown.

        Args:
            context: Optional context for determining relevance

        Returns:
            The tip to show, or None if no tip should be shown
        """
        relevant_tips = await get_relevant_tips(context)

        if not relevant_tips:
            return None

        # Filter by cooldown
        available_tips = [
            tip
            for tip in relevant_tips
            if get_sessions_since_last_shown(tip.id, self._current_session)
            >= tip.cooldown_sessions
        ]

        if not available_tips:
            return None

        # Select tip with longest time since shown
        return self._select_tip_with_longest_time_since_shown(available_tips)

    def _select_tip_with_longest_time_since_shown(
        self, tips: list[Tip]
    ) -> Tip | None:
        """Select the tip that hasn't been shown for the longest time."""
        if not tips:
            return None

        if len(tips) == 1:
            return tips[0]

        tips_with_sessions = [
            (tip, get_sessions_since_last_shown(tip.id, self._current_session))
            for tip in tips
        ]
        tips_with_sessions.sort(key=lambda x: x[1], reverse=True)
        return tips_with_sessions[0][0] if tips_with_sessions else None

    def record_shown_tip(self, tip: Tip) -> None:
        """
        Record that a tip was shown.

        Args:
            tip: The tip that was shown
        """
        record_tip_shown(tip.id, self._current_session)


# Module-level service instance
_tips_service: TipsService | None = None


def get_tips_service() -> TipsService:
    """Get the global tips service instance."""
    global _tips_service
    if _tips_service is None:
        _tips_service = TipsService()
    return _tips_service


async def get_tip_to_show(context: TipContext | None = None) -> Tip | None:
    """
    Get the tip to show using the global service.

    Args:
        context: Optional context for determining relevance

    Returns:
        The tip to show, or None
    """
    service = get_tips_service()
    return await service.get_tip_to_show(context)


def record_shown_tip(tip: Tip) -> None:
    """
    Record that a tip was shown using the global service.

    Args:
        tip: The tip that was shown
    """
    service = get_tips_service()
    service.record_shown_tip(tip)
