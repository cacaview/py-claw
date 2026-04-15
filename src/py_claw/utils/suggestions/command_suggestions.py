"""
Command suggestions utilities.

Provides slash command matching, fuzzy search, and suggestion generation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    pass

# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------

@dataclass
class SuggestionItem:
    """A single suggestion item."""

    id: str
    display_text: str
    description: str | None = None
    tag: str | None = None
    metadata: dict | None = None


# -----------------------------------------------------------------------------
# Slash command detection
# -----------------------------------------------------------------------------

@dataclass
class MidInputSlashCommand:
    """A slash command found mid-input (not at start)."""

    token: str  # e.g., "/com"
    start_pos: int  # Position of "/"
    partial_command: str  # e.g., "com"


def find_mid_input_slash_command(
    input_str: str,
    cursor_offset: int,
) -> MidInputSlashCommand | None:
    """
    Find a slash command token that appears mid-input (not at position 0).

    A mid-input slash command is "/" preceded by whitespace, where the cursor
    is at or after the "/".
    """
    # If input starts with "/", this is start-of-input case
    if input_str.startswith("/"):
        return None

    before_cursor = input_str[:cursor_offset]

    # Look for whitespace followed by "/" then optional alphanumeric/dash characters
    match = re.search(r"\s/([a-zA-Z0-9_:-]*)$", before_cursor)
    if not match:
        return None

    slash_pos = match.start() + 1
    text_after_slash = input_str[slash_pos + 1 :]

    # Extract command portion
    command_match = re.match(r"^[a-zA-Z0-9_:-]*", text_after_slash)
    full_command = command_match.group(0) if command_match else ""

    # If cursor is past the command (after a space), don't show ghost text
    if cursor_offset > slash_pos + 1 + len(full_command):
        return None

    return MidInputSlashCommand(
        token="/" + full_command,
        start_pos=slash_pos,
        partial_command=full_command,
    )


def is_command_input(input_str: str) -> bool:
    """Check if input is a command (starts with slash)."""
    return input_str.startswith("/")


def has_command_args(input_str: str) -> bool:
    """
    Check if a command input has arguments.

    A command with just a trailing space is considered to have no arguments.
    """
    if not is_command_input(input_str):
        return False
    if " " not in input_str:
        return False
    if input_str.endswith(" "):
        return False
    return True


def format_command(command: str) -> str:
    """Format a command with proper notation (trailing space)."""
    return f"/{command} "


# -----------------------------------------------------------------------------
# Command name extraction (placeholder - would integrate with commands module)
# -----------------------------------------------------------------------------

def get_command_name(command: dict) -> str:
    """Get the name of a command from its metadata."""
    if isinstance(command, dict):
        return command.get("name", command.get("commandName", ""))
    return ""


# -----------------------------------------------------------------------------
# Simple fuzzy matching
# -----------------------------------------------------------------------------

def _fuzzy_match(query: str, target: str) -> bool:
    """
    Simple fuzzy match: query must appear as a subsequence in target.
    Case-insensitive.
    """
    query = query.lower()
    target = target.lower()
    i = 0
    for char in target:
        if i < len(query) and char == query[i]:
            i += 1
    return i == len(query)


# -----------------------------------------------------------------------------
# Command suggestions
# -----------------------------------------------------------------------------

# Placeholder command registry - would be populated from commands module
_COMMAND_REGISTRY: list[dict] = []


def register_commands(commands: list[dict]) -> None:
    """Register commands for suggestion matching."""
    global _COMMAND_REGISTRY
    _COMMAND_REGISTRY = commands


def generate_command_suggestions(
    input_str: str,
    commands: list[dict] | None = None,
) -> list[SuggestionItem]:
    """
    Generate command suggestions based on input.

    Args:
        input_str: The current input (should start with "/")
        commands: Optional list of command dicts to search

    Returns:
        List of matching suggestions sorted by relevance
    """
    if commands is None:
        commands = _COMMAND_REGISTRY

    if not is_command_input(input_str):
        return []

    # If there are arguments, don't show suggestions
    if has_command_args(input_str):
        return []

    query = input_str[1:].lower().strip()

    # When just typing "/" without additional text
    if not query:
        visible = [c for c in commands if not c.get("isHidden", False)]
        return [
            SuggestionItem(
                id=get_command_name(cmd),
                display_text=format_command(get_command_name(cmd)),
                description=cmd.get("description"),
                tag=cmd.get("kind"),
                metadata=cmd,
            )
            for cmd in visible[:20]
        ]

    # Filter and score commands
    scored: list[tuple[int, SuggestionItem]] = []
    for cmd in commands:
        if cmd.get("isHidden", False):
            continue

        name = get_command_name(cmd)
        name_lower = name.lower()
        desc = (cmd.get("description") or "").lower()

        # Exact prefix match = highest score
        if name_lower == query:
            score = 0
        elif name_lower.startswith(query):
            score = 1
        elif query in name_lower:
            score = 2
        elif _fuzzy_match(query, name_lower):
            score = 3
        elif any(alias.lower().startswith(query) for alias in cmd.get("aliases", [])):
            score = 4
        else:
            continue

        scored.append(
            (
                score,
                SuggestionItem(
                    id=name,
                    display_text=format_command(name),
                    description=cmd.get("description"),
                    tag=cmd.get("kind"),
                    metadata=cmd,
                ),
            )
        )

    # Sort by score, then by name length
    scored.sort(key=lambda x: (x[0], len(x[1].display_text)))
    return [item for _, item in scored[:15]]


def get_best_command_match(
    partial_command: str,
    commands: list[dict] | None = None,
) -> tuple[str, str] | None:
    """
    Find the best matching command for a partial command.

    Returns (suffix, full_command) for inline completion, or None.
    For exact matches (suffix=''), returns the full command name.
    """
    if not partial_command or not commands:
        return None

    query = partial_command.lower()
    for cmd in commands:
        if cmd.get("isHidden", False):
            continue
        name = get_command_name(cmd)
        if name.lower().startswith(query):
            suffix = name[len(partial_command):]
            return suffix, name
    return None


# -----------------------------------------------------------------------------
# Slash command position finding
# -----------------------------------------------------------------------------

def find_slash_command_positions(
    text: str,
) -> list[tuple[int, int]]:
    """
    Find all /command patterns in text for highlighting.

    Returns array of (start, end) positions.
    Requires whitespace or start-of-string before the slash.
    """
    positions: list[tuple[int, int]] = []
    # Match /command patterns preceded by whitespace or start-of-string
    pattern = r"(^|[\s])(\/[a-zA-Z][a-zA-Z0-9:\-_]*)"
    for match in re.finditer(pattern, text):
        preceding = match.group(1) or ""
        command = match.group(2) or ""
        start = match.start() + len(preceding)
        positions.append((start, start + len(command)))
    return positions


# -----------------------------------------------------------------------------
# Apply suggestion
# -----------------------------------------------------------------------------

def apply_command_suggestion(
    suggestion: SuggestionItem | str,
    commands: list[dict],
    on_input_change: Callable[[str], None],
    set_cursor_offset: Callable[[int], None],
    on_submit: Callable[[str], None] | None = None,
) -> None:
    """
    Apply a selected command suggestion to the input.

    Args:
        suggestion: The selected suggestion item or command name string
        commands: Available commands
        on_input_change: Callback to update the input
        set_cursor_offset: Callback to set cursor position
        on_submit: Optional callback when command should be executed
    """
    if isinstance(suggestion, str):
        command_name = suggestion
    else:
        metadata = suggestion.metadata
        if not isinstance(metadata, dict):
            return
        command_name = get_command_name(metadata)

    new_input = format_command(command_name)
    on_input_change(new_input)
    set_cursor_offset(len(new_input))

    if on_submit and suggestion.metadata:
        cmd_type = suggestion.metadata.get("type")
        arg_names = suggestion.metadata.get("argNames", [])
        if cmd_type != "prompt" or not arg_names:
            on_submit(new_input)
