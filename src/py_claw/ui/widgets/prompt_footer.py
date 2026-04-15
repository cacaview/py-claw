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
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static

from py_claw.services.keybindings import get_shortcut_display
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
    PromptFooter #pf-pills-row {
        height: 1;
        padding: 0 1;
    }
    PromptFooter #pf-suggestion-list {
        height: auto;
        max-height: 10;
        padding: 0 1;
    }
    PromptFooter #pf-suggestion-list Vertical {
        height: auto;
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
    selected_index: reactive[int] = reactive(-1)
    # Status pills
    bridge_label: reactive[str] = reactive("")
    bridge_color: reactive[str] = reactive("")
    agent_count: reactive[int] = reactive(0)
    task_count: reactive[int] = reactive(0)
    team_count: reactive[int] = reactive(0)

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
        self._viewport_size = 8

    # ── compose ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static(self._mode_indicator_text(), id="pf-mode-indicator"),
            Static(self._hint_text(), id="pf-hint"),
            Static(self._pills_row(), id="pf-pills-row"),
            id="pf-top-row",
        )
        with ScrollableContainer(id="pf-suggestion-list"):
            yield Vertical(id="pf-suggestion-vertical")
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

        t = Text(f"{status_icon} ", style=Style(color=text_muted))
        if symbol:
            t.append(f"{symbol}{label}", style=Style(color=color))
        elif label:
            t.append(f" {label}", style=Style(color=color))
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
            cycle_key = get_shortcut_display("cycle-mode") or "shift+tab"
            hints: dict[str, str] = {
                "plan": f"[{dim}]{cycle_key}: cycle mode[/{dim}]",
                "auto": f"[{dim}]{cycle_key}: cycle mode[/{dim}]",
                "bypass": f"[{dim}]{cycle_key}: cycle mode[/{dim}]",
            }
            return hints.get(self.mode, "")

        return ""

    # ── pills row ─────────────────────────────────────────────────────────

    def _pills_row(self) -> Text:
        """Build the status pills row."""
        theme = get_theme()
        dim = theme.colors.get("text_dim", "#555555")

        parts: list[Text] = []

        if self.bridge_label:
            color_map = {"success": "green", "warning": "yellow", "error": "red"}
            color = color_map.get(self.bridge_color, "dim")
            parts.append(Text(f" [bridge:{self.bridge_label}] ", style=color))

        if self.agent_count > 0:
            parts.append(Text(f" [agents:{self.agent_count}] ", style="cyan"))

        if self.task_count > 0:
            parts.append(Text(f" [tasks:{self.task_count}] ", style="yellow"))

        if self.team_count > 0:
            parts.append(Text(f" [team:{self.team_count}] ", style="magenta"))

        if not parts:
            return Text("")

        result = Text("")
        for part in parts:
            result.append(part)
        return result

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

    def watch_selected_index(self, _: int) -> None:
        self._refresh()

    def watch_help_open(self, open: bool) -> None:
        self._refresh()

    def watch_bridge_label(self, _: str) -> None:
        self._refresh()

    def watch_agent_count(self, _: int) -> None:
        self._refresh()

    def watch_task_count(self, _: int) -> None:
        self._refresh()

    def watch_team_count(self, _: int) -> None:
        self._refresh()

    def _refresh(self) -> None:
        """Refresh all sub-widgets."""
        try:
            mode_widget = self.query_one("#pf-mode-indicator", Static)
            hint_widget = self.query_one("#pf-hint", Static)
            pills_widget = self.query_one("#pf-pills-row", Static)
            mode_widget.update(self._mode_indicator_text())
            hint_widget.update(self._hint_text())
            pills_widget.update(self._pills_row())

            sug_scroll = self.query_one("#pf-suggestion-list", ScrollableContainer)
            sug_vert = self.query_one("#pf-suggestion-vertical", Vertical)

            if not self.has_suggestions:
                for child in list(sug_vert.children):
                    child.remove()
                sug_scroll.display = False
            else:
                for child in list(sug_vert.children):
                    child.remove()

                theme = get_theme()
                dim = theme.colors.get("text_dim", "#555555")
                accent = "yellow"

                total = len(self._suggestion_items)
                sel = self.selected_index
                if sel < 0:
                    sel = 0

                viewport = min(self._viewport_size, total)
                start = 0
                if total > viewport:
                    start = max(0, sel - (viewport // 2))
                    start = min(start, total - viewport)
                end = min(total, start + viewport)

                if start > 0:
                    sug_vert.mount(Static(f"[{dim}]↑ {start} more[/]"))

                for i in range(start, end):
                    item = self._suggestion_items[i]
                    is_selected = i == self.selected_index
                    prefix = "▶" if is_selected else " "
                    if hasattr(item, "display_text"):
                        display = item.display_text.strip()
                        desc = getattr(item, "description", "") or ""
                        tag = getattr(item, "tag", "") or ""
                        metadata = getattr(item, "metadata", None)
                        arg_hint = ""
                        if isinstance(metadata, dict):
                            arg_hint = str(metadata.get("argumentHint") or "")
                        sug_type = getattr(item, "type", None)
                        type_tag = tag if tag else (sug_type.value if sug_type else "")
                    else:
                        display = str(item)
                        desc = ""
                        type_tag = ""
                        arg_hint = ""

                    if is_selected:
                        parts = [f"[{accent}]{prefix} {display}[/]"]
                        if arg_hint:
                            parts.append(f"[dim]{arg_hint}[/]")
                        if desc:
                            parts.append(f"[dim]— {desc}[/]")
                        if type_tag:
                            parts.append(f"[{dim}][{type_tag}][/]")
                        line = " ".join(parts)
                    else:
                        line = f"[{dim}]{prefix} {display}[/]"
                        if arg_hint:
                            line += f" [{dim}]{arg_hint}[/]"
                    sug_vert.mount(Static(line))

                if end < total:
                    sug_vert.mount(Static(f"[{dim}]↓ {total - end} more[/]"))

                nav_hint = f"[{dim}]↑↓ navigate · PageUp/Down page · Tab accept[/{dim}]"
                sug_vert.mount(Static(nav_hint))
                sug_scroll.display = True
                sug_scroll.scroll_home(animate=False)

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
        self.selected_index = selected_index
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

    # ── status pills ───────────────────────────────────────────────────────

    def set_bridge_status(self, label: str, color: str) -> None:
        """Set bridge status pill label and color.

        Args:
            label: Status label (e.g. "Remote Control active").
            color: Color name ("success", "warning", "error").
        """
        self.bridge_label = label
        self.bridge_color = color

    def set_agent_count(self, count: int) -> None:
        """Set the number of active agents."""
        self.agent_count = count

    def set_task_count(self, count: int) -> None:
        """Set the number of running tasks."""
        self.task_count = count

    def set_team_count(self, count: int) -> None:
        """Set the number of team members."""
        self.team_count = count
