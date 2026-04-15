"""ChromeDialog — Chrome Extension settings dialog.

Re-implements ClaudeCode-main/src/commands/chrome/chrome.tsx
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.themed_text import ThemedText


class ChromeDialog(Dialog):
    """Chrome Extension settings dialog.

    Provides options to:
    - Install Chrome extension
    - Manage permissions
    - Reconnect extension
    - Toggle default enable
    """

    def __init__(
        self,
        installed: bool,
        connected: bool,
        enabled_by_default: bool,
        on_install: Callable[[], None] | None = None,
        on_permissions: Callable[[], None] | None = None,
        on_reconnect: Callable[[], None] | None = None,
        on_toggle: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._installed = installed
        self._connected = connected
        self._enabled_by_default = enabled_by_default
        self._on_install = on_install
        self._on_permissions = on_permissions
        self._on_reconnect = on_reconnect
        self._on_toggle = on_toggle
        self._on_cancel = on_cancel
        super().__init__(
            title="Claude in Chrome (Beta)",
            confirm_label="Done",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the Chrome dialog."""
        # Description
        yield ThemedText(
            "Claude in Chrome works with the Chrome extension to let you control your browser "
            "directly from Claude Code. Navigate websites, fill forms, capture screenshots, "
            "record GIFs, and debug with console logs and network requests.",
            variant="normal",
        )

        # Status section
        with Vertical(id="chrome-status"):
            yield ThemedText(
                f"Status: {'Enabled' if self._connected else 'Disabled'}",
                variant="success" if self._connected else "inactive",
            )
            yield ThemedText(
                f"Extension: {'Installed' if self._installed else 'Not detected'}",
                variant="success" if self._installed else "warning",
            )

        # Buttons section
        with Horizontal(id="chrome-buttons"):
            if not self._installed:
                yield Button("Install Chrome Extension", id="btn-install", variant="primary")

            yield Button("Manage Permissions", id="btn-permissions", variant="default")
            yield Button("Reconnect Extension", id="btn-reconnect", variant="default")
            yield Button(
                f"Enabled by default: {'Yes' if self._enabled_by_default else 'No'}",
                id="btn-toggle",
                variant="default",
            )

        # Usage hint
        yield ThemedText(
            "Usage: claude --chrome or claude --no-chrome",
            variant="dim",
        )

        yield ThemedText(
            "Site-level permissions are inherited from the Chrome extension. "
            "Manage permissions in the Chrome extension settings to control which sites "
            "Claude can browse, click, and type on.",
            variant="dim",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-install" and self._on_install:
            self._on_install()
        elif event.button.id == "btn-permissions" and self._on_permissions:
            self._on_permissions()
        elif event.button.id == "btn-reconnect" and self._on_reconnect:
            self._on_reconnect()
        elif event.button.id == "btn-toggle" and self._on_toggle:
            self._on_toggle()
