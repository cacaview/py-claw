"""
Shell completion utilities.

Provides shell completion generation for bash and zsh shells.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    pass

# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------

class ShellType(str, Enum):
    """Supported shell types."""

    BASH = "bash"
    ZSH = "zsh"
    UNKNOWN = "unknown"


class CompletionType(str, Enum):
    """Types of shell completions."""

    COMMAND = "command"
    VARIABLE = "variable"
    FILE = "file"


@dataclass
class CompletionResult:
    """A single completion suggestion."""

    id: str
    display_text: str
    description: str | None = None
    metadata: dict | None = None


# -----------------------------------------------------------------------------
# Shell detection
# -----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_shell_type() -> ShellType:
    """
    Detect the current shell type.

    Checks SHELL environment variable and common paths.
    """
    shell_env = os.environ.get("SHELL", "")
    if "zsh" in shell_env:
        return ShellType.ZSH
    if "bash" in shell_env:
        return ShellType.BASH

    # Check common paths
    for path in ["/bin/bash", "/usr/bin/bash", "/bin/zsh", "/usr/bin/zsh"]:
        if os.path.exists(path):
            if "zsh" in path:
                return ShellType.ZSH
            if "bash" in path:
                return ShellType.BASH

    return ShellType.UNKNOWN


# -----------------------------------------------------------------------------
# Completion context parsing
# -----------------------------------------------------------------------------

@dataclass
class InputContext:
    """Context for shell completion."""

    prefix: str
    completion_type: CompletionType


COMMAND_OPERATORS = frozenset(["|", "||", "&&", ";"])


def get_completion_type_from_prefix(prefix: str) -> CompletionType:
    """Determine completion type based on prefix characteristics."""
    if prefix.startswith("$"):
        return CompletionType.VARIABLE
    if "/" in prefix or prefix.startswith("~") or prefix.startswith("."):
        return CompletionType.FILE
    return CompletionType.COMMAND


def find_last_string_token(tokens: list) -> tuple[str, int] | None:
    """Find the last string token in a parsed list."""
    for i in range(len(tokens) - 1, -1, -1):
        if isinstance(tokens[i], str):
            return tokens[i], i
    return None


def parse_input_context(input_str: str, cursor_offset: int) -> InputContext:
    """
    Parse input to extract completion context.

    Determines:
    - The prefix to complete
    - The type of completion needed
    """
    before_cursor = input_str[:cursor_offset]

    # Check for variable prefix
    var_match = re.search(r"\$[a-zA-Z_][a-zA-Z0-9_]*$", before_cursor)
    if var_match:
        return InputContext(
            prefix=var_match.group(0), completion_type=CompletionType.VARIABLE
        )

    # Try to parse with shell parser
    from .shell_quote import try_parse_shell_command

    parse_result = try_parse_shell_command(before_cursor)
    if not parse_result.success:
        # Fallback to simple parsing
        tokens = before_cursor.split()
        prefix = tokens[-1] if tokens else ""
        is_first = len(tokens) <= 1 and before_cursor and not before_cursor.strip().endswith(" ")
        return InputContext(
            prefix=prefix,
            completion_type=CompletionType.COMMAND if is_first else get_completion_type_from_prefix(prefix),
        )

    # Find current token
    last_str = find_last_string_token(parse_result.tokens)
    if not last_str:
        return InputContext(prefix="", completion_type=CompletionType.COMMAND)

    prefix_str, _ = last_str

    # If trailing space, new argument expected
    if before_cursor.endswith(" "):
        return InputContext(prefix="", completion_type=CompletionType.FILE)

    return InputContext(
        prefix=prefix_str, completion_type=get_completion_type_from_prefix(prefix_str)
    )


# -----------------------------------------------------------------------------
# Completion command generation
# -----------------------------------------------------------------------------

MAX_SHELL_COMPLETIONS = 15
SHELL_COMPLETION_TIMEOUT_MS = 1000


def get_bash_completion_command(prefix: str, completion_type: CompletionType) -> str:
    """Generate bash completion command using compgen."""
    from .shell_quote import quote

    if completion_type == CompletionType.VARIABLE:
        var_name = prefix[1:]  # Remove $ prefix
        return f"compgen -v {quote([var_name])} 2>/dev/null"
    elif completion_type == CompletionType.FILE:
        return f"compgen -f {quote([prefix])} 2>/dev/null | head -{MAX_SHELL_COMPLETIONS}"
    else:
        return f"compgen -c {quote([prefix])} 2>/dev/null | head -{MAX_SHELL_COMPLETIONS}"


def get_zsh_completion_command(prefix: str, completion_type: CompletionType) -> str:
    """Generate zsh completion command."""
    from .shell_quote import quote

    if completion_type == CompletionType.VARIABLE:
        var_name = prefix[1:]
        return f"print -rl -- ${{(k)parameters[(I){quote([var_name + '*'])}]}} 2>/dev/null"
    elif completion_type == CompletionType.FILE:
        return f'for f in {quote([prefix + "*"])}(N[1,{MAX_SHELL_COMPLETIONS}]); do echo "$f "; done 2>/dev/null'
    else:
        return f"print -rl -- ${{(k)commands[(I){quote([prefix + '*'])}]}} 2>/dev/null"


# -----------------------------------------------------------------------------
# Shell execution
# -----------------------------------------------------------------------------

def exec_shell_command(
    command: str,
    timeout_ms: int = SHELL_COMPLETION_TIMEOUT_MS,
    shell: str = "bash",
) -> str:
    """
    Execute a shell command and return stdout.

    Used for shell completions.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""


# -----------------------------------------------------------------------------
# Main completion function
# -----------------------------------------------------------------------------

async def get_shell_completions(
    input_str: str,
    cursor_offset: int,
    abort_signal: Callable[[], bool] | None = None,
) -> list[CompletionResult]:
    """
    Get shell completions for the given input.

    Supports bash and zsh shells.

    Args:
        input_str: The current input string
        cursor_offset: Current cursor position
        abort_signal: Optional callable that returns True to abort

    Returns:
        List of completion suggestions
    """
    shell_type = get_shell_type()
    if shell_type not in (ShellType.BASH, ShellType.ZSH):
        return []

    try:
        ctx = parse_input_context(input_str, cursor_offset)
        if not ctx.prefix:
            return []

        if abort_signal and abort_signal():
            return []

        if shell_type == ShellType.BASH:
            cmd = get_bash_completion_command(ctx.prefix, ctx.completion_type)
        else:
            cmd = get_zsh_completion_command(ctx.prefix, ctx.completion_type)

        stdout = exec_shell_command(cmd)
        completions = [
            line.strip()
            for line in stdout.split("\n")
            if line.strip()
        ][:MAX_SHELL_COMPLETIONS]

        return [
            CompletionResult(
                id=text,
                display_text=text,
                description=None,
                metadata={"completion_type": ctx.completion_type.value},
            )
            for text in completions
        ]
    except Exception:
        return []
