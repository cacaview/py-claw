"""Tests for REPLScreen — basic interactions via Textual Pilot."""

from __future__ import annotations

import pytest

from py_claw.services.keybindings import get_footer_shortcuts_hint, get_status_shortcuts_hint
from py_claw.ui.typeahead import Suggestion, SuggestionType
from py_claw.ui.widgets.messages import MessageList, MessageRole
from py_claw.ui.widgets.prompt_footer import PromptFooter
from py_claw.ui.widgets.prompt_input import PromptInput
from tests.test_tui.conftest import apply_compact_layout, type_text

pytestmark = pytest.mark.asyncio


class TestREPLSubmit:
    """Test prompt submission flow."""

    async def test_submit_empty_does_nothing(self, pilot, screen):
        """Empty input should not trigger submit."""
        await pilot.press("enter")
        assert screen.get_prompt_value() == ""
        # App still running, no crash

    async def test_submit_simple_text(self, pilot, screen, app):
        """Typing text and pressing Enter triggers on_submit."""
        screen.focus_prompt()
        await type_text(pilot, "hello world")
        await pilot.press("enter")
        await pilot.pause()

        assert "hello world" in app._test_submit_calls
        # Prompt should be cleared after submit
        assert screen.get_prompt_value() == ""

    async def test_submit_slash_command(self, pilot, screen, app):
        """Submitting a slash command is captured."""
        screen.focus_prompt()
        await type_text(pilot, "/help")
        await pilot.press("enter")
        await pilot.pause()

        assert "/help" in app._test_submit_calls

    async def test_submit_trimmed(self, pilot, screen, app):
        """Leading/trailing whitespace is stripped on submit."""
        screen.focus_prompt()
        await type_text(pilot, "  hello  ")
        await pilot.press("enter")
        await pilot.pause()

        assert "hello" in app._test_submit_calls
        assert "  hello  " not in app._test_submit_calls


class TestREPLClear:
    """Test clear log action."""

    async def test_clear_log(self, pilot, screen):
        """Ctrl+L clears the message log."""
        screen.append_message("user", "test message")

        log = screen.query_one("#repl-message-log", MessageList)
        assert len(log.get_messages()) == 1

        await pilot.press("ctrl+l")

        assert log.get_messages() == []


class TestREPLStatus:
    """Test status display updates."""

    async def test_status_line_uses_shortcut_hint(self, pilot, screen):
        """Status line exposes the aligned high-frequency shortcut hint."""
        status_line = screen.query_one("#repl-status")
        assert status_line._shortcuts == get_status_shortcuts_hint()

    async def test_set_status(self, pilot, screen):
        """set_status updates the StatusLine and footer."""
        screen.set_status("running")
        assert screen._status == "running"

    async def test_set_model(self, pilot, screen):
        """set_model updates the model name."""
        screen.set_model("claude-opus-4-6")
        assert screen._model == "claude-opus-4-6"


class TestREPLMessageLog:
    """Test message appending."""

    async def test_append_user_message(self, pilot, screen):
        """append_message adds user message."""
        screen.append_message("user", "test content")
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER
        assert messages[0].content == "test content"

    async def test_append_assistant_message(self, pilot, screen):
        """append_message adds assistant message."""
        screen.append_message("assistant", "hello")
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.ASSISTANT
        assert messages[0].content == "hello"

    async def test_append_system_message(self, pilot, screen):
        """append_message adds system message."""
        screen.append_message("system", "warning")
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.SYSTEM
        assert messages[0].content == "warning"


class TestREPMessageUpdate:
    """Test update_last_message — the pattern used by streaming response."""

    async def test_update_last_message_replaces_content(self, pilot, screen):
        """update_last_message replaces the last message content."""
        screen.append_message("assistant", "thinking...")
        screen.update_last_message("final answer")
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].content == "final answer"

    async def test_update_last_message_appends_when_flag_true(self, pilot, screen):
        """update_last_message appends when append=True."""
        screen.append_message("assistant", "part1 ")
        screen.update_last_message("part2", append=True)
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].content == "part1 part2"

    async def test_update_last_message_idempotent_when_empty(self, pilot, screen):
        """update_last_message on empty log does nothing."""
        screen.update_last_message("nothing")
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 0

    async def test_streaming_pattern_append_then_update(self, pilot, screen):
        """Simulate streaming: append thinking, then update with final text."""
        # Step 1: append thinking placeholder
        screen.append_message("assistant", "thinking...")
        log = screen.query_one("#repl-message-log", MessageList)
        assert log.get_messages()[0].content == "thinking..."

        # Step 2: update thinking with real result
        screen.update_last_message("The answer is 42", append=False)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].content == "The answer is 42"

    async def test_multiple_messages_then_update_last(self, pilot, screen):
        """Append multiple messages, then update only the last one (the system message)."""
        screen.append_message("user", "what is 2+2?")
        screen.append_message("assistant", "calculating...")
        screen.append_message("system", "tool: Bash")
        screen.update_last_message("4")  # updates the last message (system)
        messages = screen.query_one("#repl-message-log", MessageList).get_messages()
        assert messages[0].content == "what is 2+2?"      # unchanged
        assert messages[1].content == "calculating..."  # unchanged
        assert messages[2].content == "4"                  # last updated

    async def test_append_tool_progress(self, pilot, screen):
        """append_tool_progress adds a tool message with the tool name."""
        screen.append_tool_progress("Bash", 0.123)
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.TOOL
        assert messages[0].tool_name == "Bash"

    async def test_append_error(self, pilot, screen):
        """append_error adds a system message with the error text."""
        screen.append_error("permission denied")
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.SYSTEM
        assert "permission denied" in messages[0].content


