"""Bash utilities - shell quoting and completion utilities.

Based on ClaudeCode-main/src/utils/bash/shellQuote.ts and shellCompletion.ts
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Callable, Protocol

# Type aliases - defined after classes below
ShellCompletionType = str  # 'command' | 'variable' | 'file'


class ParseEntryType:
    """A parsed token from shell command."""


@dataclass
class ParseEntry:
    """A parsed token from shell command."""

    pass


@dataclass
class StringEntry(ParseEntry):
    """A string token."""

    value: str

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"StringEntry({self.value!r})"


@dataclass
class OpEntry(ParseEntry):
    """An operator token like |, ||, &&, ;"""

    op: str

    def __str__(self) -> str:
        return self.op

    def __repr__(self) -> str:
        return f"OpEntry({self.op!r})"


# Result types - defined after ParseEntry
ShellParseResult = tuple[bool, list[ParseEntry], str]
ShellQuoteResult = tuple[bool, str, str]


def try_parse_shell_command(
    cmd: str, env: dict[str, str] | None = None
) -> ShellParseResult:
    """Parse a shell command into tokens.

    Returns:
        Tuple of (success, tokens, error_message)
    """
    try:
        tokens: list[ParseEntry] = []
        parts = cmd.split()

        i = 0
        while i < len(parts):
            part = parts[i]
            # Check for operators
            if part in ("||", "&&", "|", ";"):
                tokens.append(OpEntry(part))
            elif part == ">":
                if i + 1 < len(parts) and parts[i + 1] == ">":
                    tokens.append(OpEntry(">>"))
                    i += 1
                else:
                    tokens.append(OpEntry(">"))
            elif part == "<":
                tokens.append(OpEntry("<"))
            elif part.startswith("$"):
                tokens.append(StringEntry(part))
            else:
                tokens.append(StringEntry(part))
            i += 1

        return (True, tokens, "")
    except Exception as e:
        return (False, [], str(e))


def try_quote_shell_args(args: list[object]) -> ShellQuoteResult:
    """Quote shell arguments safely.

    Returns:
        Tuple of (success, quoted_string, error_message)
    """
    try:
        validated: list[str] = []
        for i, arg in enumerate(args):
            if arg is None:
                validated.append("None")
            elif isinstance(arg, (int, float, bool)):
                validated.append(str(arg))
            elif isinstance(arg, str):
                validated.append(arg)
            elif isinstance(arg, (list, dict)):
                return (False, "", f"Cannot quote argument at index {i}: object values are not supported")
            else:
                return (False, "", f"Cannot quote argument at index {i}: unsupported type {type(arg).__name__}")

        quoted = shlex.join(validated)
        return (True, quoted, "")
    except Exception as e:
        return (False, "", str(e))


def quote_shell_args(args: list[object]) -> str:
    """Quote shell arguments with fallback handling."""
    success, quoted, error = try_quote_shell_args(args)
    if success:
        return quoted

    # Lenient fallback for objects that can be stringified
    try:
        string_args = []
        for arg in args:
            if arg is None:
                string_args.append("None")
            elif isinstance(arg, (str, int, float, bool)):
                string_args.append(str(arg))
            else:
                string_args.append(repr(arg))
        return shlex.join(string_args)
    except Exception as e:
        raise ValueError("Failed to quote shell arguments safely") from e


def has_malformed_tokens(command: str, parsed: list[ParseEntry]) -> bool:
    """Check if parsed tokens contain malformed entries.

    This detects when shell-quote misinterpreted ambiguous patterns
    like JSON-like strings with semicolons.
    """
    # Check for unterminated quotes in the original command
    in_single = False
    in_double = False
    double_count = 0
    single_count = 0

    i = 0
    while i < len(command):
        c = command[i]
        if c == "\\" and not in_single:
            i += 2
            continue
        if c == '"' and not in_single:
            double_count += 1
            in_double = not in_double
        elif c == "'" and not in_double:
            single_count += 1
            in_single = not in_single
        i += 1

    if double_count % 2 != 0 or single_count % 2 != 0:
        return True

    # Check for unbalanced braces/parens/brackets in string tokens
    for entry in parsed:
        if not isinstance(entry, StringEntry):
            continue

        token = entry.value

        # Check curly braces
        if token.count("{") != token.count("}"):
            return True

        # Check parentheses
        if token.count("(") != token.count(")"):
            return True

        # Check square brackets
        if token.count("[") != token.count("]"):
            return True

        # Check for unbalanced unescaped quotes
        # Count unescaped double quotes
        unescaped_doubles = 0
        j = 0
        while j < len(token):
            if token[j] == "\\" and j + 1 < len(token):
                j += 2
                continue
            if token[j] == '"':
                unescaped_doubles += 1
            j += 1
        if unescaped_doubles % 2 != 0:
            return True

        # Count unescaped single quotes
        unescaped_singles = 0
        j = 0
        while j < len(token):
            if token[j] == "\\" and j + 1 < len(token):
                j += 2
                continue
            if token[j] == "'":
                unescaped_singles += 1
            j += 1
        if unescaped_singles % 2 != 0:
            return True

    return False


def has_shell_quote_single_quote_bug(command: str) -> bool:
    """Detect commands with backslash patterns that exploit shell-quote bug.

    In bash, single quotes preserve ALL characters literally.
    But shell-quote incorrectly treats \\ as an escape character inside single quotes.
    """
    in_single_quote = False
    in_double_quote = False

    i = 0
    while i < len(command):
        char = command[i]

        # Handle backslash escaping outside of single quotes
        if char == "\\" and not in_single_quote:
            i += 2
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            i += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote

            # Check if we just closed a single quote with trailing backslashes
            if not in_single_quote:
                backslash_count = 0
                j = i - 1
                while j >= 0 and command[j] == "\\":
                    backslash_count += 1
                    j -= 1

                # Odd trailing backslashes = bug
                if backslash_count > 0 and backslash_count % 2 == 1:
                    return True

                # Even trailing backslashes = bug only when a later ' exists
                if (
                    backslash_count > 0
                    and backslash_count % 2 == 0
                    and "'" in command[i + 1 :]
                ):
                    return True
            i += 1
            continue
        i += 1

    return False


def find_malformed_tokens(command: str, parsed: list[ParseEntry]) -> bool:
    """Alias for has_malformed_tokens for API compatibility."""
    return has_malformed_tokens(command, parsed)


def find_shell_quote_bug(command: str) -> bool:
    """Alias for has_shell_quote_single_quote_bug for API compatibility."""
    return has_shell_quote_single_quote_bug(command)


# Shell history completion


@dataclass
class ShellHistoryMatch:
    """Result of shell history completion lookup."""

    full_command: str
    suffix: str


# Cache for shell history commands
_shell_history_cache: list[str] | None = None
_shell_history_cache_timestamp: float = 0
_CACHE_TTL_MS = 60000  # 60 seconds


def clear_shell_history_cache() -> None:
    """Clear the shell history cache."""
    global _shell_history_cache, _shell_history_cache_timestamp
    _shell_history_cache = None
    _shell_history_cache_timestamp = 0


def prepend_to_shell_history_cache(command: str) -> None:
    """Add a command to the front of the shell history cache."""
    global _shell_history_cache
    if _shell_history_cache is None:
        return

    if command in _shell_history_cache:
        _shell_history_cache.remove(command)
    _shell_history_cache.insert(0, command)


async def get_shell_history_completion(input: str) -> ShellHistoryMatch | None:
    """Find the best matching shell command from history for the given input."""
    import time

    if not input or len(input) < 2:
        return None

    trimmed_input = input.strip()
    if not trimmed_input:
        return None

    global _shell_history_cache, _shell_history_cache_timestamp
    now = time.time() * 1000

    # Return cached result if still fresh
    if _shell_history_cache and now - _shell_history_cache_timestamp < _CACHE_TTL_MS:
        commands = _shell_history_cache
    else:
        # Would need to read from history - placeholder implementation
        commands = []
        _shell_history_cache = commands
        _shell_history_cache_timestamp = now

    # Find first command that starts with the exact input
    for command in commands:
        if command.startswith(input) and command != input:
            return ShellHistoryMatch(
                full_command=command, suffix=command[len(input) :]
            )

    return None


# Shell completion functions


async def get_shell_completions(
    input: str, cursor_offset: int, abort_signal: None = None
) -> list[dict]:
    """Get shell completions for the given input.

    Supports bash and zsh shells.
    """
    # This would need actual shell execution - placeholder
    return []
