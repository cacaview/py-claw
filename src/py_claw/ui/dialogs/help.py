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

from typing import Any, Callable

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.dialog import Dialog


def _cmd_name(cmd: Any) -> str:
    return getattr(cmd, "name", "") or (cmd.get("name") if isinstance(cmd, dict) else "")


def _cmd_description(cmd: Any) -> str:
    return getattr(cmd, "description", "") or (cmd.get("description", "") if isinstance(cmd, dict) else "")


def _cmd_argument_hint(cmd: Any) -> str:
    return getattr(cmd, "argument_hint", "") or (cmd.get("argumentHint", "") if isinstance(cmd, dict) else "")


def _cmd_is_hidden(cmd: Any) -> bool:
    if hasattr(cmd, "is_hidden"):
        return cmd.is_hidden
    return bool(cmd.get("isHidden", False)) if isinstance(cmd, dict) else False


class HelpMenuDialog(Dialog):
    """Help menu dialog showing all slash commands and shortcuts.

    Displayed when the user presses `?` in the prompt.
    Shows all commands with descriptions, shortcuts, and usage hints.
    """

    def __init__(
        self,
        commands: list[Any] | None = None,
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
        dim = theme.colors.get("text_dim", "#555555")
        accent = "yellow"

        yield Static("Slash Commands", id="help-section-title")

        # Command list
        with ScrollableContainer(id="help-commands"):
            with Vertical():
                for cmd in self._commands:
                    name = _cmd_name(cmd)
                    desc = _cmd_description(cmd)
                    arg_hint = _cmd_argument_hint(cmd)
                    if not name or _cmd_is_hidden(cmd):
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
            for action, desc_text in self._shortcuts.items():
                yield Static(f"[dim]{action}[/dim]  {desc_text}")

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
