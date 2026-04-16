"""Tests for TUI overlay dialogs — Help, History Search, Quick Open, Model Picker, Tasks."""

from __future__ import annotations

import pytest
from textual.app import App

from py_claw.services.keybindings import get_all_shortcuts_for_display
from py_claw.tools.ask_user_question_tool import (
    AskUserQuestionOption,
    AskUserQuestionQuestion,
    AskUserQuestionToolInput,
)
from py_claw.ui.dialogs.permission import PermissionDialog
from py_claw.ui.dialogs.prompt import PromptDialog

pytestmark = pytest.mark.asyncio


class TestHelpMenuOverlay:
    """Test HelpMenuDialog lifecycle."""

    async def test_help_menu_opens(self, pilot, screen):
        """Showing help mounts the overlay and tracks its state."""
        screen._show_help_menu()
        await pilot.pause()
        from py_claw.ui.dialogs.help import HelpMenuDialog
        overlays = pilot.app.query(HelpMenuDialog)
        assert len(overlays) >= 1
        assert screen._active_overlay == "help-menu"
        assert "help-menu" in screen._overlay_ids

    async def test_help_menu_closes_via_cancel_action(self, pilot, screen):
        """Cancelling help closes the overlay and clears tracked state."""
        from py_claw.ui.dialogs.help import HelpMenuDialog

        screen._show_help_menu()
        await pilot.pause()

        overlay = pilot.app.query_one(HelpMenuDialog)
        overlay.action_cancel()
        await pilot.pause()

        overlays = pilot.app.query(HelpMenuDialog)
        assert len(overlays) == 0
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()

    async def test_help_menu_closes_on_escape(self, pilot, screen):
        """Escape closes the mounted help overlay."""
        from py_claw.ui.dialogs.help import HelpMenuDialog

        screen._show_help_menu()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        overlays = pilot.app.query(HelpMenuDialog)
        assert len(overlays) == 0
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()


    async def test_help_menu_shortcuts_match_centralized_display(self, pilot, screen):
        """Help overlay shows the same shortcut surface as the keybinding service."""
        from py_claw.ui.dialogs.help import HelpMenuDialog

        screen._show_help_menu()
        await pilot.pause()

        overlay = pilot.app.query_one(HelpMenuDialog)
        assert overlay._shortcuts == get_all_shortcuts_for_display()
        assert overlay._shortcuts["shift+tab"] == "Cycle prompt mode"
        assert overlay._shortcuts["ctrl+t"] == "Tasks panel"


class TestHistorySearchOverlay:
    """Test HistorySearchDialog via Ctrl+R."""

    async def test_history_search_opens(self, pilot, screen):
        """Ctrl+R opens the history search overlay."""
        await pilot.press("ctrl+r")
        await pilot.pause()
        from py_claw.ui.dialogs.history_search import HistorySearchDialog
        overlays = pilot.app.query(HistorySearchDialog)
        assert len(overlays) >= 1
        assert screen._active_overlay == "history-search"
        assert "history-search" in screen._overlay_ids

    async def test_history_search_reopen_does_not_duplicate_overlay(self, pilot, screen):
        """Repeated history-search action while open should not mount duplicates."""
        from py_claw.ui.dialogs.history_search import HistorySearchDialog

        await pilot.press("ctrl+r")
        await pilot.pause()
        screen.action_show_history_search()
        await pilot.pause()

        overlays = pilot.app.query(HistorySearchDialog)
        assert len(overlays) == 1
        assert screen._active_overlay == "history-search"

    async def test_history_search_closes_on_escape(self, pilot, screen):
        """Escape closes history search."""
        await pilot.press("ctrl+r")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        from py_claw.ui.dialogs.history_search import HistorySearchDialog
        overlays = pilot.app.query(HistorySearchDialog)
        assert len(overlays) == 0
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()

    async def test_history_search_selection_updates_prompt(self, pilot, screen, monkeypatch):
        """Confirming a history item writes it back into the prompt."""
        from py_claw.ui.dialogs import history_search as history_search_module
        from py_claw.ui.dialogs.history_search import HistorySearchDialog

        monkeypatch.setattr(
            history_search_module,
            "get_shell_history_suggestions",
            lambda query, limit=20: ["pytest tests/test_tui/test_overlays.py", "git status"],
        )

        await pilot.press("ctrl+r")
        await pilot.pause()

        overlay = pilot.app.query_one(HistorySearchDialog)
        overlay.action_confirm()
        await pilot.pause()

        assert screen.get_prompt_value() == "pytest tests/test_tui/test_overlays.py"
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()


