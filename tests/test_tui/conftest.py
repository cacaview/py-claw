"""Pytest fixtures for TUI tests — pytest + Textual Pilot."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from textual.pilot import Pilot

from py_claw.ui.typeahead import CommandItem, SuggestionEngine


async def type_text(pilot, text: str) -> None:
    """Type text into the focused widget using Pilot.press()."""
    for ch in text:
        key = "space" if ch == " " else ch
        await pilot.press(key)


def apply_compact_layout(app, size: tuple[int, int]) -> None:
    """Apply the same responsive layout state as PyClawApp for tests."""
    width, height = size
    screen = app.query_one("REPLScreen")
    if width < 80:
        app.screen.add_class("narrow")
    else:
        app.screen.remove_class("narrow")
    if height < 20:
        app.screen.add_class("short")
    else:
        app.screen.remove_class("short")

    compact_mode = "full"
    if width < 80 and height < 20:
        compact_mode = "tight"
    elif height < 20:
        compact_mode = "short"
    elif width < 80:
        compact_mode = "narrow"
    screen.set_compact_mode(compact_mode)


class MockQueryRuntime:
    """Mock QueryRuntime that returns no outputs (for submit testing)."""

    def handle_user_message(self, message):
        return []


@pytest.fixture
def command_items():
    """Sample command items matching real slash commands."""
    return [
        CommandItem(name="help", description="Show help information", argument_hint="[command]", kind="local"),
        CommandItem(name="commit", description="Commit changes", argument_hint="<message>", kind="local"),
        CommandItem(name="config", description="Edit configuration", argument_hint="[key] [value]", kind="local"),
        CommandItem(name="ask", description="Ask a question", argument_hint="<question>", kind="prompt"),
        CommandItem(name="bug", description="File a bug report", argument_hint="<description>", kind="local"),
    ]


@pytest.fixture
def suggestion_engine(command_items):
    """SuggestionEngine with sample commands."""
    return SuggestionEngine(command_items=command_items, max_results=10)


@pytest.fixture
def mock_runtime_state(command_items, suggestion_engine):
    """Mock RuntimeState with command registry."""
    state = MagicMock()
    registry = MagicMock()
    registry.slash_commands.return_value = [
        {"name": c.name, "description": c.description, "argumentHint": c.argument_hint, "kind": c.kind}
        for c in command_items
    ]
    state.build_command_registry.return_value = registry
    state.model = "claude-sonnet-4-20250514"
    return state


@pytest_asyncio.fixture
async def app(mock_runtime_state, suggestion_engine, command_items):
    """Create a PyClawApp instance for testing."""
    from textual.app import App, ComposeResult
    from py_claw.ui.screens.repl import REPLScreen
    from py_claw.ui.textual_app import _format_prompt_hint

    submit_calls: list[str] = []
    interrupt_calls: list = []
    change_calls: list[str] = []

    def on_submit(text: str) -> None:
        submit_calls.append(text)

    def on_interrupt() -> None:
        interrupt_calls.append(None)

    def on_change(text: str) -> None:
        change_calls.append(text)

    class TestPyClawApp(App):
        CSS = """
        Screen {
            layout: vertical;
        }
        #repl-message-log {
            height: 1fr;
            max-height: 60%;
        }
        #repl-prompt-input {
            height: auto;
        }
        """

        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("ctrl+g", "new_session", "New"),
            ("ctrl+l", "clear_log", "Clear"),
            ("ctrl+r", "show_history_search", "History"),
            ("ctrl+p", "show_quick_open", "Quick Open"),
            ("ctrl+m", "show_model_picker", "Model"),
            ("ctrl+t", "show_tasks_panel", "Tasks"),
        ]

        def compose(self) -> ComposeResult:
            yield REPLScreen(
                model="claude-sonnet-4-20250514",
                status="ready",
                prompt_hint="Type a prompt or /command",
                on_submit=on_submit,
                on_interrupt=on_interrupt,
                on_input_change=self._handle_input_change,
                suggestion_engine=suggestion_engine,
                command_items=command_items,
            )

        def _screen(self) -> REPLScreen:
            return self.query_one(REPLScreen)

        def _set_hint(self, text: str) -> None:
            self._screen().set_prompt_hint(text)

        def _set_suggestions(self, items: list[object]) -> None:
            self._screen().set_suggestion_items(items)

        def _handle_input_change(self, text: str) -> None:
            change_calls.append(text)
            self._set_hint(_format_prompt_hint(text, suggestion_engine))
            items = suggestion_engine.get_suggestions(text, len(text))
            self._set_suggestions(items)

        def action_quit(self) -> None:
            self.exit()

        def action_new_session(self) -> None:
            screen = self._screen()
            screen.clear_log()
            screen.set_status("idle")
            screen.set_prompt_hint("Type a prompt or /command")
            screen.focus_prompt()

        def action_clear_log(self) -> None:
            self._screen().clear_log()

        def action_show_history_search(self) -> None:
            self._screen().action_show_history_search()

        def action_show_quick_open(self) -> None:
            self._screen().action_show_quick_open()

        def action_show_model_picker(self) -> None:
            self._screen().action_show_model_picker()

        def action_show_tasks_panel(self) -> None:
            self._screen().action_show_tasks_panel()

    test_app = TestPyClawApp()
    # Attach test metadata for assertion helpers
    test_app._test_submit_calls = submit_calls  # type: ignore[attr-defined]
    test_app._test_interrupt_calls = interrupt_calls  # type: ignore[attr-defined]
    test_app._test_change_calls = change_calls  # type: ignore[attr-defined]
    yield test_app
    # Cleanup
    if test_app.is_running:
        test_app.shutdown()


@pytest_asyncio.fixture
async def pilot(app):
    """Textual Pilot for the test app — provides press(), paste(), etc."""
    async with app.run_test() as p:
        yield p


@pytest_asyncio.fixture
async def screen(pilot):
    """The REPLScreen inside the pilot."""
    return pilot.app.query_one("REPLScreen")
