"""
Tip history tracking - records which tips have been shown.

Uses the global config to store tips history, tracking the session
number when each tip was last shown.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def record_tip_shown(tip_id: str, current_session: int) -> None:
    """
    Record that a tip was shown in the current session.

    Args:
        tip_id: The unique identifier of the tip that was shown
        current_session: The current session number
    """
    # This would integrate with the global config system
    # For now, we use a module-level storage as a placeholder
    if not hasattr(record_tip_shown, "_history"):
        record_tip_shown._history = {}

    history = record_tip_shown._history
    if history.get(tip_id) == current_session:
        return  # Already recorded for this session

    history[tip_id] = current_session


def get_sessions_since_last_shown(tip_id: str, current_session: int) -> int:
    """
    Get the number of sessions since a tip was last shown.

    Args:
        tip_id: The unique identifier of the tip
        current_session: The current session number

    Returns:
        Number of sessions since the tip was last shown, or infinity if never shown
    """
    if not hasattr(record_tip_shown, "_history"):
        return float("inf")

    history = record_tip_shown._history
    last_shown = history.get(tip_id)

    if last_shown is None:
        return float("inf")

    return current_session - last_shown
