"""
Tips service - provides contextual tips to users during sessions.

This service manages a registry of tips that can be shown to users,
tracks which tips have been shown, and selects the most relevant tip
based on user context and cooldown periods.
"""
from __future__ import annotations

from .service import TipsService, get_tip_to_show, record_shown_tip
from .types import Tip, TipContext

__all__ = ["TipsService", "get_tip_to_show", "record_shown_tip", "Tip", "TipContext"]
