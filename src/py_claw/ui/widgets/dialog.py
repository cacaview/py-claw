"""Dialog — Confirm/cancel dialog with keyboard handling.

Re-implements ClaudeCode-main/src/components/design-system/Dialog.tsx
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.widgets import Button

from textual import on
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Static

from py_claw.ui.widgets.pane import Pane
from py_claw.ui.theme import get_theme


class ExitState(Enum):
    """Dialog exit state."""

    CONFIRMED = "confirmed"
    DENIED = "denied"
    CANCELLED = "cancelled"


class Dialog(Container):
    """Confirm/cancel dialog with keyboard handling.

    Matches Dialog.tsx behavior:
    - title / subtitle / body / input guide
    - confirm:no + Ctrl+C exit semantics
    - Support for temporarily disabling cancel keybinding in embedded text input scenarios
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        body: str | None = None,
        subtitle: str | None = None,
        input_guide: str | None = None,
        confirm_label: str = "Confirm",
        deny_label: str = "Cancel",
        show_confirm_deny: bool = True,
        cancel_enabled: bool = True,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._title = title
        self._body = body
        self._subtitle = subtitle
        self._input_guide = input_guide
        self._confirm_label = confirm_label
        self._deny_label = deny_label
        self._show_confirm_deny = show_confirm_deny
        self._cancel_enabled = cancel_enabled
        self._exit_state: ExitState | None = None
        self._on_confirm: Callable[[], None] | None = None
        self._on_deny: Callable[[], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        super().__init__(id=id, classes=classes)

    def on_mount(self) -> None:
        """Set up dialog after mounting."""
        theme = get_theme()
        self.styles.background = theme.colors.get("surface", "#1a1a1a")
        self.styles.border = (theme.border_style, theme.colors.get("border", "#333333"))

    def compose(self) -> ComposeResult:
        """Compose the dialog layout."""
        yield Pane(title=self._title)

        with Vertical(id="dialog-content"):
            if self._subtitle:
                yield Static(self._subtitle, id="dialog-subtitle")

            if self._body:
                yield Static(self._body, id="dialog-body")

            if self._input_guide:
                yield Static(self._input_guide, id="dialog-input-guide")

        if self._show_confirm_deny:
            with Horizontal(id="dialog-buttons"):
                yield Button(self._confirm_label, id="btn-confirm", variant="primary")
                yield Button(self._deny_label, id="btn-deny", variant="default")

    def set_callbacks(
        self,
        on_confirm: Callable[[], None] | None = None,
        on_deny: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Set callback handlers for dialog actions."""
        self._on_confirm = on_confirm
        self._on_deny = on_deny
        self._on_cancel = on_cancel

    def get_exit_state(self) -> ExitState | None:
        """Get the dialog exit state after it closes."""
        return self._exit_state

    @on(Button.Pressed, "#btn-confirm")
    def confirm(self) -> None:
        """Handle confirm button press."""
        self._exit_state = ExitState.CONFIRMED
        if self._on_confirm:
            self._on_confirm()

    @on(Button.Pressed, "#btn-deny")
    def deny(self) -> None:
        """Handle deny/cancel button press."""
        self._exit_state = ExitState.DENIED
        if self._on_deny:
            self._on_deny()

    def action_cancel(self) -> None:
        """Handle cancel action (Ctrl+C / Escape)."""
        if not self._cancel_enabled:
            return
        self._exit_state = ExitState.CANCELLED
        if self._on_cancel:
            self._on_cancel()
