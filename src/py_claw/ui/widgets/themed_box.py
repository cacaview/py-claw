"""ThemedBox — Theme-aware box container.

Re-implements ClaudeCode-main/src/components/design-system/ThemedBox.tsx
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import Renderableeton

from textual.widgets import Static

from py_claw.ui.theme import get_theme


class ThemedBox(Static):
    """A box container with theme-aware colors.

    Provides a simple colored box that adapts to the current theme.
    """

    def __init__(
        self,
        content: "Renderableeton" | None = None,
        background_color: str | None = None,
        border_color: str | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._background_color = background_color
        self._border_color = border_color
        super().__init__(content, id=id, classes=classes)

    def on_mount(self) -> None:
        """Apply theme-aware styling."""
        theme = get_theme()

        if self._background_color:
            self.styles.background = self._background_color
        else:
            self.styles.background = theme.colors.get("surface", "#1a1a1a")

        if self._border_color:
            self.styles.border = (theme.border_style, self._border_color)
