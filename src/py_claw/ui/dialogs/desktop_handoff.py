"""DesktopHandoff — Claude Desktop session handoff dialog.

Re-implements ClaudeCode-main/src/components/DesktopHandoff.tsx

Shows loading states while checking for Claude Desktop installation,
prompts for download if needed, and handles session transfer.
"""
from __future__ import annotations

import asyncio
import webbrowser
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Static

from py_claw.services.desktop_deep_link import (
    get_desktop_install_status_async,
    get_download_url,
    open_current_session_in_desktop_async,
)
from py_claw.services.session_storage import flush_session_storage
from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.spinner import Spinner


DESKTOP_DOCS_URL = "https://claude.de/desktop"


class DesktopHandoff(Dialog):
    """Dialog for transferring session to Claude Desktop.

    Shows loading states while checking install status,
    prompts for download/update if needed, and handles
    the session handoff via deep link.
    """

    # Dialog states
    STATE_CHECKING = "checking"
    STATE_PROMPT_DOWNLOAD = "prompt-download"
    STATE_FLUSHING = "flushing"
    STATE_OPENING = "opening"
    STATE_SUCCESS = "success"
    STATE_ERROR = "error"

    def __init__(
        self,
        session_id: str,
        cwd: str,
        on_done: Callable[[str | None, dict | None], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize desktop handoff dialog.

        Args:
            session_id: Current session ID to transfer
            cwd: Current working directory to pass to desktop
            on_done: Callback when handoff completes
            id: Optional dialog ID
            classes: Optional CSS classes
        """
        self._session_id = session_id
        self._cwd = cwd
        self._on_done = on_done
        self._state = self.STATE_CHECKING
        self._error: str | None = None
        self._download_message: str = ""
        self._task: asyncio.Task | None = None

        super().__init__(
            title="Transferring to Claude Desktop",
            subtitle="",
            show_confirm_deny=False,
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the dialog layout."""
        yield Pane(title=self.title)

        if self._state == self.STATE_ERROR:
            with Vertical(id="desktop-error"):
                yield Static(f"[error]Error: {self._error}[/error]", id="error-text")
                yield Static("[dim]Press any key to continue...[/dim]")

        elif self._state == self.STATE_PROMPT_DOWNLOAD:
            with Vertical(id="desktop-download-prompt"):
                yield Static(self._download_message)
                yield Static("Download now? (y/n)")

        else:
            # Loading states: checking, flushing, opening, success
            messages = {
                self.STATE_CHECKING: "Checking for Claude Desktop...",
                self.STATE_FLUSHING: "Saving session...",
                self.STATE_OPENING: "Opening Claude Desktop...",
                self.STATE_SUCCESS: "Opening in Claude Desktop...",
            }
            with Horizontal(id="desktop-loading"):
                yield Spinner()
                yield Static(messages.get(self._state, ""))

    def on_mount(self) -> None:
        """Start the handoff process on mount."""
        self._task = asyncio.create_task(self._perform_handoff())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id
        if button_id == "btn-yes":
            self._handle_yes()
        elif button_id == "btn-no":
            self._handle_no()

    def on_key(self, event) -> None:
        """Handle key press for error and prompt-download states."""
        if self._state == self.STATE_ERROR:
            self._handle_error_dismiss()
        elif self._state == self.STATE_PROMPT_DOWNLOAD:
            key = event.key.name if hasattr(event.key, "name") else str(event.key)
            if key in ("y", "Y"):
                self._handle_yes()
            elif key in ("n", "N"):
                self._handle_no()

    def _handle_error_dismiss(self) -> None:
        """Handle dismissing the error state."""
        self._exit_state = ExitState.CANCELLED
        if self._on_done:
            self._on_done(self._error or "Unknown error", {"display": "system"})

    def _handle_yes(self) -> None:
        """Handle yes response to download prompt."""
        url = get_download_url()
        try:
            webbrowser.open(url)
        except Exception:
            pass
        message = (
            f"Starting download. Re-run /desktop once you've installed the app.\n"
            f"Learn more at {DESKTOP_DOCS_URL}"
        )
        self._exit_state = ExitState.CONFIRMED
        if self._on_done:
            self._on_done(message, {"display": "system"})

    def _handle_no(self) -> None:
        """Handle no response to download prompt."""
        message = (
            f"The desktop app is required for /desktop. "
            f"Learn more at {DESKTOP_DOCS_URL}"
        )
        self._exit_state = ExitState.CANCELLED
        if self._on_done:
            self._on_done(message, {"display": "system"})

    async def _perform_handoff(self) -> None:
        """Perform the desktop handoff process."""
        try:
            # Check install status
            self._state = self.STATE_CHECKING
            self.refresh()

            status = await get_desktop_install_status_async()

            if status.status == "not-installed":
                self._download_message = "Claude Desktop is not installed."
                self._state = self.STATE_PROMPT_DOWNLOAD
                self.refresh()
                return

            if status.status == "version-too-old":
                self._download_message = (
                    f"Claude Desktop needs to be updated "
                    f"(found v{status.version}, need v1.1.2396+)."
                )
                self._state = self.STATE_PROMPT_DOWNLOAD
                self.refresh()
                return

            # Flush session storage
            self._state = self.STATE_FLUSHING
            self.refresh()

            try:
                await flush_session_storage()
            except Exception:
                pass  # Best effort flush

            # Open desktop
            self._state = self.STATE_OPENING
            self.refresh()

            result = await open_current_session_in_desktop_async(
                self._session_id, self._cwd
            )

            if not result.get("success", False):
                self._error = result.get(
                    "error", "Failed to open Claude Desktop"
                )
                self._state = self.STATE_ERROR
                self.refresh()
                return

            # Success - give user a moment to see the message
            self._state = self.STATE_SUCCESS
            self.refresh()

            # Wait a bit then call done
            await asyncio.sleep(0.5)

            self._exit_state = ExitState.CONFIRMED
            if self._on_done:
                self._on_done(
                    "Session transferred to Claude Desktop",
                    {"display": "system"},
                )

        except Exception as e:
            self._error = str(e) if e else "Unknown error"
            self._state = self.STATE_ERROR
            self.refresh()

    def on_leave(self) -> None:
        """Clean up on leave."""
        if self._task and not self._task.done():
            self._task.cancel()
