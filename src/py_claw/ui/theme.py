"""Theme constants and tokens for Textual UI.

Maps TypeScript theme tokens to Textual styles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NotRequired, TypedDict


class ThemeColors(TypedDict, total=False):
    """Color tokens matching TypeScript design-system."""

    # Background colors
    background: str
    surface: str
    surface_elevated: str

    # Text colors
    text: str
    text_muted: str
    text_dim: str

    # Border colors
    border: str
    border_focused: str

    # Semantic colors
    primary: str
    success: str
    warning: str
    error: str
    info: str


@dataclass(slots=True)
class Theme:
    """Theme configuration for Textual UI components."""

    colors: ThemeColors = field(default_factory=ThemeColors)

    # Spacing
    spacing_xs: int = 0
    spacing_sm: int = 1
    spacing_md: int = 2
    spacing_lg: int = 4

    # Border styles
    border_style: str = "solid"
    border_width: int = 1

    # Corner radius (not widely used in terminal but some components)
    radius: int = 0

    # Focus indicator
    focus_color: str = "yellow"


# Default dark theme (Claude Code default)
DEFAULT_THEME = Theme(
    colors=ThemeColors(
        background="#0f0f0f",
        surface="#1a1a1a",
        surface_elevated="#252525",
        text="#ffffff",
        text_muted="#888888",
        text_dim="#555555",
        border="#333333",
        border_focused="#666666",
        primary="#3b82f6",
        success="#22c55e",
        warning="#f59e0b",
        error="#ef4444",
        info="#06b6d4",
    ),
)

# Light theme variant
LIGHT_THEME = Theme(
    colors=ThemeColors(
        background="#ffffff",
        surface="#f5f5f5",
        surface_elevated="#ffffff",
        text="#1a1a1a",
        text_muted="#666666",
        text_dim="#999999",
        border="#dddddd",
        border_focused="#999999",
        primary="#2563eb",
        success="#16a34a",
        warning="#d97706",
        error="#dc2626",
        info="#0891b2",
    ),
)


def detect_theme() -> Theme:
    """Auto-detect theme based on terminal environment.

    Returns DEFAULT_THEME (dark) by default since Claude Code uses dark mode.
    """
    # TODO: Could check TERM_DARK or color scheme hints
    return DEFAULT_THEME


# Global theme instance
_current_theme: Theme = DEFAULT_THEME


def get_theme() -> Theme:
    """Get the current active theme."""
    return _current_theme


def set_theme(theme: Theme) -> None:
    """Set the current theme."""
    global _current_theme
    _current_theme = theme
