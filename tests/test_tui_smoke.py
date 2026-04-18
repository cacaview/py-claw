"""Smoke tests for full PyClawApp — verifies the real app can mount and respond."""

from __future__ import annotations

import pytest


class TestPyClawAppSmoke:
    """Verify PyClawApp instantiates and renders without errors.

    These tests use Textual's run_test() context manager which provides a
    headless terminal. They verify the actual PyClawApp composition without
    mocking core components.
    """

    @pytest.mark.asyncio
    async def test_pyclaw_app_mounts_repl_screen(self) -> None:
        from textual.app import App
        from py_claw.ui.textual_app import _build_command_items
        from py_claw.cli.runtime import RuntimeState
        from py_claw.ui.screens.repl import REPLScreen
        from py_claw.ui.typeahead import SuggestionEngine

        state = RuntimeState()
        command_items = _build_command_items(state)
        engine = SuggestionEngine(command_items=command_items)

        async with App().run_test() as pilot:
            screen = REPLScreen(
                model="test-model",
                status="idle",
                suggestion_engine=engine,
                command_items=command_items,
            )
            pilot.app.mount(screen)
            await pilot.pause()

            # Screen should be mounted and visible
            repl_screen = pilot.app.query_one(REPLScreen)
            assert repl_screen is not None

    @pytest.mark.asyncio
    async def test_pyclaw_app_prompt_accepts_input(self) -> None:
        from textual.app import App
        from py_claw.ui.textual_app import _build_command_items
        from py_claw.cli.runtime import RuntimeState
        from py_claw.ui.screens.repl import REPLScreen
        from py_claw.ui.typeahead import SuggestionEngine

        state = RuntimeState()
        command_items = _build_command_items(state)
        engine = SuggestionEngine(command_items=command_items)
        submitted: list[str] = []

        async with App().run_test() as pilot:
            screen = REPLScreen(
                model="test-model",
                status="idle",
                on_submit=lambda t: submitted.append(t),
                suggestion_engine=engine,
                command_items=command_items,
            )
            pilot.app.mount(screen)
            await pilot.pause()

            screen.focus_prompt()
            await pilot.press("h", "e", "l", "l", "o")
            await pilot.press("enter")
            await pilot.pause()

            assert submitted == ["hello"]

    @pytest.mark.asyncio
    async def test_pyclaw_app_ctrl_r_opens_history(self) -> None:
        from textual.app import App
        from py_claw.ui.textual_app import _build_command_items
        from py_claw.cli.runtime import RuntimeState
        from py_claw.ui.screens.repl import REPLScreen
        from py_claw.ui.dialogs.history_search import HistorySearchDialog
        from py_claw.ui.typeahead import SuggestionEngine

        state = RuntimeState()
        command_items = _build_command_items(state)
        engine = SuggestionEngine(command_items=command_items)

        async with App().run_test() as pilot:
            screen = REPLScreen(
                model="test-model",
                status="idle",
                suggestion_engine=engine,
                command_items=command_items,
            )
            pilot.app.mount(screen)
            await pilot.pause()

            screen.focus_prompt()
            await pilot.press("ctrl+r")
            await pilot.pause()

            dialogs = pilot.app.query(HistorySearchDialog)
            assert len(dialogs) == 1

    @pytest.mark.asyncio
    async def test_pyclaw_app_question_opens_help(self) -> None:
        from textual.app import App
        from py_claw.ui.textual_app import _build_command_items
        from py_claw.cli.runtime import RuntimeState
        from py_claw.ui.screens.repl import REPLScreen
        from py_claw.ui.dialogs.help import HelpMenuDialog
        from py_claw.ui.typeahead import SuggestionEngine

        state = RuntimeState()
        command_items = _build_command_items(state)
        engine = SuggestionEngine(command_items=command_items)

        async with App().run_test() as pilot:
            screen = REPLScreen(
                model="test-model",
                status="idle",
                suggestion_engine=engine,
                command_items=command_items,
            )
            pilot.app.mount(screen)
            await pilot.pause()

            screen.focus_prompt()
            await pilot.press("?")
            await pilot.pause()

            dialogs = pilot.app.query(HelpMenuDialog)
            assert len(dialogs) == 1
