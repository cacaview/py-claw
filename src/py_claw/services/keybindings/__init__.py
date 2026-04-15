"""
Keybindings service for customizing keyboard shortcuts.

Based on ClaudeCode-main/src/services/keybindings/
"""
from py_claw.services.keybindings.service import (
    generate_keybindings_template,
    get_default_keybindings,
    get_keybindings_config,
    get_keybindings_info,
    get_keybindings_path,
    is_keybinding_customization_enabled,
    load_keybindings,
    save_keybindings,
)
from py_claw.services.keybindings.types import Keybinding, KeybindingsConfig, KeybindingsResult


__all__ = [
    "get_keybindings_config",
    "get_keybindings_path",
    "is_keybinding_customization_enabled",
    "get_default_keybindings",
    "load_keybindings",
    "save_keybindings",
    "generate_keybindings_template",
    "get_keybindings_info",
    "Keybinding",
    "KeybindingsConfig",
    "KeybindingsResult",
]
