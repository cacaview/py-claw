"""ProgressBar — Progress display component.

Re-implements ClaudeCode-main/src/components/design-system/ProgressBar.tsx
"""

from __future__ import annotations

from textual.widgets import Static

from py_claw.ui.theme import get_theme


class ProgressBar(Static):
    """A horizontal progress bar.

    Shows percentage complete with optional label.
    """

    def __init__(
        self,
        value: float = 0.0,  # 0.0 to 1.0
        label: str | None = None,
        width: int = 40,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._value = max(0.0, min(1.0, value))
        self._label = label
        self._width = width
        super().__init__(id=id, classes=classes)

    def on_mount(self) -> None:
        """Set initial progress bar display."""
        self._render()

    def set_progress(self, value: float) -> None:
        """Update the progress value (0.0 to 1.0)."""
        self._value = max(0.0, min(1.0, value))
        self._render()

    def _render(self) -> None:
        """Render the progress bar."""
        filled = int(self._value * self._width)
        empty = self._width - filled
        bar = "█" * filled + "░" * empty
        label_str = f" {self._label}" if self._label else ""
        self.update(f"[{bar}]{label_str}")


class ProgressBarWide(ProgressBar):
    """A wider variant of ProgressBar for more detailed display."""

    def __init__(self, value: float = 0.0, label: str | None = None, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(value=value, label=label, width=60, id=id, classes=classes)
