"""
Bash shell utilities.

Provides:
- Shell command parsing and quoting
- Shell completion generation
- Shell type detection
"""
from __future__ import annotations

from .shell_quote import (
    quote,
    try_parse_shell_command,
    ParseResult,
    ParseEntry,
)
from .shell_completion import (
    get_shell_completions,
    parse_input_context,
    get_shell_type,
)

__all__ = [
    "quote",
    "try_parse_shell_command",
    "ParseResult",
    "ParseEntry",
    "get_shell_completions",
    "parse_input_context",
    "get_shell_type",
]
