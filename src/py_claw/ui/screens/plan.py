"""PlanScreen — Plan mode screen.

Re-implements ClaudeCode-main/src/screens/PlanMode.tsx
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Static

from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.tabs import Tabs
from py_claw.ui.widgets.themed_text import ThemedText
from py_claw.ui.widgets.divider import Divider


class PlanModeScreen(Vertical):
    """Plan mode screen.

    Shows plan approval interface with before/after views.
    """

    def __init__(
        self,
        current_plan: str,
        proposed_changes: str,
        on_approve: Callable[[], None] | None = None,
        on_reject: Callable[[], None] | None = None,
        on_modify: Callable[[str], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._current_plan = current_plan
        self._proposed_changes = proposed_changes
        self._on_approve = on_approve
        self._on_reject = on_reject
        self._on_modify = on_modify
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the plan mode screen."""
        yield Header()

        with Vertical(id="plan-content"):
            yield ThemedText("Plan Mode", variant="normal")
            yield ThemedText("Review the proposed changes below", variant="muted")

            yield Divider()

            # Before/After tabs
            tabs = Tabs(
                tabs=[
                    ("current", "Current"),
                    ("proposed", "Proposed"),
                ],
                id="plan-tabs",
            )
            yield tabs

            yield Divider()

            # Plan display
            with Horizontal(id="plan-display"):
                with Vertical(id="plan-current"):
                    yield ThemedText("Current Plan:", variant="normal")
                    yield Static(self._current_plan, id="plan-current-text")
                with Vertical(id="plan-proposed"):
                    yield ThemedText("Proposed Changes:", variant="normal")
                    yield Static(self._proposed_changes, id="plan-proposed-text")

            yield Divider()

            # Modification input
            yield ThemedText("Modify plan (optional):", variant="normal")
            yield Input(placeholder="Enter modifications...", id="plan-modify-input")

            # Action buttons
            with Horizontal(id="plan-actions"):
                yield Button("Approve", id="btn-approve", variant="primary")
                yield Button("Reject", id="btn-reject", variant="error")
                yield Button("Modify & Approve", id="btn-modify", variant="default")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "btn-approve" and self._on_approve:
            self._on_approve()
        elif button_id == "btn-reject" and self._on_reject:
            self._on_reject()
        elif button_id == "btn-modify":
            modify_input = self.query_one("#plan-modify-input", Input)
            if self._on_modify:
                self._on_modify(modify_input.value)
