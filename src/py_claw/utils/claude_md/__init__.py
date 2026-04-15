"""
Claude.md file processing utility.

Handles loading and processing of CLAUDE.md files for context injection.
Files are loaded in the following order of priority:

1. Managed memory (e.g., /etc/claude-code/CLAUDE.md) - Global instructions
2. User memory (~/.claude/CLAUDE.md) - Private global instructions
3. Project memory (CLAUDE.md, .claude/CLAUDE.md, .claude/rules/*.md) - Project instructions
4. Local memory (CLAUDE.local.md) - Private project-specific instructions

Supports @include directive for including other files.
"""
from __future__ import annotations

from .service import (
    MAX_MEMORY_CHARACTER_COUNT,
    ClaudeMdFile,
    LoadResult,
    load_claude_md_files,
    load_user_memory,
    load_project_memory,
    load_local_memory,
    resolve_include,
    get_claude_md_for_cwd,
)

__all__ = [
    "MAX_MEMORY_CHARACTER_COUNT",
    "ClaudeMdFile",
    "LoadResult",
    "load_claude_md_files",
    "load_user_memory",
    "load_project_memory",
    "load_local_memory",
    "resolve_include",
    "get_claude_md_for_cwd",
]
