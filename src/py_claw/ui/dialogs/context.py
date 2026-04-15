"""ContextDialog — Context management dialog.

Re-implements context viewing and management dialog.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Button, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.themed_text import ThemedText


class ContextDialog(Dialog):
    """Context viewer and manager.

    Shows current context (files, messages, etc.) and allows
    clearing or modifying context.
    """

    def __init__(
        self,
        context_items: list[dict],  # list of {type, path, size, ...}
        on_clear: Callable[[], None] | None = None,
        on_remove_item: Callable[[str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._context_items = context_items
        self._on_clear = on_clear
        self._on_remove_item = on_remove_item
        self._on_cancel = on_cancel
        super().__init__(
            title="Context",
            confirm_label="Done",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the context dialog."""
        # Context summary
        total_size = sum(item.get("size", 0) for item in self._context_items)
        yield ThemedText(
            f"Total: {len(self._context_items)} items, {total_size} tokens",
            variant="muted",
        )

        # Context list
        with ScrollableContainer(id="context-list"):
            with Vertical():
                for i, item in enumerate(self._context_items):
                    item_type = item.get("type", "unknown")
                    item_path = item.get("path", item.get("name", ""))
                    item_size = item.get("size", 0)
                    yield Static(
                        f"[{item_type}] {item_path} ({item_size} tokens)",
                        id=f"context-item-{i}",
                    )

        # Action buttons
        yield Button("Clear All", id="btn-clear-context", variant="error")
