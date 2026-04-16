"""Tests for the typeahead suggestion engine and related types."""

from __future__ import annotations

import pytest

from py_claw.ui.typeahead import (
    CommandItem,
    Suggestion,
    SuggestionEngine,
    SuggestionType,
)


class TestSuggestionType:
    """Tests for SuggestionType enum."""

    def test_all_types_exist(self) -> None:
        """Verify all expected suggestion types are defined."""
        assert SuggestionType.COMMAND is not None
        assert SuggestionType.PATH is not None
        assert SuggestionType.SHELL_HISTORY is not None
        assert SuggestionType.SHELL_COMPLETION is not None
        assert SuggestionType.AGENT is not None
        assert SuggestionType.CHANNEL is not None
        assert SuggestionType.MID_INPUT_SLASH is not None
        assert SuggestionType.PROMPT is not None

    def test_types_are_strings(self) -> None:
        """Verify SuggestionType values are strings (for serialization)."""
        for st in SuggestionType:
            assert isinstance(st.value, str)


class TestCommandItem:
    """Tests for CommandItem dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic CommandItem creation."""
        item = CommandItem(
            name="help",
            description="Show help information",
            argument_hint="[command]",
            kind="local",
        )
        assert item.name == "help"
        assert item.description == "Show help information"
        assert item.argument_hint == "[command]"
        assert item.kind == "local"
        assert item.is_hidden is False
        assert item.aliases == ()

    def test_from_dict(self) -> None:
        """Test CommandItem.from_dict construction."""
        d = {
            "name": "commit",
            "description": "Commit changes",
            "argumentHint": "<message>",
            "kind": "prompt",
            "isHidden": True,
            "aliases": ["ci", "check"],
        }
        item = CommandItem.from_dict(d)
        assert item.name == "commit"
        assert item.description == "Commit changes"
        assert item.argument_hint == "<message>"
        assert item.kind == "prompt"
        assert item.is_hidden is True
        assert item.aliases == ("ci", "check")

    def test_to_dict_roundtrip(self) -> None:
        """Test CommandItem.to_dict and from_dict roundtrip."""
        original = CommandItem(
            name="test",
            description="Test command",
            argument_hint="<arg>",
            kind="local",
            is_hidden=False,
            aliases=("alias1",),
        )
        d = original.to_dict()
        restored = CommandItem.from_dict(d)
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.argument_hint == original.argument_hint
        assert restored.kind == original.kind
        assert restored.is_hidden == original.is_hidden
        assert restored.aliases == original.aliases


class TestSuggestion:
    """Tests for Suggestion dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic Suggestion creation."""
        sug = Suggestion(
            type=SuggestionType.COMMAND,
            id="help",
            display_text="/help",
            description="Show help",
            suffix="lp",
            tag="cmd",
            score=0,
        )
        assert sug.type == SuggestionType.COMMAND
        assert sug.id == "help"
        assert sug.display_text == "/help"
        assert sug.description == "Show help"
        assert sug.suffix == "lp"
        assert sug.tag == "cmd"
        assert sug.score == 0

    def test_name_property(self) -> None:
        """Test Suggestion.name property returns id."""
        sug = Suggestion(type=SuggestionType.COMMAND, id="help", display_text="/help")
        assert sug.name == sug.id

    def test_display_text_stripped(self) -> None:
        """Test Suggestion.display_text_stripped removes whitespace."""
        sug = Suggestion(type=SuggestionType.COMMAND, id="help", display_text=" /help  ")
        assert sug.display_text_stripped == "/help"

    def test_metadata_defaults_to_none(self) -> None:
        """Test Suggestion.metadata defaults to None."""
        sug = Suggestion(type=SuggestionType.COMMAND, id="help", display_text="/help")
        assert sug.metadata is None


