"""
Claude.md file processing service implementation.

Handles loading and processing of CLAUDE.md files for context injection.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Recommended max character count for a memory file
MAX_MEMORY_CHARACTER_COUNT = 40_000

# Text file extensions allowed for @include directives
TEXT_FILE_EXTENSIONS = {".md", ".txt", ".text", ".rst", ".adoc"}


@dataclass
class ClaudeMdFile:
    """Represents a loaded CLAUDE.md file."""
    path: str
    content: str
    memory_type: str  # "managed" | "user" | "project" | "local"
    priority: int  # Higher priority = loaded later = higher precedence
    char_count: int = 0

    def __post_init__(self) -> None:
        if self.char_count == 0:
            self.char_count = len(self.content)


@dataclass
class LoadResult:
    """Result of loading CLAUDE.md files."""
    files: list[ClaudeMdFile]
    total_char_count: int
    warnings: list[str] = field(default_factory=list)

    @property
    def combined_content(self) -> str:
        """Combine all file contents with separator."""
        return "\n\n---\n\n".join(f.content for f in self.files)


def _get_config_home() -> str:
    """Get Claude config home directory."""
    if os.name == "nt":
        return os.environ.get("LOCALAPPDATA", str(Path.home())) + "/claude"
    return os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")) + "/claude"


def _get_home_dir() -> str:
    """Get user home directory."""
    return str(Path.home())


def _is_text_file(path: str) -> bool:
    """Check if a file is a text file based on extension."""
    return Path(path).suffix.lower() in TEXT_FILE_EXTENSIONS


def _normalize_path(path: str) -> str:
    """Normalize a path for comparison."""
    return os.path.normpath(os.path.expanduser(path))


def _find_files_in_directory(directory: str, patterns: list[str]) -> list[str]:
    """Find files in a directory matching given patterns."""
    if not os.path.isdir(directory):
        return []

    results: list[str] = []
    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.endswith(pat) or file == pat.lstrip("*") for pat in patterns):
                results.append(os.path.join(root, file))
    return results


def _find_project_memory_files(cwd: str) -> list[str]:
    """Find project memory files by traversing up from cwd."""
    files: list[tuple[str, str]] = []  # (path, search_root)

    # Patterns to search for
    patterns = ["CLAUDE.md", ".claude/CLAUDE.md"]

    current = Path(cwd)
    # Stop at filesystem root or user home
    while current != current.parent and current != Path(_get_home_dir()):
        # Check for CLAUDE.md in current directory
        claude_md = current / "CLAUDE.md"
        if claude_md.is_file():
            files.append((str(claude_md), str(current)))

        # Check for .claude/ directory
        claude_dir = current / ".claude"
        if claude_dir.is_dir():
            # Check for .claude/CLAUDE.md
            nested = claude_dir / "CLAUDE.md"
            if nested.is_file():
                files.append((str(nested), str(current)))

            # Check for .claude/rules/*.md
            rules_dir = claude_dir / "rules"
            if rules_dir.is_dir():
                for f in rules_dir.iterdir():
                    if f.is_file() and f.suffix == ".md":
                        files.append((str(f), str(current)))

        current = current.parent

    return [f[0] for f in files]


def _load_file_content(path: str) -> str | None:
    """Load content from a file, respecting size limits."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            if len(content) > MAX_MEMORY_CHARACTER_COUNT * 2:
                # Truncate very large files
                content = content[:MAX_MEMORY_CHARACTER_COUNT * 2]
                # Try to truncate at a paragraph boundary
                last_newline = content.rfind("\n\n")
                if last_newline > MAX_MEMORY_CHARACTER_COUNT:
                    content = content[:last_newline] + "\n\n[Content truncated due to size]"
            return content
    except (OSError, UnicodeDecodeError):
        return None


def _parse_include_directives(content: str, base_path: str, processed: set[str] | None = None) -> str:
    """
    Parse @include directives in content and expand them.

    Syntax: @path, @./relative/path, @~/home/path, @/absolute/path
    """
    if processed is None:
        processed = set()

    # Normalize base path
    base_dir = os.path.dirname(base_path)

    # Pattern to match @include directives
    # Matches @path, @./path, @~/path, @/path
    include_pattern = r"@((?:\./|/~|/\.\./|/)[^\s\n]*)"

    def replace_include(match: re.Match) -> str:
        include_path = match.group(1)

        # Expand ~ to home directory
        if include_path.startswith("~/"):
            include_path = os.path.join(_get_home_dir(), include_path[2:])
        # Handle relative paths
        elif include_path.startswith("./"):
            include_path = os.path.join(base_dir, include_path[2:])
        # Handle parent paths
        elif include_path.startswith("../"):
            include_path = os.path.normpath(os.path.join(base_dir, include_path))
        # Absolute paths are used as-is

        # Normalize and check for circular references
        normalized = _normalize_path(include_path)
        if normalized in processed or not os.path.isfile(normalized):
            return ""  # Skip non-existent or already processed files

        processed.add(normalized)

        # Load and expand the included file
        included_content = _load_file_content(normalized)
        if included_content:
            # Recursively process includes in the included file
            return _parse_include_directives(included_content, normalized, processed)

        return ""

    # Only process includes in text nodes (not in code blocks)
    # Simple approach: process all but be careful about false positives
    result = re.sub(include_pattern, replace_include, content)
    return result


