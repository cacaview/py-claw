"""Tests for PromptInput — keyboard interactions via Textual Pilot."""

from __future__ import annotations

import pytest

from py_claw.ui.typeahead import Suggestion, SuggestionType
from py_claw.ui.widgets.prompt_input import PromptInput, PromptMode
from tests.test_tui.conftest import type_text

pytestmark = pytest.mark.asyncio


class TestPromptInputBasic:
    """Basic input and submission."""

    async def test_focus_input(self, pilot, screen):
        """Focus request reaches the prompt input widget."""
        screen.focus_prompt()
        await pilot.pause()
        prompt = screen.query_one("#repl-prompt-input", PromptInput)
        assert prompt is not None

    async def test_question_mark_toggles_help_without_leaving_input(self, pilot, screen):
        """Typing bare '?' opens help instead of inserting text."""
        from py_claw.ui.dialogs.help import HelpMenuDialog

        screen.focus_prompt()
        await pilot.press("?")
        await pilot.pause()

        overlays = pilot.app.query(HelpMenuDialog)
        assert len(overlays) == 1
        assert screen.get_prompt_value() == ""

    async def test_type_and_see_value(self, pilot, screen):
        """Typing updates the input value."""
        screen.focus_prompt()
        await type_text(pilot, "typed text")
        assert screen.get_prompt_value() == "typed text"

    async def test_clear_input(self, pilot, screen):
        """Clearing the prompt input empties the field."""
        screen.focus_prompt()
        await type_text(pilot, "some text")
        screen.query_one("#repl-prompt-input", PromptInput).clear()
        assert screen.get_prompt_value() == ""


class TestPromptInputSubmit:
    """Submit behavior."""

    async def test_enter_submits(self, pilot, screen, app):
        """Enter key triggers Submitted message."""
        screen.focus_prompt()
        await type_text(pilot, "hello")
        await pilot.press("enter")
        assert "hello" in app._test_submit_calls

    async def test_enter_empty_does_not_submit(self, pilot, screen, app):
        """Empty Enter does not fire submit."""
        screen.focus_prompt()
        await pilot.press("enter")
        assert len(app._test_submit_calls) == 0

    async def test_escape_does_not_submit(self, pilot, screen, app):
        """Escape key does not fire submit."""
        screen.focus_prompt()
        await type_text(pilot, "text")
        await pilot.press("escape")
        assert len(app._test_submit_calls) == 0


class TestPromptInputInterrupt:
    """Interrupt on Escape."""

    async def test_escape_triggers_interrupt(self, pilot, screen, app):
        """Escape when not empty fires on_interrupt."""
        screen.focus_prompt()
        await type_text(pilot, "something")
        await pilot.press("escape")
        assert len(app._test_interrupt_calls) == 1

    async def test_escape_empty_triggers_interrupt(self, pilot, screen, app):
        """Escape on empty prompt also fires on_interrupt."""
        screen.focus_prompt()
        await pilot.press("escape")
        assert len(app._test_interrupt_calls) >= 1


class TestPromptInputHistory:
    """History ring navigation."""

    async def test_history_up_navigates_to_latest_entry_first(self, pilot, screen):
        """First Up after submissions recalls the latest history entry."""
        screen.focus_prompt()
        await type_text(pilot, "first")
        await pilot.press("enter")
        await type_text(pilot, "second")
        await pilot.press("enter")
        await pilot.press("up")
        assert screen.get_prompt_value() == "second"

    async def test_history_down_after_up_restores_live_buffer(self, pilot, screen):
        """Down after recalling latest history returns to the live buffer."""
        screen.focus_prompt()
        await type_text(pilot, "first")
        await pilot.press("enter")
        await type_text(pilot, "second")
        await pilot.press("enter")
        await pilot.press("up")
        await pilot.press("down")
        assert screen.get_prompt_value() == ""


class TestPromptInputModes:
    """Mode switching."""

    async def test_set_mode_normal(self, pilot, screen):
        """set_mode to 'normal' updates PromptMode."""
        screen.set_mode("normal")
        assert screen.query_one("#repl-prompt-input").prompt_mode == PromptMode.NORMAL

    async def test_set_mode_plan(self, pilot, screen):
        """set_mode to 'plan' switches to plan mode."""
        screen.set_mode("plan")
        assert screen.query_one("#repl-prompt-input").prompt_mode == PromptMode.PLAN

    async def test_set_mode_auto(self, pilot, screen):
        """set_mode to 'auto' switches to auto mode."""
        screen.set_mode("auto")
        assert screen.query_one("#repl-prompt-input").prompt_mode == PromptMode.AUTO


    async def test_shift_tab_cycles_modes(self, pilot, screen):
        """Shift+Tab cycles prompt mode through the main permission states."""
        screen.focus_prompt()
        prompt = screen.query_one("#repl-prompt-input", PromptInput)

        await pilot.press("shift+tab")
        assert prompt.prompt_mode == PromptMode.PLAN

        await pilot.press("shift+tab")
        assert prompt.prompt_mode == PromptMode.AUTO

        await pilot.press("shift+tab")
        assert prompt.prompt_mode == PromptMode.BYPASS_PERMISSIONS

        await pilot.press("shift+tab")
        assert prompt.prompt_mode == PromptMode.NORMAL


class TestPromptSuggestionAcceptance:
    """Prompt suggestion acceptance behavior."""

    async def test_right_arrow_accepts_prompt_suggestion(self, pilot, screen):
        screen.focus_prompt()
        prompt = screen.query_one("#repl-prompt-input", PromptInput)
        prompt.set_suggestion_items(
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

        await pilot.press("right")
        await pilot.pause()

        assert screen.get_prompt_value() == "Continue from: hello world"
        assert prompt.suggestion_items == []

class TestPromptInputOnChange:
    """on_change callback."""

    async def test_on_change_fires_on_typing(self, pilot, screen, app):
        """Typing triggers on_change callback."""
        screen.focus_prompt()
        await type_text(pilot, "abc")
        assert len(app._test_change_calls) >= 1
        assert "abc" in app._test_change_calls[-1]