class TestQuickOpenOverlay:
    """Test QuickOpenDialog lifecycle."""

    async def test_quick_open_opens(self, pilot, screen, monkeypatch):
        """Showing quick open mounts the overlay and tracks its state."""
        from py_claw.ui.dialogs import quick_open as quick_open_module
        from py_claw.ui.dialogs.quick_open import QuickOpenDialog

        monkeypatch.setattr(
            quick_open_module.QuickOpenDialog,
            "_scan_files",
            lambda self: ["repl.py", "test_overlays.py"],
        )

        screen.action_show_quick_open()
        await pilot.pause()
        overlays = pilot.app.query(QuickOpenDialog)
        assert len(overlays) >= 1
        assert screen._active_overlay == "quick-open"
        assert "quick-open" in screen._overlay_ids

    async def test_quick_open_closes_on_escape(self, pilot, screen, monkeypatch):
        """Escape closes quick open."""
        from py_claw.ui.dialogs import quick_open as quick_open_module
        from py_claw.ui.dialogs.quick_open import QuickOpenDialog

        monkeypatch.setattr(
            quick_open_module.QuickOpenDialog,
            "_scan_files",
            lambda self: ["repl.py", "test_overlays.py"],
        )

        screen.action_show_quick_open()
        await pilot.pause()
        overlay = pilot.app.query_one(QuickOpenDialog)
        overlay.action_cancel()
        await pilot.pause()

        overlays = pilot.app.query(QuickOpenDialog)
        assert len(overlays) == 0
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()

    async def test_quick_open_selection_updates_prompt(self, pilot, screen, monkeypatch):
        """Confirming a quick-open result writes the path into the prompt."""
        from py_claw.ui.dialogs import quick_open as quick_open_module
        from py_claw.ui.dialogs.quick_open import QuickOpenDialog

        monkeypatch.setattr(
            quick_open_module.QuickOpenDialog,
            "_scan_files",
            lambda self: ["test_overlays.py", "repl.py"],
        )

        screen.action_show_quick_open()
        await pilot.pause()

        overlay = pilot.app.query_one(QuickOpenDialog)
        overlay.action_confirm()
        await pilot.pause()

        assert screen.get_prompt_value() == "test_overlays.py"
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()


class TestModelPickerOverlay:
    """Test ModelPickerDialog via Ctrl+M."""

    async def test_model_picker_opens(self, pilot, screen):
        """Ctrl+M opens the model picker overlay."""
        await pilot.press("ctrl+m")
        await pilot.pause()
        from py_claw.ui.dialogs.model_picker import ModelPickerDialog
        overlays = pilot.app.query(ModelPickerDialog)
        assert len(overlays) >= 1
        assert screen._active_overlay == "model-picker"
        assert "model-picker" in screen._overlay_ids

    async def test_model_picker_closes_on_escape(self, pilot, screen):
        """Escape closes model picker."""
        await pilot.press("ctrl+m")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        from py_claw.ui.dialogs.model_picker import ModelPickerDialog
        overlays = pilot.app.query(ModelPickerDialog)
        assert len(overlays) == 0
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()

    async def test_model_picker_selection_updates_model(self, pilot, screen):
        """Confirming a model updates the REPL model and closes the overlay."""
        from py_claw.ui.dialogs.model_picker import ModelPickerDialog

        await pilot.press("ctrl+m")
        await pilot.pause()

        overlay = pilot.app.query_one(ModelPickerDialog)
        overlay.action_move_down()
        overlay.action_confirm()
        await pilot.pause()

        assert screen._model == "claude-opus-4-6-20250514"
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()


class TestTasksPanelOverlay:
    """Test TasksPanel via Ctrl+T."""

    async def test_tasks_panel_opens(self, pilot, screen):
        """Ctrl+T opens the tasks panel overlay."""
        await pilot.press("ctrl+t")
        await pilot.pause()
        from py_claw.ui.dialogs.tasks_panel import TasksPanel
        overlays = pilot.app.query(TasksPanel)
        assert len(overlays) >= 1
        assert screen._active_overlay == "tasks-panel"
        assert "tasks-panel" in screen._overlay_ids

    async def test_tasks_panel_closes_on_escape(self, pilot, screen):
        """Cancelling tasks panel closes the overlay and clears tracked state."""
        from py_claw.ui.dialogs.tasks_panel import TasksPanel

        await pilot.press("ctrl+t")
        await pilot.pause()

        overlay = pilot.app.query_one(TasksPanel)
        overlay.action_cancel()
        await pilot.pause()

        overlays = pilot.app.query(TasksPanel)
        assert len(overlays) == 0
        assert screen._active_overlay is None
        assert screen._overlay_ids == set()


