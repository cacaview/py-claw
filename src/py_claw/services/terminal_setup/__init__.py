"""
Terminal setup service for configuring terminal keybindings.

Based on ClaudeCode-main/src/commands/terminalSetup/
"""
from py_claw.services.terminal_setup.service import (
    get_terminal_type,
    get_terminal_setup_info,
    has_used_backslash_return,
    is_shift_enter_keybinding_installed,
    is_vscode_remote_ssh,
    mark_backslash_return_used,
    setup_terminal,
    should_offer_setup,
)
from py_claw.services.terminal_setup.types import TerminalSetupResult, TerminalType


__all__ = [
    "get_terminal_type",
    "get_terminal_setup_info",
    "is_vscode_remote_ssh",
    "should_offer_setup",
    "setup_terminal",
    "is_shift_enter_keybinding_installed",
    "has_used_backslash_return",
    "mark_backslash_return_used",
    "TerminalType",
    "TerminalSetupResult",
]
