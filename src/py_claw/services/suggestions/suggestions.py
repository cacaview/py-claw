"""Suggestions utilities - command/shell_history/directory suggestions.

Based on ClaudeCode-main/src/utils/suggestions/
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from typing import Protocol

    class LRUCacheProtocol(Protocol):
        """LRU Cache interface."""

        def get(self, key: str) -> Any | None: ...
        def set(self, key: str, value: Any) -> None: ...
        def clear(self) -> None: ...


# Types
@dataclass
class DirectoryEntry:
    """A directory entry for completion."""

    name: str
    path: str
    type: str = "directory"


@dataclass
class PathEntry:
    """A path entry (file or directory) for completion."""

    name: str
    path: str
    type: str = "directory"  # 'directory' | 'file'


class PathCompletionOptions(TypedDict, total=False):
    """Options for path completion."""

    base_path: str | None
    max_results: int | None
    include_files: bool | None
    include_hidden: bool | None


@dataclass
class CommandSuggestionItem:
    """A command suggestion item."""

    id: str
    display_text: str
    description: str | None = None
    tag: str | None = None
    metadata: dict | None = None


@dataclass
class MidInputSlashCommand:
    """Represents a slash command found mid-input."""

    token: str
    start_pos: int
    partial_command: str


@dataclass
class CommandMatch:
    """Result of command match."""

    suffix: str
    full_command: str


# Cache configuration
_CACHE_SIZE = 500
_CACHE_TTL = 5 * 60 * 1000  # 5 minutes


class _LRUCache:
    """Simple LRU cache implementation."""

    def __init__(self, max_size: int = 500, ttl: int = 300000):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None
        value, timestamp = self._cache[key]
        if datetime.now().timestamp() - timestamp > self._ttl:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        if len(self._cache) >= self._max_size:
            # Remove oldest entries
            oldest_keys = sorted(
                self._cache.keys(), key=lambda k: self._cache[k][1]
            )[:10]
            for k in oldest_keys:
                del self._cache[k]
        self._cache[key] = (value, datetime.now().timestamp())

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()


# Initialize LRU caches
_directory_cache = _LRUCache(max_size=_CACHE_SIZE, ttl=_CACHE_TTL)
_path_cache = _LRUCache(max_size=_CACHE_SIZE, ttl=_CACHE_TTL)


# Shell history cache
_shell_history_cache: list[str] | None = None
_shell_history_cache_timestamp: float = 0
_SHELL_HISTORY_CACHE_TTL_MS = 60000  # 60 seconds


def parse_partial_path(
    partial_path: str, base_path: str | None = None
) -> tuple[str, str]:
    """Parse a partial path into directory and prefix components.

    Returns:
        Tuple of (directory, prefix)
    """
    if not partial_path:
        directory = base_path or os.getcwd()
        return (directory, "")

    # Expand the path
    if partial_path.startswith("~"):
        partial_path = os.path.expanduser(partial_path)
    elif not partial_path.startswith("/") and not partial_path.startswith("."):
        partial_path = os.path.join(base_path or os.getcwd(), partial_path)

    # Normalize path
    partial_path = os.path.normpath(partial_path)

    # If path ends with separator, treat as directory with no prefix
    if partial_path.endswith(os.sep) or partial_path.endswith("/"):
        return (partial_path.rstrip(os.sep + "/"), "")

    # Split into directory and prefix
    directory = os.path.dirname(partial_path)
    prefix = os.path.basename(partial_path)

    return (directory, prefix)


def is_path_like_token(token: str) -> bool:
    """Check if a string looks like a path."""
    return (
        token.startswith("~/")
        or token.startswith("/")
        or token.startswith("./")
        or token.startswith("../")
        or token == "~"
        or token == "."
        or token == ".."
    )


async def scan_directory(dir_path: str) -> list[DirectoryEntry]:
    """Scan a directory and return subdirectories.

    Uses LRU cache to avoid repeated filesystem calls.
    """
    cached = _directory_cache.get(dir_path)
    if cached is not None:
        return cached

    try:
        entries = os.listdir(dir_path)
        directories = [
            DirectoryEntry(
                name=name,
                path=os.path.join(dir_path, name),
                type="directory",
            )
            for name in entries
            if os.path.isdir(os.path.join(dir_path, name))
            and not name.startswith(".")
        ]
        directories = sorted(directories, key=lambda e: e.name)[:100]

        _directory_cache.set(dir_path, directories)
        return directories
    except Exception:
        return []


async def get_directory_completions(
    partial_path: str, options: PathCompletionOptions | None = None
) -> list[CommandSuggestionItem]:
    """Get directory completion suggestions.

    Args:
        partial_path: The partial path to complete
        options: Completion options including base_path and max_results
    """
    if options is None:
        options = {}

    base_path = options.get("base_path") or os.getcwd()
    max_results = options.get("max_results", 10)

    directory, prefix = parse_partial_path(partial_path, base_path)
    entries = await scan_directory(directory)

    prefix_lower = prefix.lower()
    matches = [e for e in entries if e.name.lower().startswith(prefix_lower)][
        :max_results
    ]

    return [
        CommandSuggestionItem(
            id=entry.path,
            display_text=entry.name + "/",
            description="directory",
            metadata={"type": "directory"},
        )
        for entry in matches
    ]


def clear_directory_cache() -> None:
    """Clear the directory cache."""
    _directory_cache.clear()


async def scan_directory_for_paths(
    dir_path: str, include_hidden: bool = False
) -> list[PathEntry]:
    """Scan a directory for both files and subdirectories.

    Uses LRU cache to avoid repeated filesystem calls.
    """
    cache_key = f"{dir_path}:{include_hidden}"
    cached = _path_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        entries = os.listdir(dir_path)
        paths: list[PathEntry] = []

        for name in entries:
            if not include_hidden and name.startswith("."):
                continue
            full_path = os.path.join(dir_path, name)
            if os.path.isdir(full_path):
                paths.append(PathEntry(name=name, path=full_path, type="directory"))
            elif os.path.isfile(full_path):
                paths.append(PathEntry(name=name, path=full_path, type="file"))

        # Sort directories first, then alphabetically
        paths.sort(key=lambda e: (0 if e.type == "directory" else 1, e.name))
        paths = paths[:100]

        _path_cache.set(cache_key, paths)
        return paths
    except Exception:
        return []


async def get_path_completions(
    partial_path: str, options: PathCompletionOptions | None = None
) -> list[CommandSuggestionItem]:
    """Get path completion suggestions for files and directories."""
    if options is None:
        options = {}

    base_path = options.get("base_path") or os.getcwd()
    max_results = options.get("max_results", 10)
    include_files = options.get("include_files", True)
    include_hidden = options.get("include_hidden", False)

    directory, prefix = parse_partial_path(partial_path, base_path)
    entries = await scan_directory_for_paths(directory, include_hidden)

    prefix_lower = prefix.lower()
    matches = [
        entry
        for entry in entries
        if (include_files or entry.type == "directory")
        and entry.name.lower().startswith(prefix_lower)
    ][:max_results]

    # Construct relative path based on original partialPath
    has_separator = "/" in partial_path or os.sep in partial_path
    dir_portion = ""
    if has_separator:
        last_sep = max(partial_path.rfind("/"), partial_path.rfind(os.sep))
        dir_portion = partial_path[: last_sep + 1]

    if dir_portion.startswith("./"):
        dir_portion = dir_portion[2:]

    return [
        CommandSuggestionItem(
            id=full_path,
            display_text=full_path + ("/" if entry.type == "directory" else ""),
            metadata={"type": entry.type},
        )
        for entry in matches
        for full_path in [dir_portion + entry.name]
    ]


def clear_path_cache() -> None:
    """Clear both directory and path caches."""
    _directory_cache.clear()
    _path_cache.clear()


# Command suggestions


def is_command_input(input: str) -> bool:
    """Check if input is a command (starts with slash)."""
    return input.startswith("/")


def get_command_args(input: str) -> bool:
    """Check if a command input has arguments.

    A command with just a trailing space is considered to have no arguments.
    """
    if not is_command_input(input):
        return False
    if " " not in input:
        return False
    return not input.endswith(" ")


def format_command(command: str) -> str:
    """Format a command with proper notation."""
    return f"/{command} "


def find_mid_input_slash_command(
    input: str, cursor_offset: int
) -> MidInputSlashCommand | None:
    """Find a slash command token that appears mid-input.

    Args:
        input: The full input string
        cursor_offset: The current cursor position

    Returns:
        MidInputSlashCommand if found, None otherwise
    """
    # If input starts with "/", this is start-of-input case (handled elsewhere)
    if input.startswith("/"):
        return None

    before_cursor = input[:cursor_offset]

    # Find the last "/" preceded by whitespace
    match = re.search(r"\s/([a-zA-Z0-9_:-]*)$", before_cursor)
    if not match or match.start() == -1:
        return None

    slash_pos = match.start() + 1
    text_after_slash = input[slash_pos + 1 :]

    # Extract the command portion (until whitespace or end)
    command_match = re.match(r"^[a-zA-Z0-9_:-]*", text_after_slash)
    full_command = command_match.group(0) if command_match else ""

    # If cursor is past the command, don't show ghost text
    if cursor_offset > slash_pos + 1 + len(full_command):
        return None

    return MidInputSlashCommand(
        token="/" + full_command,
        start_pos=slash_pos,
        partial_command=full_command,
    )


def get_best_command_match(
    partial_command: str, commands: list[dict]
) -> CommandMatch | None:
    """Find the best matching command for a partial command string.

    Args:
        partial_command: The partial command typed by the user (without "/")
        commands: Available commands

    Returns:
        CommandMatch with suffix and full_command, or None
    """
    if not partial_command:
        return None

    query = partial_command.lower()
    for cmd in commands:
        name = cmd.get("name", "")
        if name.lower().startswith(query):
            suffix = name[len(partial_command) :]
            if suffix:
                return CommandMatch(suffix=suffix, full_command=name)

    return None


def generate_command_suggestions(
    input: str, commands: list[dict]
) -> list[CommandSuggestionItem]:
    """Generate command suggestions based on input.

    Args:
        input: The command input (starting with /)
        commands: Available commands

    Returns:
        List of CommandSuggestionItem
    """
    if not is_command_input(input):
        return []

    if get_command_args(input):
        return []

    query = input[1:].lower().strip()

    if query == "":
        # Just "/" - show all visible commands
        visible = [cmd for cmd in commands if not cmd.get("is_hidden", False)]
        return [
            CommandSuggestionItem(
                id=str(i),
                display_text="/" + cmd.get("name", ""),
                description=cmd.get("description", ""),
                metadata=cmd,
            )
            for i, cmd in enumerate(visible)
        ]

    # Filter by query
    query_lower = query.lower()
    matches = []
    for cmd in commands:
        name = cmd.get("name", "")
        if name.lower().startswith(query_lower):
            matches.append(cmd)

    return [
        CommandSuggestionItem(
            id=str(i),
            display_text="/" + cmd.get("name", ""),
            description=cmd.get("description", ""),
            metadata=cmd,
        )
        for i, cmd in enumerate(matches)
    ]


def find_slash_command_positions(
    text: str,
) -> list[tuple[int, int]]:
    """Find all /command patterns in text for highlighting.

    Returns:
        List of (start, end) positions.
    """
    positions: list[tuple[int, int]] = []
    # Match /command patterns preceded by whitespace or start-of-string
    pattern = r"(^|\s)(/[a-zA-Z][a-zA-Z0-9:\-_]*)"
    for match in re.finditer(pattern, text):
        preceding_char = match.group(1) or ""
        command_name = match.group(2) or ""
        start = match.start() + len(preceding_char)
        positions.append((start, start + len(command_name)))
    return positions


# Shell history completion


@dataclass
class ShellHistoryMatch:
    """Result of shell history completion lookup."""

    full_command: str
    suffix: str


def clear_shell_history_cache() -> None:
    """Clear the shell history cache."""
    global _shell_history_cache, _shell_history_cache_timestamp
    _shell_history_cache = None
    _shell_history_cache_timestamp = 0


async def get_shell_history_completion(
    input: str,
) -> ShellHistoryMatch | None:
    """Find the best matching shell command from history.

    Args:
        input: The current user input

    Returns:
        ShellHistoryMatch or None if no match
    """
    import time

    if not input or len(input) < 2:
        return None

    trimmed_input = input.strip()
    if not trimmed_input:
        return None

    global _shell_history_cache, _shell_history_cache_timestamp
    now = time.time() * 1000

    # Return cached result if still fresh
    if (
        _shell_history_cache is not None
        and now - _shell_history_cache_timestamp < _SHELL_HISTORY_CACHE_TTL_MS
    ):
        commands = _shell_history_cache
    else:
        # Placeholder - would need to read from history
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
