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
    get_shortcut_display,
    get_all_shortcuts_for_display,
    get_status_shortcuts_hint,
    get_footer_shortcuts_hint,
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
    "get_shortcut_display",
    "get_all_shortcuts_for_display",
    "get_status_shortcuts_hint",
    "get_footer_shortcuts_hint",
    "Keybinding",
    "KeybindingsConfig",
    "KeybindingsResult",
]
