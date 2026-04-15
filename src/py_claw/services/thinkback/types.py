"""
Types for thinkback service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ThinkbackPhase(str, Enum):
    """Thinkback installation phase."""
    CHECKING = "checking"
    INSTALLING_MARKETPLACE = "installing_marketplace"
    INSTALLING_PLUGIN = "installing_plugin"
    ENABLING_PLUGIN = "enabling_plugin"
    READY = "ready"
    ERROR = "error"


class MenuAction(str, Enum):
    """Thinkback menu action."""
    PLAY = "play"
    EDIT = "edit"
    FIX = "fix"
    REGENERATE = "regenerate"


@dataclass
class AnimationResult:
    """Result of playing thinkback animation."""
    success: bool
    message: str
    path: str | None = None


@dataclass
class ThinkbackResult:
    """Result of thinkback operation."""
    success: bool
    message: str
    phase: ThinkbackPhase | None = None
    action: MenuAction | None = None
