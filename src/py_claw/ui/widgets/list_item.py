"""ListItem — Reusable list item component.

Re-implements ClaudeCode-main/src/components/design-system/ListItem.tsx
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.themed_text import ThemedText


def _sanitize_item_id(item_id: str, index: int | None = None) -> str:
    """Convert arbitrary item ids into Textual-safe widget ids.

    Adds an optional numeric index suffix to prevent collisions when the same
    item_id is used multiple times within a dialog.
    """
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "-", item_id)
    sanitized = sanitized.strip("-")
    if not sanitized:
        sanitized = "item"
    if sanitized[0].isdigit():
        sanitized = f"item-{sanitized}"
    if index is not None:
        sanitized = f"{sanitized}-{index}"
    return sanitized


class ListItem(Horizontal):
    """A selectable list item with optional icon, label, and description.

    Supports:
    - Icon prefix (status icon or custom)
    - Label with optional muted description
    - Selected state styling
    - Keyboard focus indication
    """

    class Selected(Message):
        """Message sent when item is selected via click."""

        def __init__(self, item_id: str) -> None:
            self.item_id = item_id
            super().__init__()

    def __init__(
        self,
        item_id: str,
        label: str,
        description: str | None = None,
        icon: str | None = None,
        selected: bool = False,
        on_click: Callable[[str], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
        item_index: int | None = None,
    ) -> None:
        self.item_id = item_id
        self._label = label
        self._description = description
        self._icon = icon
        self._selected = selected
        self._on_click = on_click
        super().__init__(
            id=id if id is not None else f"list-item-{_sanitize_item_id(item_id, item_index)}",
            classes=classes,
        )

    def on_mount(self) -> None:
        """Apply styling based on state."""
        theme = get_theme()
        self.styles.padding = (1, 2)

        if self._selected:
            self.styles.background = theme.colors.get("surface_elevated", "#252525")
        else:
            self.styles.background = theme.colors.get("surface", "#1a1a1a")

        # Build content
        content_parts = []
        if self._icon:
            content_parts.append(ThemedText(self._icon, variant="normal"))
        content_parts.append(ThemedText(self._label, variant="normal"))

        if self._description:
            content_parts.append(ThemedText(f" — {self._description}", variant="muted"))

        # Clear and add content
        self.remove_children()
        for part in content_parts:
            self.mount(part)

    def on_click(self) -> None:
        """Handle click selection."""
        self.post_message(self.Selected(self.item_id))
        if self._on_click:
            self._on_click(self.item_id)
