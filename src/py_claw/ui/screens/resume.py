"""Resume screen — Session restoration.

Re-implements ClaudeCode-main/src/screens/ResumeConversation.tsx
as a Textual screen with real session loading and keyboard navigation.

Features:
- Load sessions from session_storage via search_sessions()
- Keyboard navigation (↑↓ to select, Enter to resume, Esc to cancel)
- All projects / same repo toggle
- Session metadata display (title, timestamp, project)
- Lazy loading with pagination
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.dialog import Dialog
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.themed_text import ThemedText

if TYPE_CHECKING:
    from py_claw.services.session_storage.search import SessionSearchResult


class ResumeScreen(Vertical):
    """Session resume screen with keyboard navigation.

    Allows user to select a previous session to restore.
    Supports keyboard navigation (↑↓ Enter Esc a) and loads sessions
    from session_storage asynchronously.
    """

    # Keyboard bindings
    BINDINGS = [
        ("up", "cursor_up", "Move up"),
        ("down", "cursor_down", "Move down"),
        ("enter", "select", "Resume session"),
        ("escape", "cancel", "Cancel"),
        ("a", "toggle_all", "Toggle all projects"),
    ]

    def __init__(
        self,
        worktree_paths: list[str] | None = None,
        on_resume: Callable[[list[dict]], None] | None = None,
        on_discard: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Args:
            worktree_paths: List of worktree paths for same-repo filtering
            on_resume: Callback(session_id) when user selects a session
            on_discard: Callback() when user starts fresh
        """
        super().__init__(id=id, classes=classes)
        self._worktree_paths = worktree_paths or []
        self._on_resume = on_resume
        self._on_discard = on_discard
        self._sessions: list["SessionSearchResult"] = []
        self._selected_index = 0
        self._show_all_projects = False
        self._loading = True
        self._loading_more = False
        self._offset = 0
        self._has_more = True
        self._error: str | None = None

    # ── Reactives ────────────────────────────────────────────────────────────

    selected_index: reactive[int] = reactive(0)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Load sessions on mount."""
        asyncio.create_task(self._load_sessions())

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_cursor_up(self) -> None:
        """Move cursor up in the session list."""
        if self._sessions:
            self._selected_index = (self._selected_index - 1) % len(self._sessions)
            self._refresh_session_highlight()

    def action_cursor_down(self) -> None:
        """Move cursor down in the session list."""
        if self._sessions:
            self._selected_index = (self._selected_index + 1) % len(self._sessions)
            self._refresh_session_highlight()

    def action_select(self) -> None:
        """Resume the selected session."""
        if not self._sessions or self._loading:
            return
        session = self._sessions[self._selected_index]
        asyncio.create_task(self._load_and_resume(session))

    def action_cancel(self) -> None:
        """Cancel resume, start fresh."""
        if self._on_discard:
            self._on_discard()

    def action_toggle_all(self) -> None:
        """Toggle between same-repo and all projects."""
        self._show_all_projects = not self._show_all_projects
        self._offset = 0
        self._sessions = []
        self._selected_index = 0
        asyncio.create_task(self._load_sessions())

    # ── Session loading ───────────────────────────────────────────────────────

    async def _load_sessions(self) -> None:
        """Load sessions from session storage."""
        self._loading = True
        self._error = None
        self._refresh_title()

        try:
            from py_claw.services.session_storage.search import search_sessions

            # Determine project path
            if self._show_all_projects:
                project_path = None
            else:
                project_path = self._worktree_paths[0] if self._worktree_paths else None

            results = await search_sessions(
                project_path=project_path,
                limit=20,
                offset=self._offset,
            )

            if self._offset == 0:
                self._sessions = results
            else:
                self._sessions.extend(results)

            self._has_more = len(results) == 20
            self._loading = False
            self._selected_index = min(self._selected_index, max(0, len(self._sessions) - 1))

        except Exception as e:
            self._error = str(e)
            self._loading = False

        self._refresh_session_list()

    async def _load_more_sessions(self) -> None:
        """Load more sessions (pagination)."""
        if self._loading_more or not self._has_more:
            return

        self._loading_more = True
        self._offset += 20

        try:
            from py_claw.services.session_storage.search import search_sessions

            project_path = None if self._show_all_projects else (self._worktree_paths[0] if self._worktree_paths else None)

            results = await search_sessions(
                project_path=project_path,
                limit=20,
                offset=self._offset,
            )

            self._sessions.extend(results)
            self._has_more = len(results) == 20

        except Exception:
            pass

        self._loading_more = False
        self._refresh_session_list()

    async def _load_and_resume(self, session: "SessionSearchResult") -> None:
        """Load a session and invoke the resume callback."""
        try:
            from py_claw.services.session_storage.storage import load_session_for_resume

            data = await load_session_for_resume(session.session_id, session.project_path)
            if data and self._on_resume:
                self._on_resume(data["messages"])
        except Exception:
            pass

    # ── UI helpers ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Compose the resume screen."""
        yield Static("Resume Session", id="resume-title")
        yield Horizontal(
            Button(
                "All Projects" if self._show_all_projects else "Same Repo",
                id="btn-toggle-projects",
                variant="default",
            ),
            Static("loading...", id="session-count"),
            id="resume-header",
        )
        with Vertical(id="session-list"):
            if self._loading:
                yield Static("Loading sessions...", id="loading-indicator", classes="resume-loading")
            elif self._error:
                yield Static(f"Error: {self._error}", id="error-indicator", classes="resume-error")
            elif not self._sessions:
                yield Static("No sessions found", id="empty-indicator", classes="resume-empty")
        yield Horizontal(
            Button("Resume", id="btn-resume", variant="primary", disabled=True),
            Button("New Session", id="btn-discard", variant="default"),
            id="resume-actions",
        )
        yield Static(
            "↑↓ navigate · Enter resume · a: all projects · Esc: cancel",
            id="resume-help",
        )

    def _refresh_title(self) -> None:
        """Refresh the title area."""
        title = self.query_one("#resume-title", Static)
        mode = "All Projects" if self._show_all_projects else "Same Repo"
        title.update(f"Resume Session [{mode}]")

    def _refresh_session_count(self) -> None:
        """Refresh the session count."""
        count = self.query_one("#session-count", Static)
        if self._loading:
            count.update("loading...")
        elif self._error:
            count.update("error")
        else:
            count.update(f"{len(self._sessions)} sessions" + (" (more)" if self._has_more else ""))

    def _refresh_session_list(self) -> None:
        """Refresh the session list display."""
        self._refresh_session_count()

        list_container = self.query_one("#session-list", Vertical)
        list_container.remove_children()

        if self._loading or self._error or not self._sessions:
            return

        from py_claw.services.session_storage.search import format_session_timestamp

        for i, session in enumerate(self._sessions):
            is_selected = i == self._selected_index
            prefix = "▶ " if is_selected else "  "
            title = session.custom_title or session.first_prompt or "Untitled"
            if len(title) > 60:
                title = title[:57] + "..."
            timestamp = format_session_timestamp(session.mtime)
            project = ""
            if session.project_path:
                import os
                project = os.path.basename(session.project_path)
                if len(project) > 20:
                    project = project[:17] + "..."

            item = SessionItem(
                prefix=prefix,
                title=title,
                timestamp=timestamp,
                project=project,
                is_selected=is_selected,
            )
            list_container.mount(item)

    def _refresh_session_highlight(self) -> None:
        """Refresh only the selection highlight without reloading the list."""
        list_container = self.query_one("#session-list", Vertical)
        for i, child in enumerate(list_container.children):
            if isinstance(child, SessionItem):
                child.update_selection(i == self._selected_index)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-toggle-projects":
            self.action_toggle_all()
        elif button_id == "btn-resume":
            self.action_select()
        elif button_id == "btn-discard":
            self.action_cancel()

    def on_resume_screen_session_selected(self, event: "ResumeScreen.SessionSelected") -> None:
        """Handle session selection from a SessionItem."""
        self._selected_index = event.index
        self.action_select()