class TestSuggestionEngineDetectType:
    """Tests for SuggestionEngine.detect_type()."""

    @pytest.fixture
    def engine(self) -> SuggestionEngine:
        """Create a SuggestionEngine with sample commands."""
        commands = [
            CommandItem(name="help", description="Show help", kind="local"),
            CommandItem(name="commit", description="Commit changes", kind="local"),
            CommandItem(name="config", description="Edit config", kind="local"),
            CommandItem(name="ask", description="Ask a question", kind="prompt"),
        ]
        return SuggestionEngine(command_items=commands, max_results=10)

    def test_empty_text_returns_none(self, engine: SuggestionEngine) -> None:
        """Test that empty text returns None."""
        assert engine.detect_type("", 0) is None

    def test_command_input_slash_only(self, engine: SuggestionEngine) -> None:
        """Test bare '/' returns COMMAND type."""
        assert engine.detect_type("/", 1) == SuggestionType.COMMAND

    def test_command_input_full_command(self, engine: SuggestionEngine) -> None:
        """Test '/help' returns COMMAND type."""
        assert engine.detect_type("/help", 5) == SuggestionType.COMMAND

    def test_command_input_partial(self, engine: SuggestionEngine) -> None:
        """Test '/he' (partial) returns COMMAND type."""
        assert engine.detect_type("/he", 3) == SuggestionType.COMMAND

    def test_path_like_absolute(self, engine: SuggestionEngine) -> None:
        """Test absolute paths like '/usr' return PATH type."""
        assert engine.detect_type("/usr", 4) == SuggestionType.PATH

    def test_path_like_home(self, engine: SuggestionEngine) -> None:
        """Test home paths like '~/Documents' return PATH type."""
        assert engine.detect_type("~/Documents", 12) == SuggestionType.PATH

    def test_path_like_relative(self, engine: SuggestionEngine) -> None:
        """Test relative paths like './src' return PATH type."""
        assert engine.detect_type("./src", 5) == SuggestionType.PATH

    def test_path_like_parent(self, engine: SuggestionEngine) -> None:
        """Test parent paths like '../foo' return PATH type."""
        assert engine.detect_type("../foo", 6) == SuggestionType.PATH

    def test_agent_mention(self, engine: SuggestionEngine) -> None:
        """Test '@' mention returns AGENT type."""
        assert engine.detect_type("@", 1) == SuggestionType.AGENT
        assert engine.detect_type("@foo", 4) == SuggestionType.AGENT

    def test_channel_mention(self, engine: SuggestionEngine) -> None:
        """Test '#' mention returns CHANNEL type."""
        assert engine.detect_type("#", 1) == SuggestionType.CHANNEL
        assert engine.detect_type("#general", 8) == SuggestionType.CHANNEL

    def test_mid_input_slash(self, engine: SuggestionEngine) -> None:
        """Test mid-input slash command returns MID_INPUT_SLASH type."""
        # "fix it /bu" with cursor after /bu
        assert engine.detect_type("fix it /bu", 9) == SuggestionType.MID_INPUT_SLASH

    def test_shell_history_short_text(self, engine: SuggestionEngine) -> None:
        """Test short text triggers shell completion, not shell history.

        Short alphanumeric text (<=3 chars) triggers SHELL_COMPLETION
        since compgen is used for subcommand/flag completion.
        """
        assert engine.detect_type("a", 1) == SuggestionType.SHELL_COMPLETION

    def test_shell_history_triggers(self, engine: SuggestionEngine) -> None:
        """Test longer text (>3 chars) triggers shell history, not completion.

        Text > 3 chars without command prefix triggers SHELL_HISTORY.
        Short text (<=3 chars) triggers SHELL_COMPLETION instead.
        """
        # "python" is > 3 chars and not a command prefix
        assert engine.detect_type("python", 6) == SuggestionType.SHELL_HISTORY

    def test_shell_completion_short_alphanumeric(self, engine: SuggestionEngine) -> None:
        """Test short alphanumeric text triggers shell completion."""
        # "abc" (len <= 3, alnum, not starting with /)
        engine2 = SuggestionEngine(command_items=[], max_results=10)
        assert engine2.detect_type("abc", 3) == SuggestionType.SHELL_COMPLETION


