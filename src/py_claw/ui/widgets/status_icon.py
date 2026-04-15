"""StatusIcon — Status icon with semantic meaning.

Re-implements ClaudeCode-main/src/components/design-system/StatusIcon.tsx
"""

from __future__ import annotations

from enum import Enum

from textual.widgets import Static

from py_claw.ui.theme import get_theme


class StatusType(Enum):
    """Status icon types."""

    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"
    PENDING = "pending"
    SPINNER = "spinner"


# Box-drawing characters for status icons
_STATUS_CHARS: dict[StatusType, str] = {
    StatusType.SUCCESS: "✓",
    StatusType.WARNING: "⚠",
    StatusType.ERROR: "✗",
    StatusType.INFO: "ℹ",
    StatusType.PENDING: "○",
    StatusType.SPINNER: "◐",
}


class StatusIcon(Static):
    """A status icon with semantic coloring.

    Uses unicode symbols with theme-aware colors.
    """

    def __init__(
        self,
        status: StatusType = StatusType.INFO,
        label: str | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._status = status
        self._label = label
        super().__init__(id=id, classes=classes)

    def on_mount(self) -> None:
        """Apply status-aware styling."""
        theme = get_theme()
        colors = theme.colors

        color_map: dict[StatusType, str] = {
            StatusType.SUCCESS: colors.get("success", "#22c55e"),
            StatusType.WARNING: colors.get("warning", "#f59e0b"),
            StatusType.ERROR: colors.get("error", "#ef4444"),
            StatusType.INFO: colors.get("info", "#06b6d4"),
            StatusType.PENDING: colors.get("text_muted", "#888888"),
            StatusType.SPINNER: colors.get("primary", "#3b82f6"),
        }

        self.styles.color = color_map.get(self._status, color_map[StatusType.INFO])

        icon = _STATUS_CHARS.get(self._status, "?")
        label_str = f" {self._label}" if self._label else ""
        self.update(f"{icon}{label_str}")