def load_user_memory() -> list[ClaudeMdFile]:
    """Load user memory file (~/.claude/CLAUDE.md)."""
    home = _get_home_dir()
    config_home = _get_config_home()

    files: list[ClaudeMdFile] = []
    priority = 0

    # User memory: ~/.claude/CLAUDE.md
    user_memory = os.path.join(config_home, "CLAUDE.md")
    if os.path.isfile(user_memory):
        content = _load_file_content(user_memory)
        if content:
            files.append(ClaudeMdFile(
                path=user_memory,
                content=content,
                memory_type="user",
                priority=priority,
            ))
            priority += 1

    return files


def load_project_memory(cwd: str) -> list[ClaudeMdFile]:
    """Load project memory files (CLAUDE.md, .claude/CLAUDE.md, .claude/rules/*.md)."""
    files: list[ClaudeMdFile] = []
    priority = 0

    # Find all project memory files
    project_files = _find_project_memory_files(cwd)

    for file_path in project_files:
        content = _load_file_content(file_path)
        if content:
            # Check if this is a local memory file
            is_local = os.path.basename(file_path) == "CLAUDE.local.md"

            files.append(ClaudeMdFile(
                path=file_path,
                content=content,
                memory_type="local" if is_local else "project",
                priority=priority,
            ))
            priority += 1

    return files


def load_local_memory(cwd: str) -> list[ClaudeMdFile]:
    """Load local memory files (CLAUDE.local.md in project root)."""
    files: list[ClaudeMdFile] = []

    # Look for CLAUDE.local.md in cwd
    local_memory = os.path.join(cwd, "CLAUDE.local.md")
    if os.path.isfile(local_memory):
        content = _load_file_content(local_memory)
        if content:
            files.append(ClaudeMdFile(
                path=local_memory,
                content=content,
                memory_type="local",
                priority=0,  # Loaded last
            ))

    return files


def load_managed_memory() -> list[ClaudeMdFile]:
    """Load managed memory files (/etc/claude-code/CLAUDE.md)."""
    files: list[ClaudeMdFile] = []

    # Managed memory locations
    managed_paths = [
        "/etc/claude-code/CLAUDE.md",  # Linux
        "/usr/local/etc/claude-code/CLAUDE.md",  # macOS Homebrew
    ]

    priority = 0
    for managed_path in managed_paths:
        if os.path.isfile(managed_path):
            content = _load_file_content(managed_path)
            if content:
                files.append(ClaudeMdFile(
                    path=managed_path,
                    content=content,
                    memory_type="managed",
                    priority=priority,
                ))
                priority += 1

    return files


def resolve_include(path: str, base_path: str | None = None) -> str | None:
    """
    Resolve an @include path to actual file content.

    Args:
        path: The path from @include directive
        base_path: Base path for relative resolution

    Returns:
        File content or None if not found
    """
    if base_path:
        base_dir = os.path.dirname(base_path)
    else:
        base_dir = os.getcwd()

    # Expand ~ to home directory
    if path.startswith("~/"):
        full_path = os.path.join(_get_home_dir(), path[2:])
    # Handle relative paths
    elif path.startswith("./"):
        full_path = os.path.join(base_dir, path[2:])
    elif path.startswith("../"):
        full_path = os.path.normpath(os.path.join(base_dir, path))
    else:
        full_path = path

    # Normalize and check existence
    normalized = _normalize_path(full_path)
    if not os.path.isfile(normalized):
        return None

    if not _is_text_file(normalized):
        return None  # Don't include binary files

    return _load_file_content(normalized)


def load_claude_md_files(cwd: str | None = None, include_local: bool = True) -> LoadResult:
    """
    Load all CLAUDE.md files for a given working directory.

    Files are loaded in order of increasing priority, so later files
    override earlier ones when combined.

    Args:
        cwd: Working directory to search from
        include_local: Whether to include CLAUDE.local.md files

    Returns:
        LoadResult with all loaded files and metadata
    """
    if cwd is None:
        cwd = os.getcwd()

    all_files: list[ClaudeMdFile] = []
    warnings: list[str] = []

    # Load in priority order (lower priority first)
    # Managed memory (lowest priority)
    all_files.extend(load_managed_memory())

    # User memory
    all_files.extend(load_user_memory())

    # Project memory (CLAUDE.md, .claude/CLAUDE.md, .claude/rules/*.md)
    all_files.extend(load_project_memory(cwd))

    # Local memory (highest priority, unless disabled)
    if include_local:
        all_files.extend(load_local_memory(cwd))

    # Process @include directives in each file
    processed_files: list[ClaudeMdFile] = []
    for f in all_files:
        try:
            expanded_content = _parse_include_directives(f.content, f.path)
            f.content = expanded_content
            f.char_count = len(expanded_content)
            processed_files.append(f)
        except Exception as e:
            warnings.append(f"Error processing {f.path}: {e}")

    # Calculate total character count
    total_chars = sum(f.char_count for f in processed_files)

    # Check for oversized content
    if total_chars > MAX_MEMORY_CHARACTER_COUNT * 10:
        warnings.append(
            f"Total CLAUDE.md content ({total_chars} chars) exceeds recommended limit"
        )

    return LoadResult(
        files=processed_files,
        total_char_count=total_chars,
        warnings=warnings,
    )


def get_claude_md_for_cwd(cwd: str | None = None) -> str:
    """
    Get combined CLAUDE.md content for a working directory.

    This is a convenience function that loads all CLAUDE.md files
    and combines their content.

    Args:
        cwd: Working directory to search from

    Returns:
        Combined CLAUDE.md content
    """
    result = load_claude_md_files(cwd)
    return result.combined_content
