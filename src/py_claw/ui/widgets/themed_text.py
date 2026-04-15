"""ThemedText — Theme-aware text component.

Re-implements ClaudeCode-main/src/components/design-system/ThemedText.tsx
"""

from __future__ import annotations

from typing import Literal

from textual.widgets import Static

from py_claw.ui.theme import get_theme

TextVariant = Literal["normal", "muted", "dim", "error", "success", "warning", "info"]


class ThemedText(Static):
    """A text component with theme-aware styling.

    Supports different text variants for semantic coloring.
    """

    def __init__(
        self,
        text: str,
        variant: TextVariant = "normal",
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._variant = variant
        super().__init__(text, id=id, classes=classes)

    def on_mount(self) -> None:
        """Apply theme-aware styling based on variant."""
        theme = get_theme()
        colors = theme.colors

        color_map: dict[TextVariant, str] = {
            "normal": colors.get("text", "#ffffff"),
            "muted": colors.get("text_muted", "#888888"),
            "dim": colors.get("text_dim", "#555555"),
            "error": colors.get("error", "#ef4444"),
            "success": colors.get("success", "#22c55e"),
            "warning": colors.get("warning", "#f59e0b"),
            "info": colors.get("info", "#06b6d4"),
        }

        self.styles.color = color_map.get(self._variant, color_map["normal"])
