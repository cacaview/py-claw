"""ShareDialog — Share conversation dialog.

Re-implements ClaudeCode-main/src/components/design-system/ShareDialog.tsx
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Horizontal
from textual.widgets import Button, Input, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.themed_text import ThemedText


class ShareDialog(Dialog):
    """Share conversation dialog.

    Allows sharing conversation via link, export, or other methods.
    """

    def __init__(
        self,
        conversation_id: str,
        share_url: str | None = None,
        on_share: Callable[[str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._conversation_id = conversation_id
        self._share_url = share_url or f"https://claude.ai/share/{conversation_id}"
        self._on_share = on_share
        self._on_cancel = on_cancel
        super().__init__(
            title="Share Conversation",
            confirm_label="Copy Link",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the share dialog."""
        yield ThemedText("Share this conversation", variant="normal")

        # Share URL display
        yield ThemedText("Share URL:", variant="muted")
        share_input = Input(value=self._share_url, id="share-url-input", read_only=True)
        yield share_input

        # Copy button
        yield Button("Copy to Clipboard", id="btn-copy", variant="primary")

        # Export options
        yield ThemedText("Or export as:", variant="muted")
        with Horizontal(id="export-buttons"):
            yield Button("JSON", id="btn-export-json", variant="default")
            yield Button("Markdown", id="btn-export-md", variant="default")
            yield Button("Text", id="btn-export-txt", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "btn-copy":
            # Copy URL to clipboard (Textual handles this)
            share_input = self.query_one("#share-url-input", Input)
            # In a real implementation, would copy to clipboard
            if self._on_share:
                self._on_share(self._share_url)

        elif button_id == "btn-export-json":
            if self._on_share:
                self._on_share("json")
        elif button_id == "btn-export-md":
            if self._on_share:
                self._on_share("markdown")
        elif button_id == "btn-export-txt":
            if self._on_share:
                self._on_share("text")

    def confirm(self) -> None:
        """Handle confirm - copy link."""
        if self._on_share:
            self._on_share(self._share_url)
