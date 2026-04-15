"""Resume screen — Session restoration.

Re-implements ClaudeCode-main/src/screens/ResumeConversation.tsx
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.app import App
from textual.containers import Vertical
from textual.widgets import Button, Footer, Header, Static

from py_claw.ui.widgets.dialog import Dialog
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.themed_text import ThemedText
from py_claw.ui.theme import get_theme


class ResumeScreen(Vertical):
    """Resume conversation screen.

    Allows user to select a previous session to restore.
    """

    def __init__(
        self,
        sessions: list[dict],  # list of session info dicts
        on_resume: Callable[[str], None] | None = None,
        on_discard: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._sessions = sessions
        self._on_resume = on_resume
        self._on_discard = on_discard
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the resume screen layout."""
        yield Header()

        with Vertical(id="resume-content"):
            yield ThemedText("Resume Previous Session", variant="normal")

            yield Static("Select a session to continue:", id="resume-prompt")

            # Session list
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

            # Action buttons
            yield Button("Resume Selected", id="btn-resume", variant="primary")
            yield Button("Start Fresh", id="btn-discard", variant="default")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "btn-resume":
            # Find selected session
            selected = self.query_one("#session-list Button:focused", Button)
            if selected and self._on_resume:
                session_id = selected.id.replace("session-btn-", "")
                self._on_resume(session_id)

        elif button_id == "btn-discard":
            if self._on_discard:
                self._on_discard()


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
        yield ResumeScreen(
            sessions=self._sessions,
            on_resume=lambda sid: print(f"Resuming {sid}"),
            on_discard=lambda: print("Starting fresh"),
        )

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()
