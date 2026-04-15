"""
Shell history completion suggestions.

Provides completions based on shell command history.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# -----------------------------------------------------------------------------
# Shell history files
# -----------------------------------------------------------------------------

def get_shell_history_path() -> Path | None:
    """
    Get the shell history file path for the current shell.

    Checks common locations for bash and zsh history files.
    """
    shell = os.environ.get("SHELL", "")
    home = Path.home()

    if "zsh" in shell:
        # zsh history location depends on HISTFILE setting
        histfile = os.environ.get("HISTFILE")
        if histfile:
            p = Path(histfile)
            if p.exists():
                return p
        # Default zsh history
        return home / ".zsh_history"
    elif "bash" in shell:
        return home / ".bash_history"

    return None


def get_shell_history_suggestions(
    prefix: str,
    limit: int = 10,
) -> list[str]:
    """
    Get shell command history suggestions matching a prefix.

    Returns unique commands from history, most recent first.
    """
    history_path = get_shell_history_path()
    if not history_path or not history_path.exists():
        return []

    suggestions: list[str] = []
    seen: set[str] = set()

    try:
        content = history_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    prefix_lower = prefix.lower()

    for line in reversed(content.splitlines()):
        line = line.strip()
        if not line:
            continue

        # Strip leading spaces and common prefixes
        cmd = line.lstrip()
        if cmd.startswith("#"):
            continue  # Skip comments

        # Check if command starts with prefix
        if cmd.lower().startswith(prefix_lower):
            if cmd not in seen:
                seen.add(cmd)
                suggestions.append(cmd)
                if len(suggestions) >= limit:
                    break

    return suggestions
