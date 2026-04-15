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
        Keybinding(key="ctrl+o", command="open", description="Open file"),
        Keybinding(key="ctrl+s", command="save", description="Save file"),
        Keybinding(key="ctrl+c", command="copy", description="Copy"),
        Keybinding(key="ctrl+v", command="paste", description="Paste"),
        Keybinding(key="ctrl+z", command="undo", description="Undo"),
        Keybinding(key="ctrl+y", command="redo", description="Redo"),
        Keybinding(key="ctrl+b", command="toggle-sidebar", description="Toggle sidebar"),
        Keybinding(key="ctrl+p", command="quick-open", description="Quick open file"),
        Keybinding(key="ctrl+shift+p", command="command-palette", description="Command palette"),
        Keybinding(key="ctrl+`", command="toggle-terminal", description="Toggle terminal"),
        Keybinding(key="ctrl+/", command="toggle-comment", description="Toggle line comment"),
        Keybinding(key="ctrl+shift+k", command="delete-line", description="Delete line"),
        Keybinding(key="alt+up", command="move-line-up", description="Move line up"),
        Keybinding(key="alt+down", command="move-line-down", description="Move line down"),
        Keybinding(key="ctrl+space", command="suggest", description="Trigger suggestion"),
        Keybinding(key="ctrl+shift+space", command="parameter-hints", description="Parameter hints"),
        Keybinding(key="ctrl+shift+o", command="outline", description="Show outline"),
        Keybinding(key="ctrl+shift+g", command="git", description="Show git view"),
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
