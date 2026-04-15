"""
HelpMenuDialog — Help menu dialog showing slash commands and shortcuts.

Re-implements ClaudeCode-main/src/components/PromptInput/PromptInputHelpMenu.tsx
as a Textual dialog.

Shows:
- All available slash commands with descriptions and argument hints
- Global keyboard shortcuts
- Dismissable via Escape or ?
"""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.dialog import Dialog


class HelpMenuDialog(Dialog):
    """Help menu dialog showing all slash commands and shortcuts.

    Displayed when the user presses `?` in the prompt.
    Shows all commands with descriptions, shortcuts, and usage hints.
    """

    def __init__(
        self,
        commands: list[dict] | None = None,
        shortcuts: dict[str, str] | None = None,
        on_close: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._commands = list(commands or [])
        self._shortcuts = dict(shortcuts or _DEFAULT_SHORTCUTS)
        self._on_close = on_close
        super().__init__(
            title="Help — Slash Commands & Shortcuts",
            body="",
            show_confirm_deny=False,
            cancel_enabled=True,
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        theme = get_theme()
        text = theme.colors.get("text", "#ffffff")
        dim = theme.colors.get("text_dim", "#555555")
        accent = "yellow"

        yield Static("Slash Commands", id="help-section-title")

        # Command list
        with ScrollableContainer(id="help-commands"):
            with Vertical():
                for cmd in self._commands:
                    name = cmd.get("name", "")
                    desc = cmd.get("description", "")
                    arg_hint = cmd.get("argumentHint", "")
                    if not name or cmd.get("isHidden", False):
                        continue
                    cmd_line = f"[{accent}]/{name}[/] "
                    if arg_hint:
                        cmd_line += f"[dim]{arg_hint}[/]  "
                    if desc:
                        cmd_line += f"[dim]— {desc}[/]"
                    yield Static(cmd_line)

        yield Static("", id="help-separator")
        yield Static("Keyboard Shortcuts", id="help-section-title-2")

        with Vertical(id="help-shortcuts"):
            for action, desc in self._shortcuts.items():
                yield Static(f"[dim]{action}[/dim]  {desc}")

    def action_cancel(self) -> None:
        """Handle Escape — close the help dialog."""
        if self._on_close:
            self._on_close()


# Default shortcuts displayed in the help menu
_DEFAULT_SHORTCUTS: dict[str, str] = {
    "enter": "Submit prompt",
    "esc": "Interrupt / cancel / close",
    "↑ / ↓": "Navigate history / suggestions",
    "tab": "Accept suggestion / complete",
    "→": "Accept inline ghost text",
    "?": "Toggle this help menu",
    "ctrl+g": "New session",
    "ctrl+l": "Clear log",
    "ctrl+c": "Quit",
}
