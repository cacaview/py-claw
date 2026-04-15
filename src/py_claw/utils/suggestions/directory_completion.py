"""
Directory completion suggestions.

Provides file and directory path completions.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# -----------------------------------------------------------------------------
# Directory completion
# -----------------------------------------------------------------------------

MAX_COMPLETIONS = 15


def get_directory_completions(
    prefix: str,
    cwd: str | None = None,
    limit: int = MAX_COMPLETIONS,
) -> list[str]:
    """
    Get directory and file completions for a path prefix.

    Handles:
    - Relative paths (./, ../)
    - Home directory expansion (~)
    - Absolute paths

    Returns completions with trailing "/" for directories.
    """
    if not prefix:
        return []

    if cwd is None:
        cwd = os.getcwd()

    # Expand home directory
    if prefix.startswith("~"):
        prefix = str(Path.home() / prefix[1:])
    elif prefix.startswith("./") or prefix.startswith("../"):
        prefix = str(Path(cwd) / prefix)

    path = Path(prefix)
    parent = path.parent if path.parent != path else Path(".")
    partial_name = path.name

    completions: list[str] = []

    try:
        entries = list(parent.iterdir())
    except OSError:
        return []

    for entry in entries:
        try:
            name = entry.name
            if not name.startswith(partial_name):
                continue

            # Build full path
            if prefix.startswith("./"):
                full = f"./{name}"
            elif prefix.startswith("../"):
                full = f"../{name}"
            elif prefix.startswith("~"):
                home = str(Path.home())
                full = f"~/{entry.relative_to(home)}"
            else:
                full = name

            # Add trailing slash for directories
            if entry.is_dir():
                full += "/"

            completions.append(full)
        except OSError:
            continue

    # Sort: directories first, then alphabetical
    completions.sort(key=lambda x: (0 if x.endswith("/") else 1, x.lower()))
    return completions[:limit]
