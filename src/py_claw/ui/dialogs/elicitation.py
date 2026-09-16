"""ElicitationDialog — MCP elicitation (server-initiated user prompt) dialog.

Minimal Textual dialog that presents an MCP server's elicitation request to
the user and collects the answer:

- form mode: the server's ``message`` plus one input per top-level property
  of ``requestedSchema`` (a single "value" input when no schema is given).
  Buttons: Accept / Decline.
- url mode: the server's ``message`` plus the ``url`` the user should visit.
  Buttons: Completed / Cancel. The server's ``complete`` notification can
  also resolve the request out-of-band (ElicitationHandler handles that).

Escape / Ctrl+C always means "cancel" so a pending elicitation can never
strand the waiting worker (same contract as PermissionDialog's Esc=deny).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.pane import Pane


def _field_id(name: str) -> str:
    """Build a Textual-safe widget id for a schema property name."""
    sanitized = re.sub(r"\W+", "_", name).strip("_")
    return f"field-{sanitized}" if sanitized else "field-value"


class ElicitationDialog(Dialog):
    """Minimal dialog for MCP elicitation requests.

    Registers its own ``@on(Button.Pressed, ...)`` handlers rather than
    relying on the inherited ``Dialog.confirm`` — a plain override would
    shadow the decorated base handler and the buttons would never act
    (same pattern as PermissionDialog / PromptDialog).
    """

    def __init__(
        self,
        server_name: str,
        message: str,
        *,
        mode: str = "form",
        url: str | None = None,
        requested_schema: dict[str, Any] | None = None,
        on_accept: Callable[[dict[str, Any] | None], None] | None = None,
        on_decline: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._server_name = server_name
        self._message = message or ""
        self._mode = "url" if mode == "url" else "form"
        self._url = url
        # (schema property name, widget id, label, default value)
        self._fields: list[tuple[str, str, str, str]] = []

        if self._mode == "url":
            body = f"{self._message}\n\n{url}" if url else self._message
            confirm_label, deny_label = "Completed", "Cancel"
        else:
            self._fields = self._build_fields(requested_schema)
            body = self._message
            confirm_label, deny_label = "Accept", "Decline"

        super().__init__(
            title=f"Elicitation: {server_name}",
            body=body,
            confirm_label=confirm_label,
            deny_label=deny_label,
            show_confirm_deny=False,
            id=id,
            classes=classes,
        )
        # NOTE: assign callbacks AFTER super().__init__ — Dialog.__init__
        # resets the base callback slots to None.
        self._on_accept = on_accept
        self._on_decline = on_decline
        self._on_cancel_cb = on_cancel

    @staticmethod
    def _build_fields(
        requested_schema: dict[str, Any] | None,
    ) -> list[tuple[str, str, str, str]]:
        """Derive the form fields from the top level of requestedSchema."""
        fields: list[tuple[str, str, str, str]] = []
        properties = (
            requested_schema.get("properties")
            if isinstance(requested_schema, dict)
            else None
        )
        if isinstance(properties, dict) and properties:
            for name, spec in properties.items():
                label = str(name)
                default = ""
                if isinstance(spec, dict):
                    if isinstance(spec.get("title"), str) and spec["title"]:
                        label = spec["title"]
                    default_value = spec.get("default")
                    if isinstance(default_value, (str, int, float, bool)):
                        default = str(default_value)
                fields.append((str(name), _field_id(str(name)), label, default))
        if not fields:
            # No (usable) schema: a single free-form answer.
            fields.append(("value", "field-value", "value", ""))
        return fields

    def compose(self) -> ComposeResult:
        """Compose the dialog layout with elicitation-specific controls."""
        yield Pane(title=self._title)

        with Vertical(id="dialog-content"):
            if self._body:
                yield Static(self._body, id="dialog-body")
            if self._mode == "form":
                for _name, field_id, label, default in self._fields:
                    yield Static(label, id=f"{field_id}-label")
                    yield Input(value=default, id=field_id, placeholder=label)

        with Horizontal(id="dialog-buttons"):
            yield Button(self._confirm_label, id="btn-confirm", variant="primary")
            yield Button(self._deny_label, id="btn-deny", variant="default")

    def collect_values(self) -> dict[str, Any]:
        """Read the current form values keyed by schema property name."""
        values: dict[str, Any] = {}
        for name, field_id, _label, _default in self._fields:
            try:
                values[name] = self.query_one(f"#{field_id}", Input).value
            except Exception:
                continue
        return values

    def accept(self) -> None:
        """Handle Accept (form) / Completed (url)."""
        self._exit_state = ExitState.CONFIRMED
        content: dict[str, Any] | None = None
        if self._mode == "form":
            # Empty answers are omitted; an all-empty form carries no content.
            content = {k: v for k, v in self.collect_values().items() if v != ""} or None
        if self._on_accept:
            self._on_accept(content)

    def decline(self) -> None:
        """Handle Decline (form mode only)."""
        self._exit_state = ExitState.DENIED
        if self._on_decline:
            self._on_decline()

    def cancel(self) -> None:
        """Handle Cancel / Escape."""
        self._exit_state = ExitState.CANCELLED
        if self._on_cancel_cb:
            self._on_cancel_cb()

    def deny(self) -> None:
        """Uniform deny entry point (used by app-level interrupt handling).

        Escape on a pending elicitation means cancel.
        """
        self.cancel()

    @on(Button.Pressed, "#btn-confirm")
    def _confirm_pressed(self) -> None:
        self.accept()

    @on(Button.Pressed, "#btn-deny")
    def _deny_pressed(self) -> None:
        if self._mode == "url":
            self.cancel()
        else:
            self.decline()

    def action_cancel(self) -> None:
        """Escape / Ctrl+C on a pending elicitation means cancel.

        The query worker blocks while this dialog is visible, so Escape must
        resolve it — otherwise the dialog becomes an orphan and the turn can
        never resume.
        """
        if not self._cancel_enabled:
            return
        self.cancel()
