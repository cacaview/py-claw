"""
Typeahead — Unified suggestion engine for PromptInput.

Orchestrates slash commands, path completions, and shell history
into a single suggestion pipeline, matching the behavior of
ClaudeCode-main/src/hooks/useTypeahead.tsx.

Provides:
- SuggestionEngine: detects type, fetches completions, returns unified list
- Suggestion: unified suggestion item dataclass
- SuggestionType: enum for suggestion categories
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from py_claw.utils.suggestions.command_suggestions import (
    generate_command_suggestions,
    get_best_command_match,
    is_command_input,
    has_command_args,
)
from py_claw.utils.suggestions.directory_completion import get_directory_completions
from py_claw.utils.suggestions.shell_history_completion import get_shell_history_suggestions


# ─────────────────────────────── Types ───────────────────────────────────────


class SuggestionType(str, Enum):
    """Category of a suggestion item."""

    COMMAND = "command"
    PATH = "path"
    SHELL_HISTORY = "shell_history"
    SHELL_COMPLETION = "shell_completion"
    AGENT = "agent"
    CHANNEL = "channel"
    MID_INPUT_SLASH = "mid_input_slash"


@dataclass(slots=True, frozen=True)
class CommandItem:
    """Type-safe command item for the suggestion engine.

    Replaces the dict-based command_items used previously.
    """

    name: str
    description: str
    argument_hint: str = ""
    kind: str = ""  # "local" | "prompt"
    is_hidden: bool = False
    aliases: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CommandItem:
        """Construct from a dict (e.g. from CommandDefinition.to_slash_command())."""
        return cls(
            name=str(d.get("name", "")),
            description=str(d.get("description", "") or ""),
            argument_hint=str(d.get("argumentHint", "") or ""),
            kind=str(d.get("kind", "") or ""),
            is_hidden=bool(d.get("isHidden", False)),
            aliases=tuple(d.get("aliases") or []) if d.get("aliases") else (),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert back to dict for compatibility with SuggestionItem.metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "argumentHint": self.argument_hint,
            "kind": self.kind,
            "isHidden": self.is_hidden,
            "aliases": list(self.aliases),
        }


@dataclass(slots=True)
class Suggestion:
    """Unified suggestion item for PromptInput.

    Attributes:
        type: Category of the suggestion.
        id: Unique identifier (e.g. command name, file path).
        display_text: Text shown in the suggestion list.
        description: Secondary description shown below display_text.
        suffix: The completion suffix for inline ghost text (e.g. "lp" for "/he" → "/help").
        tag: Short label shown alongside display_text (e.g. "cmd", "file").
        metadata: Additional data passed through from the underlying source.
        score: Relevance score (lower = better). Used for sorting.
    """

    type: SuggestionType
    id: str
    display_text: str
    description: str = ""
    suffix: str = ""
    tag: str = ""
    metadata: dict[str, Any] | None = None
    score: int = 0

    # For compatibility with the PromptInput suggestion_items reactive
    @property
    def name(self) -> str:
        return self.id

    @property
    def display_text_stripped(self) -> str:
        return self.display_text.strip()


# ─────────────────────────── SuggestionEngine ──────────────────────────────────


class SuggestionEngine:
    """
    Unified suggestion engine coordinating slash commands, paths, and shell history.

    Given the current input text and cursor position, detects which type of
    suggestions to provide and returns a unified list of ``Suggestion`` objects.

    This replaces scattered util functions with a single entry point consumable
    by both the inline ghost-text suggester and the suggestion list renderer.
    """

    def __init__(
        self,
        command_items: list[CommandItem] | None = None,
        max_results: int = 100,
        teammates: dict | None = None,
        agent_names: dict | None = None,
    ) -> None:
        self._command_items: list[CommandItem] = list(command_items or [])
        self._max_results = max_results
        self._teammates = teammates or {}
        self._agent_names = agent_names or {}

    def set_team_context(self, teammates: dict, agent_names: dict) -> None:
        """Update team context for @agent suggestions."""
        self._teammates = teammates
        self._agent_names = agent_names

    def set_command_items(self, items: list[CommandItem]) -> None:
        """Update the command registry."""
        self._command_items = list(items)

    def detect_type(self, text: str, cursor_offset: int) -> SuggestionType | None:
        """
        Detect which type of suggestion the user wants based on input text.

        Priority:
        1. Mid-input slash command (e.g. "see /bug" with cursor after "/bu")
        2. Start-of-input slash — COMMAND if a command matches, else PATH
        3. Path-like token (e.g. "~/", "./", "../")
        4. @-mention agent suggestion (teammates)
        5. #-mention channel suggestion (Slack MCP)
        6. Shell completion (bare text that looks like a shell command token)
        7. Shell history match (for bare text >= 2 chars)
        """
        if not text:
            return None

        # Case 1: Mid-input slash — "/" preceded by whitespace, not at start
        if not text.startswith("/") and cursor_offset > 0:
            before = text[:cursor_offset]
            if re.search(r"\s/([a-zA-Z0-9_:-]*)$", before):
                return SuggestionType.MID_INPUT_SLASH

        # Case 2: Start-of-input slash — distinguish command vs path
        if is_command_input(text) and not has_command_args(text):
            # Check if any command matches — if so, treat as COMMAND
            partial = text[1:].strip()
            if partial:
                match = get_best_command_match(partial, self._command_items)
                if match:
                    return SuggestionType.COMMAND
            # No partial command match: could be a path starting with /
            if self._is_path_like(text):
                return SuggestionType.PATH
            # Bare "/" with no partial — show commands
            if not partial:
                return SuggestionType.COMMAND
            return None

        # Case 3: Path-like token (~/, ./, ../)
        if self._is_path_like(text):
            return SuggestionType.PATH

        trimmed = text.strip()

        # Case 4: @-mention agent — e.g. "@" or "@foo"
        if re.search(r"(^|\s)@([\w-]*)$", trimmed):
            return SuggestionType.AGENT

        # Case 5: #-mention channel — e.g. "#" or "#general"
        if re.search(r"(^|\s)#([a-z0-9][a-z0-9_-]*)$", trimmed):
            return SuggestionType.CHANNEL

        # Case 6: Shell completion — bare text that looks like a shell command
        # Only triggers when text is short (compgen for subcommands/flags)
        if trimmed and len(trimmed) <= 3 and not trimmed.startswith("/"):
            if self._is_shell_command_token(trimmed):
                return SuggestionType.SHELL_COMPLETION

        # Case 7: Shell history — bare text >= 2 chars
        if len(trimmed) >= 2 and not trimmed.startswith("/"):
            return SuggestionType.SHELL_HISTORY

        return None

    def _is_shell_command_token(self, text: str) -> bool:
        """Check if text looks like a shell command token (alphanumeric, dashes, etc)."""
        return bool(text) and text.isalnum()

    async def get_suggestions_async(
        self,
        text: str,
        cursor_offset: int,
        abort_signal: Callable[[], bool] | None = None,
    ) -> list[Suggestion]:
        """Async version of get_suggestions that includes shell completions.

        Args:
            text: The current input text
            cursor_offset: Current cursor position
            abort_signal: Optional callable that returns True to abort
        """
        sug_type = self.detect_type(text, cursor_offset)

        if sug_type == SuggestionType.MID_INPUT_SLASH:
            return self._get_mid_input_suggestions(text, cursor_offset)
        if sug_type == SuggestionType.COMMAND:
            return self._get_command_suggestions(text)
        if sug_type == SuggestionType.PATH:
            return self._get_path_suggestions(text)
        if sug_type == SuggestionType.SHELL_HISTORY:
            return self._get_shell_history_suggestions(text)
        if sug_type == SuggestionType.SHELL_COMPLETION:
            return await self._get_shell_completion_suggestions(text, cursor_offset, abort_signal)
        if sug_type == SuggestionType.AGENT:
            return self._get_agent_suggestions(text)
        if sug_type == SuggestionType.CHANNEL:
            return self._get_channel_suggestions(text)

        return []

    def get_suggestions(
        self,
        text: str,
        cursor_offset: int,
    ) -> list[Suggestion]:
        """
        Get all matching suggestions for the given input.

        Returns suggestions sorted by relevance (best first).
        """
        sug_type = self.detect_type(text, cursor_offset)

        if sug_type == SuggestionType.MID_INPUT_SLASH:
            return self._get_mid_input_suggestions(text, cursor_offset)
        if sug_type == SuggestionType.COMMAND:
            return self._get_command_suggestions(text)
        if sug_type == SuggestionType.PATH:
            return self._get_path_suggestions(text)
        if sug_type == SuggestionType.SHELL_HISTORY:
            return self._get_shell_history_suggestions(text)

        return []

    def get_best_suffix(self, text: str, cursor_offset: int) -> str:
        """
        Get the best ghost-text suffix for inline completion.

        Returns the suffix to append after the cursor (e.g. "lp" for "/he").
        """
        sug_type = self.detect_type(text, cursor_offset)

        if sug_type in (SuggestionType.COMMAND, SuggestionType.MID_INPUT_SLASH):
            partial = self._get_command_partial(text, cursor_offset)
            if not partial:
                return ""
            match = get_best_command_match(partial, self._command_items)
            if match:
                suffix, _ = match
                return suffix
        elif sug_type == SuggestionType.PATH:
            suffix = self._get_path_suffix(text)
            if suffix:
                return suffix

        return ""

    # ── internal helpers ──────────────────────────────────────────────────────

    def _is_path_like(self, text: str) -> bool:
        """Check if text looks like a path prefix."""
        if not text:
            return False
        # Bare "/" alone is not a path — it's the command trigger
        if text == "/":
            return False
        return (
            text.startswith("~/")
            or text.startswith("/")
            or text.startswith("./")
            or text.startswith("../")
        )

    def _get_command_partial(self, text: str, cursor_offset: int) -> str:
        """Extract the partial command from input text."""
        if is_command_input(text):
            return text[1:].strip()
        # Mid-input: find the slash command
        before = text[:cursor_offset]
        match = re.search(r"/([a-zA-Z0-9_:-]*)$", before)
        if match:
            return match.group(1)
        return ""

    def _get_command_suggestions(self, text: str) -> list[Suggestion]:
        """Generate slash command suggestions."""
        if has_command_args(text):
            return []

        raw = generate_command_suggestions(text, self._command_items)
        return [
            Suggestion(
                type=SuggestionType.COMMAND,
                id=item.id,
                display_text=item.display_text,
                description=item.description or "",
                tag=item.tag or "cmd",
                metadata=item.metadata,
                suffix=self._get_command_suffix(item),
                score=i,
            )
            for i, item in enumerate(raw[: self._max_results])
        ]

    def _get_command_suffix(self, item: object) -> str:
        """Extract the ghost-text suffix from a SuggestionItem."""
        name = ""
        if hasattr(item, "metadata") and isinstance(getattr(item, "metadata", None), dict):
            name = str(getattr(item, "metadata", {}).get("name") or "")
        if not name:
            name = getattr(item, "id", "") or getattr(item, "display_text", "").strip().lstrip("/")
        partial = getattr(item, "display_text", "").strip().lstrip("/").rstrip()
        if name and partial and name != partial:
            suffix = name[len(partial):]
            if suffix:
                return suffix
        return ""

    def _get_mid_input_suggestions(
        self, text: str, cursor_offset: int
    ) -> list[Suggestion]:
        """Handle mid-input slash command suggestions (e.g. "fix it /bug")."""
        partial = self._get_command_partial(text, cursor_offset)
        if not partial:
            return []
        return self._get_command_suggestions(f"/{partial}")

    def _get_path_suggestions(self, text: str) -> list[Suggestion]:
        """Generate path completion suggestions."""
        # Use directory completion (sync, simpler)
        partial = text
        dirs = get_directory_completions(partial, cwd=os.getcwd(), limit=self._max_results)

        return [
            Suggestion(
                type=SuggestionType.PATH,
                id=d,
                display_text=d,
                description="directory" if d.endswith("/") else "file",
                tag="path",
                metadata={"type": "directory" if d.endswith("/") else "file"},
            )
            for d in dirs
        ]

    def _get_path_suffix(self, text: str) -> str:
        """Get the best path completion suffix."""
        dirs = get_directory_completions(text, cwd=os.getcwd(), limit=1)
        if not dirs:
            return ""
        best = dirs[0]
        if best.startswith(text):
            return best[len(text):]
        return ""

    def _get_shell_history_suggestions(self, text: str) -> list[Suggestion]:
        """Generate shell history suggestions."""
        trimmed = text.strip()
        if len(trimmed) < 2:
            return []

        cmds = get_shell_history_suggestions(trimmed, limit=self._max_results)
        return [
            Suggestion(
                type=SuggestionType.SHELL_HISTORY,
                id=cmd,
                display_text=cmd,
                description="shell history",
                tag="history",
            )
            for cmd in cmds
        ]

    async def _get_shell_completion_suggestions(
        self,
        text: str,
        cursor_offset: int,
        abort_signal: Callable[[], bool] | None = None,
    ) -> list[Suggestion]:
        """Get shell completion suggestions using compgen."""
        from py_claw.utils.bash.shell_completion import get_shell_completions

        results = await get_shell_completions(text, cursor_offset, abort_signal)
        return [
            Suggestion(
                type=SuggestionType.SHELL_COMPLETION,
                id=r.id,
                display_text=r.display_text,
                description=r.description or "shell completion",
                tag="completion",
            )
            for r in results[: self._max_results]
        ]

    def _get_agent_suggestions(self, text: str) -> list[Suggestion]:
        """Get @-mention agent suggestions from teammates and agent registry."""
        # Extract partial after "@"
        match = re.search(r"(^|\s)@([\w-]*)$", text.strip())
        if not match:
            return []
        partial = match.group(2).lower()

        suggestions: list[Suggestion] = []

        # Teammates from team_context
        for name, info in self._teammates.items():
            if partial and name.lower()[:len(partial)] != partial:
                continue
            color = info.get("color") if isinstance(info, dict) else getattr(info, "color", None)
            suggestions.append(
                Suggestion(
                    type=SuggestionType.AGENT,
                    id=f"dm-{name}",
                    display_text=f"@{name}",
                    description=info.get("agent_type") if isinstance(info, dict) else getattr(info, "agent_type", ""),
                    tag="agent",
                    metadata={"name": name, "color": color},
                )
            )

        # Agent name registry entries
        for name, agent_id in self._agent_names.items():
            if partial and name.lower()[:len(partial)] != partial:
                continue
            # Avoid duplicates with teammates
            if any(s.id == f"dm-{name}" for s in suggestions):
                continue
            suggestions.append(
                Suggestion(
                    type=SuggestionType.AGENT,
                    id=f"dm-{name}",
                    display_text=f"@{name}",
                    description=f"agent: {agent_id}",
                    tag="agent",
                    metadata={"name": name, "agent_id": agent_id},
                )
            )

        return suggestions[: self._max_results]

    def _get_channel_suggestions(self, text: str) -> list[Suggestion]:
        """Get #-mention channel suggestions.

        Real Slack channel suggestions require a connected Slack MCP server.
        This provides a stub that searches teammates' channel knowledge,
        or returns an empty list with a hint when no MCP is available.
        """
        # Extract partial after "#"
        match = re.search(r"(^|\s)#([a-z0-9][a-z0-9_-]*)$", text.strip())
        if not match:
            return []
        partial = match.group(2).lower()

        # Stub: suggest common Slack-style channel names based on partial match.
        # Real implementation queries Slack MCP server via slack_search_channels tool.
        common_channels = ["general", "random", "dev", "eng", "ops", "announcements", "help", "debug"]
        suggestions: list[Suggestion] = []
        for channel in common_channels:
            if not partial or channel.startswith(partial):
                suggestions.append(
                    Suggestion(
                        type=SuggestionType.CHANNEL,
                        id=f"#{channel}",
                        display_text=f"#{channel}",
                        description="Slack channel (connect Slack MCP for live suggestions)",
                        tag="channel",
                    )
                )

        return suggestions[: self._max_results]
