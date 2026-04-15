"""Suggestions utilities - command/shell_history/directory suggestions.

Based on ClaudeCode-main/src/utils/suggestions/
"""

from py_claw.services.suggestions.suggestions import (
    CommandMatch,
    CommandSuggestionItem,
    DirectoryEntry,
    MidInputSlashCommand,
    PathCompletionOptions,
    PathEntry,
    clear_directory_cache,
    clear_path_cache,
    find_mid_input_slash_command,
    find_slash_command_positions,
    format_command,
    generate_command_suggestions,
    get_best_command_match,
    get_command_args,
    get_directory_completions,
    get_path_completions,
    get_shell_history_completion,
    is_command_input,
    is_path_like_token,
    parse_partial_path,
)
from py_claw.services.suggestions.usage_tracking import (
    CommandUsageTracker,
    get_usage_tracker,
)

__all__ = [
    # Types
    "DirectoryEntry",
    "PathEntry",
    "PathCompletionOptions",
    "CommandSuggestionItem",
    "MidInputSlashCommand",
    "CommandMatch",
    # Directory suggestions
    "parse_partial_path",
    "get_directory_completions",
    "clear_directory_cache",
    "is_path_like_token",
    "get_path_completions",
    "clear_path_cache",
    # Command suggestions
    "is_command_input",
    "get_command_args",
    "format_command",
    "find_mid_input_slash_command",
    "get_best_command_match",
    "generate_command_suggestions",
    "find_slash_command_positions",
    # Shell history
    "get_shell_history_completion",
    # Usage tracking
    "CommandUsageTracker",
    "get_usage_tracker",
]
