"""
Theme service for managing color themes.

Based on ClaudeCode-main/src/services/theme/
"""
from py_claw.services.theme.service import (
    format_theme_text,
    get_current_theme_name,
    get_theme,
    get_theme_info,
    list_themes,
    set_current_theme,
)
from py_claw.services.theme.types import Theme, ThemeColor, ThemeResult


__all__ = [
    "get_current_theme_name",
    "set_current_theme",
    "get_theme",
    "list_themes",
    "get_theme_info",
    "format_theme_text",
    "Theme",
    "ThemeColor",
    "ThemeResult",
]
