"""
HistorySearchDialog — Shell history search overlay.

Re-implements ClaudeCode-main/src/components/PromptInput/HistorySearchInput.tsx
as a Textual dialog that allows searching shell command history.

Triggered by Ctrl+R in the REPL.
"""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.pane import Pane
from py_claw.utils.suggestions.shell_history_completion import get_shell_history_suggestions


class HistorySearchDialog(Vertical):
    """Shell history search dialog.

    Shows a search input and matching shell commands from history.
    Pressing Enter inserts the selected command into the prompt.
    Escape closes without inserting.
    """

    BINDINGS = [
        ("up", "move_up", "Move Up"),
        ("down", "move_down", "Move Down"),
        ("enter", "confirm", "Use Command"),
        ("escape", "cancel", "Cancel"),
    ]

    class Selected(Message):
        """Emitted when user confirms a history entry."""

        def __init__(self, command: str) -> None:
            self.command = command
            super().__init__()

    class Cancelled(Message):
        """Emitted when user presses Escape."""

    def __init__(
        self,
        on_select: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._on_select = on_select
        self._on_close = on_close
        self._history: list[str] = []
        self._filtered: list[str] = []
        self._selected_index: int = 0
        self._query: str = ""
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        theme = get_theme()
        accent = theme.colors.get("accent", "cyan")

        yield Pane(title="Search History", border_color=accent)
        yield Input(placeholder="Search shell history...", id="history-search-input")
        yield Static("↑↓ navigate · Enter: use · Esc: cancel", id="history-hint")
        with Vertical(id="history-results"):
            pass  # Populated on mount

    def on_mount(self) -> None:
        """Load initial history."""
        self._history = get_shell_history_suggestions("", limit=20)
        self._filtered = self._history
        self._refresh_results()
        # Focus the search input
        self.query_one("#history-search-input", Input).focus()

    def _refresh_results(self) -> None:
        """Refresh the results list."""
        results = self.query_one("#history-results", Vertical)
        results.remove_children()

        theme = get_theme()
        accent = theme.colors.get("accent", "cyan")
        dim = theme.colors.get("text_dim", "#555555")

        for i, cmd in enumerate(self._filtered[:10]):
            is_selected = i == self._selected_index
            prefix = "▶" if is_selected else " "
            color = accent if is_selected else dim
            cmd_short = cmd[:80] + ("..." if len(cmd) > 80 else "")
            results.mount(
                Static(
                    f"[{color}]{prefix} {cmd_short}[/]",
                    id=f"history-item-{i}",
                )
            )

        # Update hint
        hint = self.query_one("#history-hint", Static)
        count = len(self._filtered)
        if count == 0:
            hint.update("[dim]no matching commands[/dim]")
        else:
            hint.update(f"[dim]↑↓ navigate · Enter: use · Esc: cancel · {count} results[/dim]")

    def _filter(self, query: str) -> None:
        """Filter history by query."""
        self._query = query
        if not query:
            self._filtered = self._history[:20]
        else:
            self._filtered = get_shell_history_suggestions(query, limit=20)
        self._selected_index = 0
        self._refresh_results()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "history-search-input":
            self._filter(event.value)

    def action_move_up(self) -> None:
        """Move selection up."""
        if self._filtered:
            self._selected_index = (self._selected_index - 1) % len(self._filtered[:10])
            self._refresh_results()

    def action_move_down(self) -> None:
        """Move selection down."""
        if self._filtered:
            self._selected_index = (self._selected_index + 1) % len(self._filtered[:10])
            self._refresh_results()

    def action_confirm(self) -> None:
        """Confirm selection."""
        if not self._filtered:
            return
        idx = self._selected_index
        if idx < len(self._filtered):
            cmd = self._filtered[idx]
            self.post_message(self.Selected(cmd))
            if self._on_select:
                self._on_select(cmd)
            self._close()

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.post_message(self.Cancelled())
        self._close()

    def _close(self) -> None:
        """Close the dialog."""
        if self._on_close:
            self._on_close()
        self.remove()
