"""Tests for the Textual TUI components."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from py_claw.ui.typeahead import CommandItem, SuggestionEngine
from py_claw.ui.screens.repl import REPLScreen


# Synchronous SuggestionEngine tests
class TestSuggestionEngineIntegration:
    """Tests for SuggestionEngine integration with TUI."""

    def test_command_items_built_from_list(self) -> None:
        """Test that SuggestionEngine correctly handles command items."""
        items = [
            CommandItem(name="help", description="Show help", argument_hint="", kind="local"),
            CommandItem(name="clear", description="Clear screen", argument_hint="", kind="local"),
        ]
        engine = SuggestionEngine(command_items=items)

        suggestions = engine.get_suggestions("/h", 2)
        assert len(suggestions) > 0
        # Note: display_text includes trailing space, e.g., "/help "
        assert any("/help" in s.display_text for s in suggestions)

    def test_slash_command_prefix_matching(self) -> None:
        """Test that partial slash commands are matched correctly."""
        items = [
            CommandItem(name="help", description="Show help", argument_hint="[command]", kind="local"),
            CommandItem(name="history", description="Show history", argument_hint="", kind="local"),
        ]
        engine = SuggestionEngine(command_items=items)

        # Test partial command matching
        suggestions = engine.get_suggestions("/he", 3)
        assert len(suggestions) > 0

    def test_no_command_match(self) -> None:
        """Test that non-matching commands return empty list."""
        items = [
            CommandItem(name="help", description="Show help", argument_hint="", kind="local"),
        ]
        engine = SuggestionEngine(command_items=items)

        suggestions = engine.get_suggestions("/xyz", 4)
        assert len(suggestions) == 0

    def test_slash_alone_shows_all_commands(self) -> None:
        """Test that typing '/' alone shows all visible commands."""
        items = [
            CommandItem(name="help", description="Show help", argument_hint="", kind="local"),
            CommandItem(name="clear", description="Clear screen", argument_hint="", kind="local"),
            CommandItem(name="status", description="Show status", argument_hint="", kind="local"),
        ]
        engine = SuggestionEngine(command_items=items)

        suggestions = engine.get_suggestions("/", 1)
        assert len(suggestions) >= 2  # At least help and clear

    def test_command_args_prevents_suggestions(self) -> None:
        """Test that commands with arguments don't show suggestions."""
        items = [
            CommandItem(name="help", description="Show help", argument_hint="[command]", kind="local"),
        ]
        engine = SuggestionEngine(command_items=items)

        # Typing "/help arg" should not show suggestions
        suggestions = engine.get_suggestions("/help arg", 9)
        assert len(suggestions) == 0

    def test_hidden_commands_excluded(self) -> None:
        """Test that hidden commands are excluded from suggestions."""
        items = [
            CommandItem(name="visible", description="A visible command", argument_hint="", kind="local"),
            CommandItem(name="hidden_cmd", description="A hidden command", argument_hint="", kind="local", is_hidden=True),
        ]
        engine = SuggestionEngine(command_items=items)

        suggestions = engine.get_suggestions("/", 1)
        names = [s.id for s in suggestions]
        assert "visible" in names
        assert "hidden_cmd" not in names


# Async Textual widget tests
class TestREPLScreenMount:
    """Tests for REPLScreen mounting and basic interactions."""

    @pytest.mark.asyncio
    async def test_repl_screen_mounts(self) -> None:
        """Test that REPLScreen can be mounted in a Textual app."""
        from textual.app import App

        submitted: list[str] = []
        changed: list[str] = []

        async with App().run_test() as pilot:
            app = pilot.app
            screen = REPLScreen(
                model="test-model",
                status="idle",
                on_submit=lambda t: submitted.append(t),
                on_input_change=lambda t: changed.append(t),
            )
            app.mount(screen)
            await pilot.pause()

            # Check screen has expected children
            assert screen.query_one("#repl-status") is not None
            assert screen.query_one("#repl-message-log") is not None
            assert screen.query_one("#repl-prompt-input") is not None
            assert screen.query_one("#repl-footer") is not None

    @pytest.mark.asyncio
    async def test_repl_screen_displays_model(self) -> None:
        """Test that REPLScreen displays the model name."""
        from textual.app import App

        async with App().run_test() as pilot:
            app = pilot.app
            screen = REPLScreen(
                model="claude-sonnet-4-20250514",
                status="idle",
            )
            app.mount(screen)
            await pilot.pause()

            # Check status line shows the model
            status_line = screen.query_one("#repl-status")
            assert status_line is not None

    @pytest.mark.asyncio
    async def test_repl_screen_message_log(self) -> None:
        """Test that REPLScreen message log can receive messages."""
        from textual.app import App
        from py_claw.ui.widgets.messages import MessageList, MessageItem, MessageRole

        async with App().run_test() as pilot:
            app = pilot.app
            screen = REPLScreen(
                model="test-model",
                status="idle",
            )
            app.mount(screen)
            await pilot.pause()

            # Append a message
            screen.append_message("user", "Hello, world!")
            await pilot.pause()

            log = screen.query_one("#repl-message-log", MessageList)
            messages = log.get_messages()
            assert len(messages) == 1
            assert messages[0].role == MessageRole.USER
            assert messages[0].content == "Hello, world!"
            
            # Check updating the last message
            screen.update_last_message(" Updated")
            messages = log.get_messages()
            assert messages[0].content == " Updated"
            
            screen.update_last_message(" again", append=True)
            messages = log.get_messages()
            assert messages[0].content == " Updated again"
            
            # Check clearing
            screen.clear_log()
            messages = log.get_messages()
            assert len(messages) == 0


class TestPromptInputWidget:
    """Tests for PromptInput widget behavior."""

    @pytest.mark.asyncio
    async def test_prompt_widget_mounts(self) -> None:
        """Test that PromptInput widget can be mounted."""
        from textual.app import App

        async with App().run_test() as pilot:
            app = pilot.app
            screen = REPLScreen(
                model="test-model",
                status="idle",
            )
            app.mount(screen)
            await pilot.pause()

            prompt = screen.query_one("#repl-prompt-input")
            assert prompt is not None
