"""SessionScreen — Session management screen.

Re-implements ClaudeCode-main/src/screens/SessionScreen.tsx
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Static

from py_claw.ui.widgets.list_item import ListItem
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.themed_text import ThemedText
from py_claw.ui.theme import get_theme


class SessionScreen(Vertical):
    """Session management screen.

    Shows session list, allows selecting/resuming/deleting sessions.
    """

    def __init__(
        self,
        sessions: list[dict],  # list of {id, title, timestamp, message_count}
        on_select: Callable[[str], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_create: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._sessions = sessions
        self._on_select = on_select
        self._on_delete = on_delete
        self._on_create = on_create
        self._selected_session_id: str | None = None
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the session screen."""
        yield Header()

        with Horizontal(id="session-layout"):
            # Left panel - session list
            with Vertical(id="session-list-panel"):
                yield ThemedText("Sessions", variant="normal")
                yield Button("+ New Session", id="btn-new-session", variant="primary")

                with Vertical(id="session-list"):
                    for session in self._sessions:
                        session_id = session.get("id", "")
                        session_title = session.get("title", "Untitled")
                        session_count = session.get("message_count", 0)
                        yield ListItem(
                            item_id=session_id,
                            label=session_title,
                            description=f"{session_count} messages",
                            icon="💬",
                        )

            # Right panel - session preview
            with Vertical(id="session-preview-panel"):
                yield ThemedText("Preview", variant="normal")
                yield Pane(title="Session Preview")

                # Preview content would go here
                yield Static("Select a session to preview", id="session-preview-placeholder")

                # Action buttons
                with Horizontal(id="session-actions"):
                    yield Button("Resume", id="btn-resume-session", variant="primary")
                    yield Button("Delete", id="btn-delete-session", variant="error")

        yield Footer()

    def on_list_item_selected(self, event: ListItem.Selected) -> None:
        """Handle session selection."""
        self._selected_session_id = event.item_id

        # Update preview (in real implementation, would load session content)
        preview = self.query_one("#session-preview-placeholder", Static)
        preview.update(f"Preview of session: {event.item_id}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "btn-new-session" and self._on_create:
            self._on_create()
        elif button_id == "btn-resume-session" and self._selected_session_id:
            if self._on_select:
                self._on_select(self._selected_session_id)
        elif button_id == "btn-delete-session" and self._selected_session_id:
            if self._on_delete:
                self._on_delete(self._selected_session_id)
