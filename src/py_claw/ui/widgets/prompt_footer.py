"""
PromptFooter — Dynamic footer for PromptInput.

Re-implements the dynamic footer portion of
ClaudeCode-main/src/components/PromptInput/PromptInputFooter.tsx
and ClaudeCode-main/src/components/PromptInput/PromptInputFooterLeftSide.tsx
as a Textual widget.

Shows:
- Mode indicator (plan/auto/bypass/normal) with color
- Contextual hints that change based on current state
- Suggestion list (replaces #pi-suggestion-list)
- Help menu toggle (via ?)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static

from py_claw.ui.theme import get_theme

if TYPE_CHECKING:
    from py_claw.ui.typeahead import Suggestion


# ────────────────────────── PromptFooter ──────────────────────────────────────


class PromptFooter(Static):
    """
    Dynamic footer widget for the REPL prompt area.

    Displays contextual information below the prompt input:
    - Mode indicator with permission context (plan/auto/bypass/normal)
    - Context-aware hint text (changes based on state)
    - Suggestion list (keyboard-navigable)
    - Help shortcut (? for help menu)

    This replaces the static `#pi-hint` and `#pi-suggestion-list` areas
    in PromptInput with a single cohesive footer zone.
    """

    DEFAULT_CSS = """
    PromptFooter {
        height: auto;
    }
    PromptFooter #pf-mode-indicator {
        height: 1;
        padding: 0 1;
    }
    PromptFooter #pf-hint {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    PromptFooter #pf-suggestion-list {
        height: auto;
        padding: 0 1;
    }
    PromptFooter #pf-help-row {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    # ── reactive state ──────────────────────────────────────────────────────
    mode: reactive[str] = reactive("normal")
    status: reactive[str] = reactive("idle")  # "idle" | "running" | "thinking" | "error"
    is_loading: reactive[bool] = reactive(False)
    has_suggestions: reactive[bool] = reactive(False)
    help_open: reactive[bool] = reactive(False)

    # ── messages ────────────────────────────────────────────────────────────

    class HelpToggled(Message):
        """Emitted when the user presses ? to toggle help."""

    # ── init ───────────────────────────────────────────────────────────────

    def __init__(
        self,
        shortcuts: str | None = None,
        on_help_toggle: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._shortcuts = shortcuts or "?: help"
        self._on_help_toggle = on_help_toggle
        self._suggestion_items: list[object] = []
        self._selected_index: int = -1

    # ── compose ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static(self._mode_indicator_text(), id="pf-mode-indicator"),
            Static(self._hint_text(), id="pf-hint"),
            id="pf-top-row",
        )
        yield Static("", id="pf-suggestion-list")
        yield Static(f"[dim]?[/dim] {self._shortcuts}", id="pf-help-row")

    # ── mode indicator ─────────────────────────────────────────────────────

    def _mode_indicator_text(self) -> Text:
        """Build the mode/permission indicator text."""
        theme = get_theme()
        text_muted = theme.colors.get("text_muted", "#888888")

        mode_colors: dict[str, str] = {
            "normal": text_muted,
            "plan": "yellow",
            "auto": "cyan",
            "bypass": "red",
        }
        mode_labels: dict[str, str] = {
            "normal": "",
            "plan": " [plan] ",
            "auto": " [auto] ",
            "bypass": " [bypass] ",
        }
        mode_symbols: dict[str, str] = {
            "normal": "",
            "plan": "◈",
            "auto": "◎",
            "bypass": "⚡",
        }

        color = mode_colors.get(self.mode, text_muted)
        label = mode_labels.get(self.mode, "")
        symbol = mode_symbols.get(self.mode, "")

        # Use Text() with style= param for color — avoids Rich markup parsing issues
        from rich.style import Style
        status_icons = {"idle": "○", "running": "◐", "thinking": "◑", "error": "✗"}
        status_icon = status_icons.get(self.status, "○")
        muted_hex = text_muted.lstrip("#")

        t = Text(f"{status_icon} ", style=Style(color=muted_hex))
        if symbol:
            sym_hex = color.lstrip("#")
            t.append(f"{symbol}{label}", style=Style(color=sym_hex))
        elif label:
            lbl_hex = color.lstrip("#")
            t.append(f" {label}", style=Style(color=lbl_hex))
        return t

    # ── hint text ──────────────────────────────────────────────────────────

    def _hint_text(self) -> str:
        """Build the contextual hint based on current state."""
        theme = get_theme()
        dim = theme.colors.get("text_dim", "#555555")
        accent = "yellow"

        if self.has_suggestions:
            return ""

        if self.is_loading:
            return f"[{dim}]esc: interrupt[/{dim}]"

        if self.mode != "normal":
            hints: dict[str, str] = {
                "plan": f"[{dim}]shift+tab: cycle mode[/{dim}]",
                "auto": f"[{dim}]shift+tab: cycle mode[/{dim}]",
                "bypass": f"[{dim}]shift+tab: cycle mode[/{dim}]",
            }
            return hints.get(self.mode, "")

        return ""

    # ── suggestion list ────────────────────────────────────────────────────

    def _suggestion_list_text(self) -> str:
        """Build the suggestion list display text."""
        theme = get_theme()
        dim = theme.colors.get("text_dim", "#555555")
        accent = "yellow"

        if not self._suggestion_items:
            return ""

        lines: list[str] = []
        for i, item in enumerate(self._suggestion_items):
            is_selected = i == self._selected_index
            prefix = "▶" if is_selected else " "
            item_dim = accent if is_selected else dim

            if hasattr(item, "display_text"):
                display = item.display_text.strip()
                desc = getattr(item, "description", "") or ""
                tag = getattr(item, "tag", "") or ""
                metadata = getattr(item, "metadata", None)
                arg_hint = ""
                if isinstance(metadata, dict):
                    arg_hint = str(metadata.get("argumentHint") or "")
            else:
                display = str(item)
                desc = ""
                tag = ""
                arg_hint = ""

            if is_selected:
                parts = [f"[{accent}]{prefix} {display}[/]"]
                if arg_hint:
                    parts.append(f"[dim]{arg_hint}[/]")
                if desc:
                    parts.append(f"[dim]— {desc}[/]")
                if tag:
                    parts.append(f"[{dim}][{tag}][/]")
                lines.append(" ".join(parts))
            else:
                line = f"[{dim}]{prefix} {display}[/]"
                if arg_hint:
                    line += f" [{dim}]{arg_hint}[/]"
                lines.append(line)

        nav_hint = f"[{dim}]↑↓ navigate · Tab accept[/{dim}]"
        lines.append(nav_hint)
        return "\n".join(lines)

    # ── reactive watchers ─────────────────────────────────────────────────

    def watch_mode(self, _: str) -> None:
        self._refresh()

    def watch_status(self, _: str) -> None:
        self._refresh()

    def watch_is_loading(self, _: bool) -> None:
        self._refresh()

    def watch_has_suggestions(self, has_sugs: bool) -> None:
        self._refresh()

    def watch_help_open(self, open: bool) -> None:
        self._refresh()

    def _refresh(self) -> None:
        """Refresh all sub-widgets."""
        try:
            # Top row: mode indicator + hint
            top = self.query_one("#pf-top-row", Horizontal)
            mode_widget = self.query_one("#pf-mode-indicator", Static)
            hint_widget = self.query_one("#pf-hint", Static)
            mode_widget.update(self._mode_indicator_text())
            hint_widget.update(self._hint_text())

            # Suggestion list
            sug_list = self.query_one("#pf-suggestion-list", Static)
            if self.has_suggestions:
                sug_list.update(self._suggestion_list_text())
            else:
                sug_list.update("")

            # Help row visibility
            help_row = self.query_one("#pf-help-row", Static)
            if self.help_open:
                help_row.update(f"[yellow]?[/yellow] close help")
            else:
                help_row.update(f"[dim]?[/dim] {self._shortcuts}")

        except Exception:
            pass

    # ── public API ─────────────────────────────────────────────────────────

    def set_mode(self, mode: str) -> None:
        """Set the current mode (normal/plan/auto/bypass)."""
        self.mode = mode

    def set_status(self, status: str) -> None:
        """Set the current status (idle/running/thinking/error)."""
        self.status = status

    def set_loading(self, loading: bool) -> None:
        """Set loading state."""
        self.is_loading = loading

    def set_suggestions(self, items: list[object], selected_index: int = -1) -> None:
        """Update suggestion items and selected index."""
        self._suggestion_items = items
        self._selected_index = selected_index
        self.has_suggestions = bool(items)
        self._refresh()

    def toggle_help(self) -> None:
        """Toggle help menu visibility."""
        self.help_open = not self.help_open
        self.post_message(self.HelpToggled())

    def close_help(self) -> None:
        """Close help menu."""
        if self.help_open:
            self.help_open = False