class TestSuggestionEngineGetSuggestions:
    """Tests for SuggestionEngine.get_suggestions()."""

    @pytest.fixture
    def engine(self) -> SuggestionEngine:
        """Create a SuggestionEngine with sample commands."""
        commands = [
            CommandItem(name="help", description="Show help", kind="local"),
            CommandItem(name="commit", description="Commit changes", kind="local"),
            CommandItem(name="config", description="Edit config", kind="local"),
            CommandItem(name="ask", description="Ask a question", kind="prompt"),
        ]
        return SuggestionEngine(command_items=commands, max_results=10)

    def test_command_suggestions_bare_slash(self, engine: SuggestionEngine) -> None:
        """Test '/' returns all non-hidden commands."""
        suggestions = engine.get_suggestions("/", 1)
        assert len(suggestions) == 4
        assert all(s.type == SuggestionType.COMMAND for s in suggestions)

    def test_command_suggestions_filtered(self, engine: SuggestionEngine) -> None:
        """Test '/c' returns only commands starting with 'c'."""
        suggestions = engine.get_suggestions("/c", 2)
        names = [s.id for s in suggestions]
        assert "commit" in names
        assert "config" in names
        assert "help" not in names

    def test_command_suggestions_with_args(self, engine: SuggestionEngine) -> None:
        """Test '/commit message' (has args) returns empty."""
        suggestions = engine.get_suggestions("/commit message", 14)
        assert suggestions == []

    def test_mid_input_slash_suggestions(self, engine: SuggestionEngine) -> None:
        """Test mid-input '/bu' returns matching commands."""
        suggestions = engine.get_suggestions("see /bu", 7)
        # Should find 'bug', 'build' etc if they existed
        # With our test commands, nothing matches 'bu'
        assert isinstance(suggestions, list)

    def test_path_suggestions(self, engine: SuggestionEngine) -> None:
        """Test path suggestions return PATH type."""
        suggestions = engine.get_suggestions("/tmp", 4)
        assert all(s.type == SuggestionType.PATH for s in suggestions)

    def test_shell_history_suggestions(self, engine: SuggestionEngine) -> None:
        """Test shell history suggestions return SHELL_HISTORY type."""
        suggestions = engine.get_suggestions("git", 3)
        # May or may not have results depending on actual shell history
        assert all(s.type == SuggestionType.SHELL_HISTORY for s in suggestions)

    def test_empty_input_returns_empty(self, engine: SuggestionEngine) -> None:
        """Test empty input returns empty list."""
        suggestions = engine.get_suggestions("", 0)
        assert suggestions == []


class TestSuggestionEngineBestSuffix:
    """Tests for SuggestionEngine.get_best_suffix()."""

    @pytest.fixture
    def engine(self) -> SuggestionEngine:
        """Create a SuggestionEngine with sample commands."""
        commands = [
            CommandItem(name="help", description="Show help", kind="local"),
            CommandItem(name="commit", description="Commit changes", kind="local"),
            CommandItem(name=" Ask", description="Ask a question", kind="prompt"),
        ]
        return SuggestionEngine(command_items=commands, max_results=10)

    def test_best_suffix_partial_command(self, engine: SuggestionEngine) -> None:
        """Test '/he' returns 'lp ' as suffix."""
        suffix = engine.get_best_suffix("/he", 3)
        assert suffix == "lp "

    def test_best_suffix_full_command(self, engine: SuggestionEngine) -> None:
        """Test '/help' (full) returns ' ' suffix."""
        suffix = engine.get_best_suffix("/help", 5)
        assert suffix == " "

    def test_best_suffix_no_match(self, engine: SuggestionEngine) -> None:
        """Test '/xyz' (no match) returns empty suffix."""
        suffix = engine.get_best_suffix("/xyz", 4)
        assert suffix == ""

    def test_best_suffix_empty(self, engine: SuggestionEngine) -> None:
        """Test empty input returns empty suffix."""
        suffix = engine.get_best_suffix("", 0)
        assert suffix == ""


