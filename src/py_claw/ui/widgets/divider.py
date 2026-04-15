"""Divider — Visual separator line.

Re-implements ClaudeCode-main/src/components/design-system/Divider.tsx
"""

from __future__ import annotations

from textual.widgets import Static

from py_claw.ui.theme import get_theme


class Divider(Static):
    """A horizontal or vertical divider line.

    Uses box-drawing characters for a clean terminal appearance.
    """

    def __init__(
        self,
        vertical: bool = False,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._vertical = vertical
        super().__init__(id=id, classes=classes)

    def on_mount(self) -> None:
        """Apply divider styling."""
        theme = get_theme()
        self.styles.color = theme.colors.get("border", "#333333")

        if self._vertical:
            self.update("│")
        else:
            self.update("─" * 40)
