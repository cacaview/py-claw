"""
Suggestions utilities.

Provides:
- Command suggestions with fuzzy matching
- Shell completion suggestions
- Slash command position detection
"""
from __future__ import annotations

from .command_suggestions import (
    find_mid_input_slash_command,
    get_best_command_match,
    is_command_input,
    has_command_args,
    format_command,
    generate_command_suggestions,
    apply_command_suggestion,
    find_slash_command_positions,
)
from .shell_history_completion import get_shell_history_suggestions
from .directory_completion import get_directory_completions

__all__ = [
    "find_mid_input_slash_command",
    "get_best_command_match",
    "is_command_input",
    "has_command_args",
    "format_command",
    "generate_command_suggestions",
    "apply_command_suggestion",
    "find_slash_command_positions",
    "get_shell_history_suggestions",
    "get_directory_completions",
]
