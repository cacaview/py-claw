"""Pane — Colored border content container.

Re-implements ClaudeCode-main/src/components/design-system/Pane.tsx
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import Renderableeton
    from textual.css.styles import Styles
    from textual.widget import Widget

from textual.widgets import Static

from py_claw.ui.theme import get_theme


class Pane(Static):
    """A content container with colored border and header.

    Matches Pane.tsx behavior:
    - Colored border (typically primary color)
    - Optional title in header bar
    - Content area below header
    """

    def __init__(
        self,
        title: str | None = None,
        border_color: str | None = None,
        content: "Renderableeton" | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._title = title
        self._border_color = border_color or get_theme().colors.get("primary", "#3b82f6")
        super().__init__(content, id=id, classes=classes)

    def render(self) -> str:
        """Render the pane with border."""
        theme = get_theme()
        border = f"[{self._border_color}]{'─' * 40}[/]"

        lines = []
        lines.append(border)

        if self._title:
            title_bar = f"┤ {self._title} ├"
            lines[0] = f"[{self._border_color}]{title_bar.center(40, '─')}[/]"

        lines.append(border)

        return "\n".join(lines)
