"""
Vim service for managing Vim mode.

Based on ClaudeCode-main/src/services/vim/

Provides Vim editing mode state management with TUI integration.
When vim mode changes, publishes updates to the global TUI store.
"""
from py_claw.services.vim.service import (
    format_vim_text,
    get_current_mode,
    get_tui_vim_mode,
    get_vim_info,
    get_vim_status_for_tui,
    is_vim_active_in_tui,
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
    "get_tui_vim_mode",
    "is_vim_active_in_tui",
    "get_vim_status_for_tui",
    "VimMode",
    "VimConfig",
    "VimResult",
]