class SessionItem(Static):
    """A single session item in the resume list."""

    def __init__(
        self,
        prefix: str = "  ",
        title: str = "",
        timestamp: str = "",
        project: str = "",
        is_selected: bool = False,
    ) -> None:
        super().__init__()
        self._prefix = prefix
        self._title = title
        self._timestamp = timestamp
        self._project = project
        self._is_selected = is_selected

    def update_selection(self, is_selected: bool) -> None:
        """Update the selection state."""
        self._is_selected = is_selected
        self._prefix = "▶ " if is_selected else "  "
        self._refresh()

    def _refresh(self) -> None:
        """Refresh the display text."""
        theme = get_theme()
        if self._is_selected:
            fg = theme.colors.get("text", "#ffffff")
        else:
            fg = theme.colors.get("text", "#ffffff")
        from rich.text import Text
        text = Text()
        text.append(self._prefix, style=f"bold {fg}" if self._is_selected else fg)
        text.append(self._title, style=fg)
        text.append(f"  {self._timestamp}", style=theme.colors.get("text_dim", "#888888"))
        if self._project:
            dim = theme.colors.get("text_dim", "#888888")
            text.append(f" · {self._project}", style=dim)
        self.update(text)

    def on_mount(self) -> None:
        """Mount and set content."""
        self._refresh()


class ResumeApp(App):
    """Standalone Resume application for testing."""

    CSS = """
    Screen {
        background: $background;
    }
    #resume-content {
        height: 100%;
        padding: 2;
    }
    .session-button {
        margin: 1 0;
    }
    """

    BINDINGS = [("escape", "quit", "Quit"), ("ctrl+c", "quit", "Quit")]

    def __init__(self, sessions: list[dict] | None = None) -> None:
        self._sessions = sessions or [
            {"id": "1", "label": "Session 1 - Yesterday"},
            {"id": "2", "label": "Session 2 - 2 days ago"},
        ]
        super().__init__()

    def compose(self) -> ComposeResult:
        """Compose the app."""
        yield Header()
        with Vertical(id="resume-content"):
            yield ThemedText("Resume Previous Session", variant="normal")
            yield Static("Select a session to continue:", id="resume-prompt")
            with Vertical(id="session-list"):
                for i, session in enumerate(self._sessions):
                    session_id = session.get("id", f"session-{i}")
                    session_label = session.get("label", f"Session {i + 1}")
                    yield Button(
                        session_label,
                        id=f"session-btn-{session_id}",
                        classes="session-button",
                    )
            yield Static("", id="resume-spacer")
            yield Button("Resume Selected", id="btn-resume", variant="primary")
            yield Button("Start Fresh", id="btn-discard", variant="default")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "btn-resume":
            selected = self.query_one("#session-list Button:focused", Button)
            if selected and self._on_resume:
                session_id = selected.id.replace("session-btn-", "")
                self._on_resume(session_id)

        elif button_id == "btn-discard":
            if self._on_discard:
                self._on_discard()

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()
