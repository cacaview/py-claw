"""TrustDialog — Workspace trust confirmation dialog.

Re-implements ClaudeCode-main/src/components/TrustDialog/TrustDialog.tsx

Shows a safety check dialog when accessing a workspace for the first time,
prompting the user to confirm they trust the folder before allowing
file read/write/execute operations.
"""
from __future__ import annotations

import os
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.theme import get_theme


class TrustDialog(Dialog):
    """Trust confirmation dialog for workspace access.

    Shows when accessing a workspace to prompt user confirmation
    that they trust the folder before enabling full file operations.
    """

    def __init__(
        self,
        workspace_path: str,
        on_trust: Callable[[], None] | None = None,
        on_exit: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize trust dialog.

        Args:
            workspace_path: Path to the workspace being accessed
            on_trust: Callback when user chooses to trust
            on_exit: Callback when user chooses to exit
            id: Optional dialog ID
            classes: Optional CSS classes
        """
        self._workspace_path = workspace_path
        self._on_trust = on_trust
        self._on_exit = on_exit
        self._is_home_dir = self._check_is_home_dir()

        subtitle = self._build_subtitle()
        body = self._build_body()

        super().__init__(
            title="Accessing workspace:",
            body=body,
            subtitle=subtitle,
            input_guide="Enter to confirm · Esc to cancel",
            confirm_label="Yes, I trust this folder",
            deny_label="No, exit",
            id=id,
            classes=classes,
        )

    def _check_is_home_dir(self) -> bool:
        """Check if workspace is the user's home directory."""
        return os.path.expanduser("~") == self._workspace_path

    def _build_subtitle(self) -> str:
        """Build the subtitle showing the workspace path."""
        return self._workspace_path

    def _build_body(self) -> str:
        """Build the body text explaining the safety check."""
        return (
            "Quick safety check: Is this a project you created or one you trust? "
            "(Like your own code, a well-known open source project, or work from your team). "
            "If not, take a moment to review what's in this folder first.\n\n"
            "Claude Code will be able to read, edit, and execute files here."
        )

    def set_callbacks(
        self,
        on_trust: Callable[[], None] | None = None,
        on_exit: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Set dialog callbacks."""
        self._on_trust = on_trust
        self._on_exit = on_exit
        self._on_cancel = on_cancel

    def trust(self) -> None:
        """Handle trust confirmation."""
        self._exit_state = ExitState.CONFIRMED
        if self._on_trust:
            self._on_trust()

    def exit(self) -> None:
        """Handle exit (no trust)."""
        self._exit_state = ExitState.DENIED
        if self._on_exit:
            self._on_exit()

    def compose(self) -> ComposeResult:
        """Compose the dialog layout."""
        theme = get_theme()
        warning_color = theme.colors.get("warning", "#ffcc00")

        yield Pane(title=self.title)

        with Vertical(id="trust-dialog-content"):
            yield Static(self.subtitle or "", id="trust-path", markup=True)

            yield Static(
                "[warning]Quick safety check:[/warning] Is this a project you created "
                "or one you trust? (Like your own code, a well-known open source project, "
                "or work from your team). If not, take a moment to review what's in this "
                "folder first.",
                id="trust-message",
            )

            yield Static(
                "Claude Code will be able to read, edit, and execute files here.",
                id="trust-capabilities",
            )

            yield Static(
                "[dim]Security guide: https://code.claude.com/docs/en/security[/dim]",
                id="trust-link",
            )

        with Vertical(id="trust-buttons"):
            yield Button(
                "Yes, I trust this folder",
                id="btn-trust",
                variant="primary",
            )
            yield Button("No, exit", id="btn-exit", variant="default")

        yield Static(
            "Enter to confirm · Esc to cancel",
            id="trust-input-guide",
            classes="dim",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id
        if button_id == "btn-trust":
            self.trust()
        elif button_id == "btn-exit":
            self.exit()