class TestOverlayExclusivity:
    """Test that opening one overlay blocks others."""

    async def test_history_search_blocks_model_picker(self, pilot, screen):
        """While history search is open, model picker should not open."""
        await pilot.press("ctrl+r")
        await pilot.pause()
        await pilot.press("ctrl+m")
        await pilot.pause()
        from py_claw.ui.dialogs.model_picker import ModelPickerDialog
        overlays = pilot.app.query(ModelPickerDialog)
        assert len(overlays) == 0
        assert screen._active_overlay == "history-search"

    async def test_overlay_can_reopen_after_close(self, pilot, screen):
        """Closing an overlay should allow it to be opened again."""
        from py_claw.ui.dialogs.history_search import HistorySearchDialog

        await pilot.press("ctrl+r")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()

        overlays = pilot.app.query(HistorySearchDialog)
        assert len(overlays) == 1
        assert screen._active_overlay == "history-search"


class TestStandaloneDialogs:
    """Direct dialog tests for prompt/permission overlays used by REPL flows."""

    async def test_prompt_dialog_accepts_first_option(self) -> None:
        """PromptDialog confirm returns the first option label for the first question."""
        accepted: list[tuple[dict[str, str], dict]] = []
        declined: list[bool] = []

        arguments = AskUserQuestionToolInput(
            questions=[
                AskUserQuestionQuestion(
                    header="Approach",
                    question="Which approach should we use?",
                    options=[
                        AskUserQuestionOption(label="A", description="Use approach A"),
                        AskUserQuestionOption(label="B", description="Use approach B"),
                    ],
                )
            ]
        )

        async with App().run_test() as pilot:
            dialog = PromptDialog(
                arguments=arguments,
                on_accept=lambda answers, annotations: accepted.append((answers, annotations)),
                on_decline=lambda: declined.append(True),
            )
            pilot.app.mount(dialog)
            await pilot.pause()

            body = pilot.app.query_one("#dialog-body")
            assert str(body.render()) == "Which approach should we use?"
            dialog.confirm()
            await pilot.pause()

        assert accepted == [({"Approach": "A"}, {})]
        assert declined == []

    async def test_prompt_dialog_decline_calls_callback(self) -> None:
        """PromptDialog deny triggers the decline callback."""
        declined: list[bool] = []

        arguments = AskUserQuestionToolInput(
            questions=[
                AskUserQuestionQuestion(
                    header="Approach",
                    question="Which approach should we use?",
                    options=[
                        AskUserQuestionOption(label="A", description="Use approach A"),
                        AskUserQuestionOption(label="B", description="Use approach B"),
                    ],
                )
            ]
        )

        async with App().run_test() as pilot:
            dialog = PromptDialog(arguments=arguments, on_decline=lambda: declined.append(True))
            pilot.app.mount(dialog)
            await pilot.pause()

            dialog.deny()
            await pilot.pause()

        assert declined == [True]

    async def test_permission_dialog_renders_params_and_allow_deny(self) -> None:
        """PermissionDialog renders request details and fires allow/deny callbacks."""
        allowed: list[bool] = []
        denied: list[bool] = []

        async with App().run_test() as pilot:
            dialog = PermissionDialog(
                tool_name="Bash",
                message="Run shell command",
                params={"command": "pytest tests/test_tui/test_overlays.py", "timeout": 120000},
                on_allow=lambda: allowed.append(True),
                on_deny=lambda: denied.append(True),
            )
            pilot.app.mount(dialog)
            await pilot.pause()

            body = str(pilot.app.query_one("#dialog-body").render())
            assert "Run shell command" in body
            assert "command: pytest tests/test_tui/test_overlays.py" in body
            assert "timeout: 120000" in body

            dialog.confirm()
            await pilot.pause()

        async with App().run_test() as pilot:
            dialog = PermissionDialog(
                tool_name="Bash",
                message="Run shell command",
                params={"command": "pytest tests/test_tui/test_overlays.py", "timeout": 120000},
                on_allow=lambda: allowed.append(True),
                on_deny=lambda: denied.append(True),
            )
            pilot.app.mount(dialog)
            await pilot.pause()

            dialog.deny()
            await pilot.pause()

        assert allowed == [True]
        assert denied == [True]
