"""
Types for vim service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VimMode(str, Enum):
    """Vim editing mode."""
    NORMAL = "normal"
    INSERT = "insert"
    VISUAL = "visual"
    COMMAND = "command"


@dataclass
class VimConfig:
    """Vim configuration."""
    enabled: bool = False
    current_mode: VimMode = VimMode.NORMAL


@dataclass
class VimResult:
    """Result of vim operation."""
    success: bool
    message: str
    mode: VimMode | None = None