class TestREPLResponsiveLayout:
    """Responsive narrow/short layout behavior."""

    async def test_narrow_layout_keeps_mode_bar_and_footer_visible(self, pilot, screen):
        apply_compact_layout(pilot.app, (79, 28))
        await pilot.pause()

        prompt = screen.query_one("#repl-prompt-input", PromptInput)
        footer = screen.query_one("#repl-footer", PromptFooter)
        mode_bar = prompt.query_one("#pi-mode-bar")

        assert "narrow" in screen.screen.classes
        assert prompt.compact_mode == "narrow"
        assert footer.compact_mode == "narrow"
        assert bool(mode_bar.display) is True
        assert bool(footer.display) is True

    async def test_short_layout_enters_compact_footer_mode(self, pilot, screen):
        apply_compact_layout(pilot.app, (100, 19))
        await pilot.pause()

        footer = screen.query_one("#repl-footer", PromptFooter)
        help_row = footer.query_one("#pf-help-row")

        assert "short" in screen.screen.classes
        assert footer.compact_mode == "short"
        assert bool(footer.display) is True
        assert bool(help_row.display) is True

    async def test_tight_layout_hides_help_row_but_keeps_footer(self, pilot, screen):
        apply_compact_layout(pilot.app, (79, 19))
        await pilot.pause()

        prompt = screen.query_one("#repl-prompt-input", PromptInput)
        footer = screen.query_one("#repl-footer", PromptFooter)
        help_row = footer.query_one("#pf-help-row")

        assert {"narrow", "short"}.issubset(set(screen.screen.classes))
        assert prompt.compact_mode == "tight"
        assert footer.compact_mode == "tight"
        assert bool(footer.display) is True
        assert bool(help_row.display) is False


class TestREPLPromptValue:
    """Test programmatic prompt value manipulation."""

    async def test_footer_uses_aligned_shortcut_hint(self, pilot, screen):
        """Footer help row uses the centralized shortcut hint text."""
        footer = screen.query_one("#repl-footer", PromptFooter)
        assert footer._shortcuts == get_footer_shortcuts_hint()


    async def test_set_prompt_value(self, pilot, screen):
        """set_prompt_value updates the input field."""
        screen.set_prompt_value("from code")
        assert screen.get_prompt_value() == "from code"

    async def test_get_prompt_value_empty(self, pilot, screen):
        """get_prompt_value on empty input returns empty string."""
        assert screen.get_prompt_value() == ""

    async def test_clear_log_then_append(self, pilot, screen):
        """After clear, appending messages still works."""
        screen.clear_log()
        screen.append_message("user", "after clear")
        log = screen.query_one("#repl-message-log", MessageList)
        messages = log.get_messages()
        assert len(messages) == 1
        assert messages[0].content == "after clear"


class TestPromptSuggestionDisplay:
    """Prompt suggestion display in the footer."""

    async def test_repl_screen_surfaces_prompt_suggestion_in_footer(self, pilot, screen):
        screen.set_suggestion_items(
            [
                Suggestion(
                    type=SuggestionType.PROMPT,
                    id="prompt-suggestion",
                    display_text="Continue from: hello world",
                    description="next prompt suggestion",
                    tag="prompt",
                )
            ]
        )
        await pilot.pause()

        footer = screen.query_one("#repl-footer", PromptFooter)
        prompt = screen.query_one("#repl-prompt-input", PromptInput)

        assert footer.has_suggestions is True
        assert len(screen.get_suggestion_items()) == 1
        assert prompt.suggestion_items[0].type == SuggestionType.PROMPT
        assert prompt.suggestion_items[0].display_text == "Continue from: hello world"
