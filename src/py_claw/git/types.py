"""
Git types for py-claw runtime.

Based on ClaudeCode-main/src/utils/git.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GitDiffStats:
    """Summary statistics for a git diff."""
    files_count: int = 0
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class PerFileStats:
    """Per-file diff statistics."""
    added: int = 0
    removed: int = 0
    is_binary: bool = False
    is_untracked: bool = False


@dataclass
class StructuredPatchHunk:
    """A hunk from a structured patch."""
    old_start: int = 0
    old_lines: int = 0
    new_start: int = 0
    new_lines: int = 0
    lines: list[str] = field(default_factory=list)


@dataclass
class GitDiffResult:
    """Complete git diff result."""
    stats: GitDiffStats = field(default_factory=GitDiffStats)
    per_file_stats: dict[str, PerFileStats] = field(default_factory=dict)
    hunks: dict[str, list[StructuredPatchHunk]] = field(default_factory=dict)


@dataclass
class ToolUseDiff:
    """Diff for a single file tool use."""
    filename: str = ""
    status: str = ""
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    patch: str | None = None
    repository: str | None = None


@dataclass
class NumstatResult:
    """Result from parsing git diff --numstat."""
    stats: GitDiffStats = field(default_factory=GitDiffStats)
    per_file_stats: dict[str, PerFileStats] = field(default_factory=dict)


@dataclass
class GitFileStatus:
    """Git file status result."""
    tracked: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)


@dataclass
class GitRepoState:
    """Complete git repository state."""
    commit_hash: str = ""
    branch_name: str = ""
    remote_url: str | None = None
    is_head_on_remote: bool = False
    is_clean: bool = True
    worktree_count: int = 0


@dataclass
class PreservedGitState:
    """Preserved git state for issue submission."""
    remote_base_sha: str = ""
    remote_base: str | None = None
    patch: str = ""
    untracked_files: list[str] = field(default_factory=list)
    format_patch: str = ""
    head_sha: str = ""
    branch_name: str = ""


@dataclass
class ParsedRepository:
    """Parsed repository information from remote URL."""
    host: str = ""
    owner: str = ""
    name: str = ""


@dataclass
class GitDiffOptions:
    """Options for git diff operations."""
    include_untracked: bool = True
    include_staged: bool = False
    include_working_tree: bool = True
    max_files: int = 50
    max_diff_size_bytes: int = 1_000_000
    max_lines_per_file: int = 400


# Constants
GIT_TIMEOUT_MS: int = 5000
MAX_FILES: int = 50
MAX_DIFF_SIZE_BYTES: int = 1_000_000
MAX_LINES_PER_FILE: int = 400
MAX_FILES_FOR_DETAILS: int = 500

# Binary file extensions
BINARY_EXTENSIONS: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".a", ".o", ".obj",
    ".pyc", ".pyo", ".class", ".jar", ".war",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".db", ".sqlite", ".mdb",
}
