"""
QuickOpenDialog — Quick file open dialog.

Fuzzy searches files in the current project directory.
Triggered by Ctrl+P in the REPL.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.widgets import Input, Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.list_item import ListItem


class QuickOpenDialog(Vertical):
    """Quick open dialog — fuzzy file search.

    Searches files in the current working directory.
    Uses simple fuzzy matching on filenames.
    """

    BINDINGS = [
        ("up", "move_up", "Move Up"),
        ("down", "move_down", "Move Down"),
        ("enter", "confirm", "Open"),
        ("escape", "cancel", "Cancel"),
    ]

    class Selected(Message):
        """Emitted when a file is selected."""

        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    class Cancelled(Message):
        """Emitted when user presses Escape."""

    def __init__(
        self,
        root_dir: str | None = None,
        on_select: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._root = Path(root_dir or os.getcwd())
        self._on_select = on_select
        self._on_close = on_close
        self._all_files: list[str] = []
        self._filtered: list[str] = []
        self._selected_index: int = 0
        self._query: str = ""
        # Common ignore patterns
        self._ignore = {
            ".git", ".pytest_cache", "__pycache__", ".mypy_cache",
            "node_modules", ".venv", "venv", ".tox", "dist", "build",
            ".eggs", "*.pyc", "*.pyo", ".DS_Store", ".claude",
        }
        super().__init__(id=id, classes=classes)

    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        name = path.name
        for pattern in self._ignore:
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern:
                return True
        return False

    def _scan_files(self) -> list[str]:
        """Scan for files in the root directory."""
        files: list[str] = []
        try:
            for root, dirs, filenames in os.walk(self._root):
                # Filter ignored directories in-place
                dirs[:] = [d for d in dirs if not self._should_ignore(Path(d))]
                root_path = Path(root)
                for filename in filenames:
                    file_path = root_path / filename
                    if self._should_ignore(file_path):
                        continue
                    # Make relative to root
                    try:
                        rel = file_path.relative_to(self._root)
                        files.append(str(rel))
                    except ValueError:
                        files.append(str(file_path))
        except OSError:
            pass
        return sorted(files)

    def _fuzzy_match(self, query: str, text: str) -> tuple[float, list[int]]:
        """Simple fuzzy match - returns score and matched indices."""
        if not query:
            return 1.0, []

        query_lower = query.lower()
        text_lower = text.lower()

        score = 0.0
        matched: list[int] = []

        q_idx = 0
        for i, char in enumerate(text_lower):
            if q_idx < len(query_lower) and char == query_lower[q_idx]:
                score += 1.0
                matched.append(i)
                q_idx += 1

        if q_idx < len(query_lower):
            return 0.0, []

        # Penalty for gaps
        if matched:
            score -= (max(matched) - min(matched)) * 0.1

        return score / len(query), matched

    def _filter(self, query: str) -> list[str]:
        """Filter files by fuzzy query."""
        if not query:
            return self._all_files[:20]

        scored: list[tuple[str, float]] = []
        for f in self._all_files:
            score, _ = self._fuzzy_match(query, f)
            if score > 0:
                scored.append((f, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [f for f, _ in scored[:20]]

    def compose(self) -> ComposeResult:
        theme = get_theme()
        accent = theme.colors.get("accent", "cyan")

        yield Pane(title="Quick Open", border_color=accent)
        yield Input(placeholder="Search files... (Ctrl+P)", id="quick-open-input")
        yield Static("↑↓ navigate · Enter: open · Esc: cancel", id="quick-open-hint")
        with ScrollableContainer(id="quick-open-list"):
            pass  # Populated on mount

    def on_mount(self) -> None:
        """Scan files and show initial list."""
        self._all_files = self._scan_files()
        self._filtered = self._all_files[:20]
        self._refresh_list()
        self.query_one("#quick-open-input", Input).focus()

    def _refresh_list(self) -> None:
        """Refresh the file list display."""
        list_container = self.query_one("#quick-open-list", ScrollableContainer)
        list_container.remove_children()

        theme = get_theme()
        accent = theme.colors.get("accent", "cyan")
        dim = theme.colors.get("text_dim", "#555555")

        for i, file_path in enumerate(self._filtered[:15]):
            is_selected = i == self._selected_index
            prefix = "▶" if is_selected else " "
            color = accent if is_selected else dim

            # Show file with path truncated if too long
            display = file_path if len(file_path) <= 70 else "..." + file_path[-67:]
            list_container.mount(
                ListItem(
                    item_id=file_path,
                    label=f"[{color}]{prefix} {display}[/]",
                    description=str(Path(file_path).parent) if len(display) > 50 else "",
                )
            )

        hint = self.query_one("#quick-open-hint", Static)
        count = len(self._filtered)
        if count == 0:
            hint.update("[dim]no matching files[/dim]")
        else:
            hint.update(f"[dim]↑↓ navigate · Enter: open · Esc: cancel · {count} files[/dim]")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "quick-open-input":
            self._query = event.value
            self._filtered = self._filter(self._query)
            self._selected_index = 0
            self._refresh_list()

    def action_move_up(self) -> None:
        """Move selection up."""
        if self._filtered:
            self._selected_index = (self._selected_index - 1) % len(self._filtered[:15])
            self._refresh_list()

    def action_move_down(self) -> None:
        """Move selection down."""
        if self._filtered:
            self._selected_index = (self._selected_index + 1) % len(self._filtered[:15])
            self._refresh_list()

    def action_confirm(self) -> None:
        """Confirm selection."""
        if not self._filtered:
            return
        idx = self._selected_index
        if idx < len(self._filtered):
            path = self._filtered[idx]
            self.post_message(self.Selected(path))
            if self._on_select:
                self._on_select(path)
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
