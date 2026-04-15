"""
Types for terminal_setup service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TerminalType(str, Enum):
    """Terminal type."""
    VSCODE = "vscode"
    CURSOR = "cursor"
    WINDSURF = "windsurf"
    ALACRITTY = "alacritty"
    ZED = "zed"
    NATIVE_CSIU = "native-csiu"  # Kitty, Ghostty, iTerm, WezTerm, Warp


@dataclass
class TerminalSetupResult:
    """Result of terminal setup."""
    success: bool
    message: str
    terminal_type: TerminalType | None = None
