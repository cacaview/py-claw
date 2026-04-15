"""
Theme service for managing color themes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .types import Theme, ThemeColor, ThemeResult

logger = logging.getLogger(__name__)

# Built-in themes
BUILT_IN_THEMES = {
    "default": Theme(
        name="default",
        description="Default theme",
        colors={
            "background": "#1e1e1e",
            "foreground": "#d4d4d4",
            "error": "#f44747",
            "warning": "#cca700",
            "info": "#3794ff",
            "success": "#89d185",
        },
    ),
    "monokai": Theme(
        name="monokai",
        description="Monokai theme",
        colors={
            "background": "#272822",
            "foreground": "#f8f8f2",
            "error": "#f92672",
            "warning": "#e6db74",
            "info": "#66d9ef",
            "success": "#a6e22e",
        },
    ),
    "solarized-dark": Theme(
        name="solarized-dark",
        description="Solarized Dark theme",
        colors={
            "background": "#002b36",
            "foreground": "#839496",
            "error": "#dc322f",
            "warning": "#b58900",
            "info": "#268bd2",
            "success": "#859900",
        },
    ),
    "solarized-light": Theme(
        name="solarized-light",
        description="Solarized Light theme",
        colors={
            "background": "#fdf6e3",
            "foreground": "#657b83",
            "error": "#dc322f",
            "warning": "#b58900",
            "info": "#268bd2",
            "success": "#859900",
        },
    ),
    "nord": Theme(
        name="nord",
        description="Nord theme",
        colors={
            "background": "#2e3440",
            "foreground": "#eceff4",
            "error": "#bf616a",
            "warning": "#ebcb8b",
            "info": "#81a1c1",
            "success": "#a3be8c",
        },
    ),
    "dracula": Theme(
        name="dracula",
        description="Dracula theme",
        colors={
            "background": "#282a36",
            "foreground": "#f8f8f2",
            "error": "#ff5555",
            "warning": "#f1fa8c",
            "info": "#8be9fd",
            "success": "#50fa7b",
        },
    ),
}


def get_theme_storage_path() -> Path:
    """Get the path to theme configuration.

    Returns:
        Path to themes.json
    """
    config_dir = Path.home() / ".claude"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "themes.json"


def get_current_theme_name() -> str:
    """Get the name of the current theme.

    Returns:
        Current theme name
    """
    try:
        data = {}
        path = get_theme_storage_path()
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        return data.get("current", "default")
    except Exception:
        return "default"


def set_current_theme(theme_name: str) -> ThemeResult:
    """Set the current theme.

    Args:
        theme_name: Name of the theme to set

    Returns:
        ThemeResult with operation status
    """
    if theme_name not in BUILT_IN_THEMES:
        return ThemeResult(
            success=False,
            message=f"Unknown theme: {theme_name}. Available: {', '.join(BUILT_IN_THEMES.keys())}",
        )

    try:
        path = get_theme_storage_path()
        data = {"current": theme_name}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return ThemeResult(
            success=True,
            message=f"Theme set to {theme_name}",
            theme=BUILT_IN_THEMES[theme_name],
        )
    except IOError as e:
        return ThemeResult(
            success=False,
            message=f"Error saving theme: {e}",
        )


def get_theme(theme_name: str | None = None) -> Theme | None:
    """Get a theme by name.

    Args:
        theme_name: Name of the theme to get, or None for current

    Returns:
        Theme object or None
    """
    if theme_name is None:
        theme_name = get_current_theme_name()
    return BUILT_IN_THEMES.get(theme_name)


def list_themes() -> list[Theme]:
    """List all available themes.

    Returns:
        List of Theme objects
    """
    return list(BUILT_IN_THEMES.values())


def get_theme_info() -> ThemeResult:
    """Get current theme information.

    Returns:
        ThemeResult with current theme info
    """
    current_name = get_current_theme_name()
    current = BUILT_IN_THEMES.get(current_name)

    if current:
        return ThemeResult(
            success=True,
            message=f"Current theme: {current_name}",
            theme=current,
        )
    else:
        return ThemeResult(
            success=True,
            message=f"Theme {current_name} not found, using default",
            theme=BUILT_IN_THEMES["default"],
        )


def format_theme_text(result: ThemeResult) -> str:
    """Format theme result as plain text.

    Args:
        result: ThemeResult to format

    Returns:
        Formatted text
    """
    if not result.success:
        return f"Error: {result.message}"

    lines = ["Claude Code Themes", "=" * 40, ""]

    # List all themes
    lines.append("Available themes:")
    for name, theme in BUILT_IN_THEMES.items():
        marker = " *" if result.theme and result.theme.name == name else ""
        lines.append(f"  - {name}{marker}: {theme.description}")

    lines.append("")
    lines.append("Colors:")
    if result.theme:
        for color_name, hex_value in result.theme.colors.items():
            lines.append(f"  {color_name}: {hex_value}")

    return "\n".join(lines)
