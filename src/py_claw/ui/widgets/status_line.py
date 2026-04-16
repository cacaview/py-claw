"""StatusLine — Status line component.

Re-implements ClaudeCode-main/src/components/design-system/StatusLine.tsx
"""

from __future__ import annotations

from textual.widgets import Static

from py_claw.services.keybindings import get_status_shortcuts_hint
from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.themed_text import ThemedText


class StatusLine(Static):
    """A status line showing connection state, model info, and shortcuts.

    Displays:
    - Connection status indicator
    - Current model name
    - Keyboard shortcuts hint
    - Token usage (optional)
    """

    DEFAULT_CSS = """
    StatusLine {
        height: 1;
    }
    """

    def __init__(
        self,
        status: str = "idle",  # "idle" | "running" | "thinking" | "error"
        model: str | None = None,
        shortcuts: str | None = None,
        tokens: str | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._status = status
        self._model = model
        self._shortcuts = shortcuts or get_status_shortcuts_hint()
        self._tokens = tokens
        super().__init__(id=id, classes=classes)
        self._update_content()

    def _update_content(self) -> None:
        """Update the Static widget content using markup."""
        theme = get_theme()

        status_icons = {
            "idle": "○",
            "running": "◐",
            "thinking": "◑",
            "error": "✗",
        }
        status_icon = status_icons.get(self._status, "○")
        status_color = theme.colors.get("text_muted", "#888888")
        text_muted = theme.colors.get("text_muted", "#888888")
        text_dim = theme.colors.get("text_dim", "#555555")

        parts = [f"[{status_color}]{status_icon}[/{status_color}]"]

        if self._model:
            parts.append(f" [{text_muted}]{self._model}[/]")

        if self._tokens:
            parts.append(f" [{text_muted}]·[/] [{text_muted}]Tokens: {self._tokens}[/]")

        if self._shortcuts:
            parts.append(f" [{text_dim}]·[/] [{text_dim}]{self._shortcuts}[/]")

        self.update("".join(parts))

    def set_status(self, status: str) -> None:
        """Update the status."""
        self._status = status
        self._update_content()

    def set_model(self, model: str) -> None:
        """Update the model name."""
        self._model = model
        self._update_content()

    def set_tokens(self, tokens: str) -> None:
        """Update the token count."""
        self._tokens = tokens
        self._update_content()