class TestSuggestionEngineAgentSuggestions:
    """Tests for SuggestionEngine._get_agent_suggestions()."""

    def test_agent_suggestions_from_teammates(self) -> None:
        """Test @-mention suggestions from teammates."""
        engine = SuggestionEngine(
            command_items=[],
            max_results=10,
            teammates={"alice": {"color": "blue", "agent_type": "coder"}},
            agent_names={},
        )
        suggestions = engine.get_suggestions("@", 1)
        assert len(suggestions) >= 1
        assert any("alice" in s.display_text for s in suggestions)

    def test_agent_suggestions_filtered(self) -> None:
        """Test @-mention suggestions are filtered by partial."""
        engine = SuggestionEngine(
            command_items=[],
            max_results=10,
            teammates={"alice": {"color": "blue", "agent_type": "coder"}},
            agent_names={},
        )
        suggestions = engine.get_suggestions("@al", 3)
        assert len(suggestions) >= 1
        assert all("al" in s.display_text.lower() for s in suggestions)

    def test_agent_suggestions_no_match(self) -> None:
        """Test @-mention with no matching teammate."""
        engine = SuggestionEngine(
            command_items=[],
            max_results=10,
            teammates={"alice": {"color": "blue", "agent_type": "coder"}},
            agent_names={},
        )
        suggestions = engine.get_suggestions("@xyz", 4)
        assert len(suggestions) == 0


class TestSuggestionEngineChannelSuggestions:
    """Tests for SuggestionEngine._get_channel_suggestions()."""

    def test_channel_suggestions(self) -> None:
        """Test channel suggestions return common Slack-style channels."""
        engine = SuggestionEngine(command_items=[], max_results=10)
        suggestions = engine.get_suggestions("#", 1)
        assert len(suggestions) >= 1
        assert all(s.type == SuggestionType.CHANNEL for s in suggestions)
        assert all(s.display_text.startswith("#") for s in suggestions)

    def test_channel_suggestions_filtered(self) -> None:
        """Test channel suggestions are filtered by partial."""
        engine = SuggestionEngine(command_items=[], max_results=10)
        suggestions = engine.get_suggestions("#de", 3)
        assert len(suggestions) >= 1
        assert all("de" in s.display_text.lower() for s in suggestions)

    def test_channel_suggestions_no_match(self) -> None:
        """Test channel suggestions with non-matching partial."""
        engine = SuggestionEngine(command_items=[], max_results=10)
        suggestions = engine.get_suggestions("#xyzxyz", 7)
        # No channels match 'xyzxyz'
        assert len(suggestions) == 0


class TestSuggestionEngineSetContext:
    """Tests for SuggestionEngine context updates."""

    def test_set_command_items(self) -> None:
        """Test updating command registry."""
        engine = SuggestionEngine(command_items=[], max_results=10)
        new_commands = [
            CommandItem(name="newcmd", description="New command", kind="local"),
        ]
        engine.set_command_items(new_commands)
        suggestions = engine.get_suggestions("/", 1)
        assert len(suggestions) == 1
        assert suggestions[0].id == "newcmd"

    def test_set_team_context(self) -> None:
        """Test updating team context for agent suggestions."""
        engine = SuggestionEngine(command_items=[], max_results=10)
        engine.set_team_context(
            teammates={"bob": {"color": "red", "agent_type": "reviewer"}},
            agent_names={},
        )
        suggestions = engine.get_suggestions("@", 1)
        assert any("bob" in s.display_text for s in suggestions)


class TestPromptSuggestionItems:
    """Tests for prompt suggestion items traveling through the unified model."""

    def test_prompt_suggestion_item_keeps_prompt_metadata(self) -> None:
        suggestion = Suggestion(
            type=SuggestionType.PROMPT,
            id="prompt-suggestion",
            display_text="Continue from: hello world",
            description="next prompt suggestion",
            tag="prompt",
            metadata={"source": "prompt_suggestion"},
        )

        assert suggestion.type == SuggestionType.PROMPT
        assert suggestion.display_text == "Continue from: hello world"
        assert suggestion.metadata == {"source": "prompt_suggestion"}
