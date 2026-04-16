"""
Keybindings service for customizing keyboard shortcuts.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .types import Keybinding, KeybindingsConfig, KeybindingsResult

logger = logging.getLogger(__name__)

_keybindings_config = KeybindingsConfig()


def get_keybindings_config() -> KeybindingsConfig:
    """Get the keybindings configuration."""
    return _keybindings_config


def is_keybinding_customization_enabled() -> bool:
    """Check if keybinding customization is enabled.

    Returns:
        True if customization is enabled
    """
    return _keybindings_config.enabled


def get_keybindings_path() -> Path:
    """Get the path to the keybindings file.

    Returns:
        Path to keybindings.json
    """
    config_dir = Path.home() / ".claude"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "keybindings.json"


def get_default_keybindings() -> list[Keybinding]:
    """Get the default keybindings.

    Returns:
        List of default Keybinding objects
    """
    return [
        Keybinding(key="enter", command="submit", description="Submit prompt"),
        Keybinding(key="esc", command="interrupt", description="Interrupt / cancel / close"),
        Keybinding(key="up", command="history-up", description="Navigate history / suggestions"),
        Keybinding(key="down", command="history-down", description="Navigate history / suggestions"),
        Keybinding(key="tab", command="accept-suggestion", description="Accept suggestion / complete"),
        Keybinding(key="shift+tab", command="cycle-mode", description="Cycle prompt mode"),
        Keybinding(key="right", command="accept-ghost-text", description="Accept inline ghost text"),
        Keybinding(key="?", command="toggle-help", description="Toggle this help menu"),
        Keybinding(key="ctrl+g", command="new-session", description="New session"),
        Keybinding(key="ctrl+l", command="clear-log", description="Clear log"),
        Keybinding(key="ctrl+r", command="history-search", description="History search"),
        Keybinding(key="ctrl+p", command="quick-open", description="Quick open file"),
        Keybinding(key="ctrl+m", command="model-picker", description="Model picker"),
        Keybinding(key="ctrl+t", command="tasks-panel", description="Tasks panel"),
        # Vim mode bindings
        Keybinding(key="i", command="vim-insert", description="Insert mode (vim)"),
        Keybinding(key="a", command="vim-append", description="Append mode (vim)"),
        Keybinding(key="v", command="vim-visual", description="Visual mode (vim)"),
        Keybinding(key="escape", command="vim-normal", description="Normal mode (vim)"),
    ]


def load_keybindings() -> list[Keybinding]:
    """Load keybindings from the keybindings file.

    Returns:
        List of Keybinding objects
    """
    keybindings_file = get_keybindings_path()

    if not keybindings_file.exists():
        return get_default_keybindings()

    try:
        with open(keybindings_file, encoding="utf-8") as f:
            data = json.load(f)

        bindings = []
        for item in data.get("keybindings", []):
            bindings.append(Keybinding(
                key=item.get("key", ""),
                command=item.get("command", ""),
                description=item.get("description"),
            ))
        return bindings

    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Error loading keybindings: %s", e)
        return get_default_keybindings()


def save_keybindings(keybindings: list[Keybinding]) -> KeybindingsResult:
    """Save keybindings to the keybindings file.

    Args:
        keybindings: List of Keybinding objects to save

    Returns:
        KeybindingsResult with operation status
    """
    keybindings_file = get_keybindings_path()

    try:
        data = {
            "keybindings": [
                {
                    "key": kb.key,
                    "command": kb.command,
                    "description": kb.description,
                }
                for kb in keybindings
            ]
        }

        with open(keybindings_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return KeybindingsResult(
            success=True,
            message=f"Saved {len(keybindings)} keybindings to {keybindings_file}",
            keybindings=keybindings,
            path=str(keybindings_file),
        )

    except IOError as e:
        logger.error("Error saving keybindings: %s", e)
        return KeybindingsResult(
            success=False,
            message=f"Error saving keybindings: {e}",
        )


def generate_keybindings_template() -> KeybindingsResult:
    """Generate a keybindings template file.

    Returns:
        KeybindingsResult with the template
    """
    template = get_default_keybindings()
    return save_keybindings(template)


def get_keybindings_info() -> dict:
    """Get detailed keybindings information.

    Returns:
        Dictionary with keybindings info
    """
    bindings = load_keybindings()
    return {
        "enabled": is_keybinding_customization_enabled(),
        "path": str(get_keybindings_path()),
        "count": len(bindings),
        "keybindings": [
            {"key": kb.key, "command": kb.command, "description": kb.description}
            for kb in bindings
        ],
    }


# ── shortcut display helpers ──────────────────────────────────────────────────

# Maps command names to their display-key strings (for help menu / footer hints)
_SHORTCUT_DISPLAY_MAP: dict[str, str] = {
    "submit": "enter",
    "interrupt": "esc",
    "history-up": "↑",
    "history-down": "↓",
    "accept-suggestion": "tab",
    "accept-ghost-text": "→",
    "toggle-help": "?",
    "cycle-mode": "shift+tab",
    "new-session": "ctrl+g",
    "clear-log": "ctrl+l",
    "history-search": "ctrl+r",
    "quick-open": "ctrl+p",
    "model-picker": "ctrl+m",
    "tasks-panel": "ctrl+t",
    "vim-insert": "i",
    "vim-append": "a",
    "vim-visual": "v",
    "vim-normal": "esc",
}


_HELP_SHORTCUTS: dict[str, str] = {
    "enter": "Submit prompt",
    "esc": "Interrupt / cancel / close",
    "↑ / ↓": "Navigate history / suggestions",
    "tab": "Accept suggestion / complete",
    "→": "Accept inline ghost text",
    "shift+tab": "Cycle prompt mode",
    "?": "Toggle this help menu",
    "ctrl+g": "New session",
    "ctrl+l": "Clear log",
    "ctrl+c": "Quit",
    "ctrl+r": "History search",
    "ctrl+p": "Quick open",
    "ctrl+m": "Model picker",
    "ctrl+t": "Tasks panel",
    "i": "Insert mode (vim)",
    "a": "Append mode (vim)",
    "v": "Visual mode (vim)",
}


_STATUS_SHORTCUTS = "Ctrl+G new · Ctrl+L clear · ?: help"
_FOOTER_SHORTCUTS = "help · Ctrl+R: history · Ctrl+P: files · Ctrl+M: model · Ctrl+T: tasks"


def get_shortcut_display(action: str) -> str | None:
    """Get display text for a shortcut action.

    Args:
        action: Command/action name (e.g. "submit", "toggle-help")

    Returns:
        Human-readable shortcut string like "↑ / ↓" for "history-up/down"
        or None if no shortcut exists.
    """
    return _SHORTCUT_DISPLAY_MAP.get(action)


def get_all_shortcuts_for_display() -> dict[str, str]:
    """Get all shortcuts mapped to their display strings for the help menu.

    Returns:
        Dictionary mapping action names to display strings,
        suitable for HelpMenuDialog._shortcuts.
    """
    return dict(_HELP_SHORTCUTS)


def get_status_shortcuts_hint() -> str:
    """Get the condensed status-line shortcut hint string."""
    return _STATUS_SHORTCUTS


def get_footer_shortcuts_hint() -> str:
    """Get the footer shortcut hint string without the leading `?`."""
    return _FOOTER_SHORTCUTS
