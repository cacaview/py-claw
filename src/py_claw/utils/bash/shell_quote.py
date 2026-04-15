"""
Shell quoting and parsing utilities.

Provides functions for safely quoting shell arguments and parsing shell commands.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Union

# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------

ParseEntry = Union[str, "ParseOp"]
ParseOp = dict  # For now, simplified - {'op': '|'}


@dataclass
class ParseResult:
    """Result of parsing a shell command."""

    success: bool
    tokens: list[ParseEntry]
    error: str | None = None


# -----------------------------------------------------------------------------
# Shell quoting
# -----------------------------------------------------------------------------

def quote(args: list[str]) -> str:
    """
    Quote a list of arguments for safe shell execution.

    Uses shlex.quote for proper escaping.
    """
    return " ".join(shlex.quote(arg) for arg in args)


def quote_single(arg: str) -> str:
    """Quote a single argument for shell execution."""
    return shlex.quote(arg)


# -----------------------------------------------------------------------------
# Shell parsing
# -----------------------------------------------------------------------------

# Command operators
COMMAND_OPERATORS = frozenset(["|", "||", "&&", ";", "&", "!", "(", ")", "{", "}"])


def try_parse_shell_command(command: str) -> ParseResult:
    """
    Parse a shell command into tokens.

    Handles quoted strings, operators, and regular arguments.
    Returns ParseResult with success=False on parse error.
    """
    tokens: list[ParseEntry] = []
    pos = 0
    n = len(command)

    while pos < n:
        # Skip whitespace
        while pos < n and command[pos].isspace():
            pos += 1
        if pos >= n:
            break

        char = command[pos]

        # Handle quoted strings
        if char in ("'", '"'):
            quote_char = char
            start = pos
            pos += 1
            while pos < n and command[pos] != quote_char:
                if command[pos] == "\\" and pos + 1 < n:
                    pos += 2  # Skip escaped char
                else:
                    pos += 1
            if pos >= n:
                return ParseResult(success=False, tokens=[], error="Unterminated quote")
            tokens.append(command[start : pos + 1])
            pos += 1
            continue

        # Handle operators
        if char in COMMAND_OPERATORS:
            # Check for multi-char operators
            if char == "|" and pos + 1 < n and command[pos + 1] == "|":
                tokens.append({"op": "||"})
                pos += 2
                continue
            if char == "&" and pos + 1 < n and command[pos + 1] == "&":
                tokens.append({"op": "&&"})
                pos += 2
                continue
            tokens.append({"op": char})
            pos += 1
            continue

        # Handle regular argument
        start = pos
        while pos < n:
            char = command[pos]
            if char.isspace() or char in COMMAND_OPERATORS or char in ("'", '"'):
                break
            pos += 1
        tokens.append(command[start:pos])

    return ParseResult(success=True, tokens=tokens)


def is_operator(token: ParseEntry) -> bool:
    """Check if a token is a command operator."""
    return isinstance(token, dict) and "op" in token


def get_operator(token: ParseEntry) -> str | None:
    """Get the operator string from a token."""
    if isinstance(token, dict) and "op" in token:
        return token["op"]
    return None
