"""PermissionDialog — Permission request dialog.

Re-implements ClaudeCode-main/src/components/design-system/PermissionDialog.tsx
"""

from __future__ import annotations

from enum import Enum
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.themed_text import ThemedText
from py_claw.ui.theme import get_theme


class PermissionDialog(Dialog):
    """Dialog for permission requests.

    Shows the tool being requested and its parameters,
    with Allow/Deny options.
    """

    def __init__(
        self,
        tool_name: str,
        message: str,
        params: dict | None = None,
        on_allow: Callable[[], None] | None = None,
        on_deny: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._tool_name = tool_name
        self._message = message
        self._params = params or {}
        super().__init__(
            title=f"Permission: {tool_name}",
            body=self._format_body(),
            confirm_label="Allow",
            deny_label="Deny",
            id=id,
            classes=classes,
        )
        self._on_allow = on_allow
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

    def set_callbacks(
        self,
        on_confirm: Callable[[], None] | None = None,
        on_deny: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Set permission-specific callbacks."""
        self._on_confirm = on_confirm
        self._on_deny = on_deny
        self._on_cancel = on_cancel

    def confirm(self) -> None:
        """Handle allow."""
        self._exit_state = ExitState.CONFIRMED
        if self._on_allow:
            self._on_allow()

    def deny(self) -> None:
        """Handle deny."""
        self._exit_state = ExitState.DENIED
        if self._on_deny:
            self._on_deny()
