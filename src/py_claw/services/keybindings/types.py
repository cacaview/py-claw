"""
Types for keybindings service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Keybinding:
    """A keyboard shortcut binding."""
    key: str
    command: str
    description: str | None = None


@dataclass
class KeybindingsConfig:
    """Configuration for keybindings."""
    enabled: bool = True
    custom_keybindings: dict[str, str] | None = None


@dataclass
class KeybindingsResult:
    """Result of keybindings operation."""
    success: bool
    message: str
    keybindings: list[Keybinding] | None = None
    path: str | None = None
