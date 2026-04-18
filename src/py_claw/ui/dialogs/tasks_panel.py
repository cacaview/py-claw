"""
TasksPanel — Background tasks panel.

Shows currently running or recent background tasks.
Triggered by Ctrl+T in the REPL.
"""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.widgets import Button, Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.list_item import ListItem


class TaskEntry:
    """A task entry for display."""

    def __init__(
        self,
        task_id: str,
        label: str,
        status: str,  # running, completed, failed
        started: str | None = None,
    ) -> None:
        self.task_id = task_id
        self.label = label
        self.status = status
        self.started = started


class TasksPanel(Vertical):
    """Background tasks panel.

    Shows running/completed tasks with status indicators.
    Allows cancelling running tasks.
    """

    BINDINGS = [
        ("up", "move_up", "Move Up"),
        ("down", "move_down", "Move Down"),
        ("escape", "cancel", "Close"),
    ]

    class Cancelled(Message):
        """Emitted when user presses Escape."""

    def __init__(
        self,
        tasks: list[TaskEntry] | None = None,
        on_cancel: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._tasks = list(tasks or [])
        self._on_cancel = on_cancel
        self._on_close = on_close
        self._selected_index: int = 0
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        theme = get_theme()
        accent = theme.colors.get("accent", "cyan")

        yield Pane(title="Background Tasks", border_color=accent)
        yield Static("↑↓ navigate · Esc: close", id="tasks-hint")
        with ScrollableContainer(id="tasks-list"):
            if not self._tasks:
                yield Static("[dim]No background tasks[/dim]", id="tasks-empty")
            else:
                with Vertical():
                    for task in self._tasks:
                        self._render_task(task)

    def _render_task(self, task: TaskEntry) -> None:
        """Render a single task entry."""
        status_colors = {
            "running": "yellow",
            "completed": "green",
            "failed": "red",
        }
        status_icons = {
            "running": "◐",
            "completed": "✓",
            "failed": "✗",
        }
        color = status_colors.get(task.status, "white")
        icon = status_icons.get(task.status, "?")
        label = f"[{color}]{icon} {task.label}[/]"
        if task.started:
            label += f" [dim](started {task.started})[/]"
        yield ListItem(
            item_id=task.task_id,
            label=label,
            description=task.status,
            item_index=i,
        )

    def action_cancel(self) -> None:
        """Close the panel."""
        self.post_message(self.Cancelled())
        if self._on_close:
            self._on_close()
        self.remove()

    def action_move_up(self) -> None:
        """Move selection up."""
        if self._tasks:
            self._selected_index = (self._selected_index - 1) % len(self._tasks)
            self._refresh_selection()

    def action_move_down(self) -> None:
        """Move selection down."""
        if self._tasks:
            self._selected_index = (self._selected_index + 1) % len(self._tasks)
            self._refresh_selection()

    def _refresh_selection(self) -> None:
        """Update visual selection state."""
        list_container = self.query_one("#tasks-list", ScrollableContainer)
        for i, child in enumerate(list_container.query(".list-item")):
            if hasattr(child, "item_id"):
                if i == self._selected_index:
                    child.add_class("list-item--selected")
                else:
                    child.remove_class("list-item--selected")

    def on_mount(self) -> None:
        """Refresh list and focus."""
        self._refresh_selection()
