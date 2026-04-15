"""Bash utilities - shell quoting and completion utilities.

Based on ClaudeCode-main/src/utils/bash/
"""

from py_claw.services.bash.bash import (
    OpEntry,
    ParseEntry,
    ShellCompletionType,
    ShellParseResult,
    ShellQuoteResult,
    StringEntry,
    clear_shell_history_cache,
    find_malformed_tokens,
    find_shell_quote_bug,
    get_shell_completions,
    get_shell_history_completion,
    has_malformed_tokens,
    has_shell_quote_single_quote_bug,
    prepend_to_shell_history_cache,
    quote_shell_args,
    try_parse_shell_command,
    try_quote_shell_args,
)

__all__ = [
    "ShellCompletionType",
    "ShellParseResult",
    "ShellQuoteResult",
    "try_parse_shell_command",
    "try_quote_shell_args",
    "has_malformed_tokens",
    "has_shell_quote_single_quote_bug",
    "quote_shell_args",
    "get_shell_completions",
    "get_shell_history_completion",
    "clear_shell_history_cache",
    "prepend_to_shell_history_cache",
    "find_malformed_tokens",
    "find_shell_quote_bug",
]
