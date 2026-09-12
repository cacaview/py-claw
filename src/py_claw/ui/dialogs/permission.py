"""PermissionDialog — Permission request dialog.

Re-implements ClaudeCode-main/src/components/design-system/PermissionDialog.tsx
"""

from __future__ import annotations

from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.pane import Pane


class PermissionDialog(Dialog):
    """Dialog for permission requests.

    Shows the tool being requested and its parameters, with Allow /
    Allow-always / Deny options.

    NOTE: this dialog composes its own buttons and registers its own
    ``@on(Button.Pressed, ...)`` handlers instead of overriding the base
    ``Dialog.confirm``/``Dialog.deny`` decorated methods. Overriding those
    names without the decorator silently shadows the base handlers — Textual
    dispatches via the class where the handler was declared, which previously
    made the Allow/Deny buttons dead (the dialog could never be satisfied).
    """

    def __init__(
        self,
        tool_name: str,
        message: str,
        params: dict | None = None,
        on_allow: Callable[[], None] | None = None,
        on_always_allow: Callable[[], None] | None = None,
        on_deny: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._tool_name = tool_name
        self._message = message
        self._params = params or {}
        # NOTE: assign callbacks AFTER super().__init__ — Dialog.__init__
        # resets _on_confirm/_on_deny/_on_cancel to None.
        super().__init__(
            title=f"Permission: {tool_name}",
            body=self._format_body(),
            confirm_label="Allow",
            deny_label="Deny",
            show_confirm_deny=False,
            id=id,
            classes=classes,
        )
        self._on_allow = on_allow
        self._on_always_allow = on_always_allow
        self._on_deny = on_deny

    def _format_body(self) -> str:
        """Format the permission request body."""
        lines = [self._message, ""]

        if self._params:
            lines.append("Parameters:")
            for key, value in self._params.items():
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                lines.append(f"  {key}: {value_str}")

        return "\n".join(lines)

    def compose(self) -> ComposeResult:
        """Compose the dialog layout with permission-specific buttons."""
        from textual.containers import Vertical
        from textual.widgets import Static

        yield Pane(title=self._title)

        with Vertical(id="dialog-content"):
            if self._body:
                yield Static(self._body, id="dialog-body")

        with Horizontal(id="dialog-buttons"):
            # The Allow button keeps the base-class id "btn-confirm" so the
            # inherited @on(Button.Pressed, "#btn-confirm") wiring and any
            # caller querying "#btn-confirm" keep working alongside the
            # permission-specific Always-allow button.
            yield Button("Allow", id="btn-confirm", variant="primary")
            yield Button("Always allow", id="btn-always-allow", variant="success")
            yield Button("Deny", id="btn-deny", variant="error")

    @property
    def default_focus_button_id(self) -> str:
        return "#btn-confirm"

    @on(Button.Pressed, "#btn-confirm")
    def _allow_pressed(self) -> None:
        self.confirm()

    @on(Button.Pressed, "#btn-always-allow")
    def _always_allow_pressed(self) -> None:
        self.always_allow()

    # NOTE: no @on handler for "#btn-deny" here — the base class's decorated
    # deny() already matches that selector; adding a second handler would fire
    # the on_deny callback twice.

    def confirm(self) -> None:
        """Handle allow."""
        self._exit_state = ExitState.CONFIRMED
        if self._on_allow:
            self._on_allow()

    def always_allow(self) -> None:
        """Handle allow + remember for the rest of the session."""
        self._exit_state = ExitState.CONFIRMED
        if self._on_always_allow:
            self._on_always_allow()
        elif self._on_allow:
            self._on_allow()

    def deny(self) -> None:
        """Handle deny."""
        self._exit_state = ExitState.DENIED
        if self._on_deny:
            self._on_deny()

    def action_cancel(self) -> None:
        """Escape on a pending permission request means deny.

        The query worker blocks while this dialog is visible, so Escape must
        resolve it — otherwise the dialog becomes an orphan and the turn can
        never resume.
        """
        if not self._cancel_enabled:
            return
        self.deny()

    def set_callbacks(
        self,
        on_confirm: Callable[[], None] | None = None,
        on_deny: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Set permission-specific callbacks (on_confirm aliases allow)."""
        if on_confirm is not None:
            self._on_allow = on_confirm
        if on_deny is not None:
            self._on_deny = on_deny
        if on_cancel is not None:
            self._on_cancel = on_cancel
