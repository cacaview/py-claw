"""
Vim service for managing Vim mode.

Based on ClaudeCode-main/src/services/vim/

Note: This is a simplified implementation. The actual Claude Code
Vim mode integration is more sophisticated with keybinding handling.
"""
from py_claw.services.vim.service import (
    format_vim_text,
    get_current_mode,
    get_vim_info,
    is_vim_enabled,
    set_vim_mode,
    toggle_vim_mode,
)
from py_claw.services.vim.types import VimConfig, VimMode, VimResult


__all__ = [
    "is_vim_enabled",
    "get_current_mode",
    "toggle_vim_mode",
    "set_vim_mode",
    "get_vim_info",
    "format_vim_text",
    "VimMode",
    "VimConfig",
    "VimResult",
]
