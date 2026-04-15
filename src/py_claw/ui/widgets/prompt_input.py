"""
PromptInput — Enhanced terminal prompt input widget.

Re-implements the core user-facing portion of
ClaudeCode-main/src/components/PromptInput/PromptInput.tsx
as a Textual widget.

Features:
- Mode indicator (normal / plan / vim)
- Input history navigation (up/down arrows)
- Multi-line input via Shift+Enter (lines joined with \n)
- Paste-content notifications (via PasteAdded message)
- Submit on Enter; interrupt on Escape
- Suggestion hint line below input
"""
from __future__ import annotations

from enum import auto, Enum
from typing import TYPE_CHECKING, Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.suggester import Suggester
from textual.widgets import Input, Static

from py_claw.ui.theme import get_theme

if TYPE_CHECKING:
    from py_claw.ui.typeahead import Suggestion, SuggestionEngine


# ──────────────── CommandSuggester for inline ghost text ─────────────────────


class CommandSuggester(Suggester):
    """Textual Suggester that provides slash-command completions as ghost text.

    Uses ``SuggestionEngine`` to determine the best suffix for inline ghost text
    display. When the user types a partial slash command (e.g. "/he"), this
    returns the full completed command (e.g. "/help ") so that Textual's Input
    widget displays the remaining characters as dimmed ghost text after the cursor.
    """

    def __init__(self, engine: "SuggestionEngine", *, case_sensitive: bool = False) -> None:
        super().__init__(use_cache=True, case_sensitive=case_sensitive)
        self._engine = engine

    async def get_suggestion(self, value: str) -> str | None:
        """Return the best completion suffix for the given input value."""
        if not value:
            return None
        # cursor_offset = len(value) means cursor is at end — full ghost text
        suffix = self._engine.get_best_suffix(value, len(value))
        if suffix:
            # Return full completed value for inline display
            return value + suffix
        return None


class PromptMode(str, Enum):
    """Active prompt / permission mode."""

    NORMAL = "normal"
    PLAN = "plan"
    AUTO = "auto"
    BYPASS_PERMISSIONS = "bypass_permissions"


class VimMode(str, Enum):
    """Vim editing mode indicator."""

    INSERT = "INSERT"
    NORMAL = "NORMAL"
    VISUAL = "VISUAL"


# ────────────────────────── messages ──────────────────────────────────────────


class PromptInput(Vertical):
    """
    Enhanced prompt input widget for the REPL screen.

    Wraps a Textual ``Input`` with:
    - A one-line mode/vim indicator row above the input
    - A suggestion hint line below the input
    - History ring navigation (up / down when buffer is empty or cursor at edges)
    - ``PromptInput.Submitted`` / ``PromptInput.Interrupted`` messages

    Usage::

        yield PromptInput(
            model="claude-opus-4-6",
            prompt_mode=PromptMode.NORMAL,
            on_submit=handle_submit,
            on_interrupt=handle_interrupt,
        )
    """

    DEFAULT_CSS = """
    PromptInput {
        height: auto;
    }
    PromptInput #pi-mode-bar {
        height: 1;
        padding: 0 1;
    }
    PromptInput #pi-input {
        height: 1;
        border: none;
        padding: 0 1;
    }
    PromptInput #pi-hint {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    PromptInput #pi-suggestion-list {
        height: auto;
        padding: 0 1;
        color: $text;
    }
    /* Inline ghost text for slash command completion */
    PromptInput #pi-input .input--suggestion {
        color: $text-muted;
    }
    """

    # ── reactive state ──────────────────────────────────────────────────────
    prompt_mode: reactive[PromptMode] = reactive(PromptMode.NORMAL)
    vim_mode: reactive[VimMode | None] = reactive(None)
    hint: reactive[str] = reactive("")
    suggestion_items: reactive[list["SuggestionItem"]] = reactive([])
    selected_index: reactive[int] = reactive(-1)
    pasted_content_label: reactive[str] = reactive("")

    # ── messages ────────────────────────────────────────────────────────────

    class Submitted(Message):
        """Emitted when the user presses Enter to submit."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class Changed(Message):
        """Emitted when the input value changes."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class Interrupted(Message):
        """Emitted when the user presses Escape."""

    class PasteAdded(Message):
        """Emitted when a paste blob is attached to the prompt."""

        def __init__(self, content_id: str, label: str) -> None:
            super().__init__()
            self.content_id = content_id
            self.label = label

    class HelpToggled(Message):
        """Emitted when the user presses ? to toggle help."""

    class VimModeChanged(Message):
        """Emitted when vim editing mode changes."""

        def __init__(self, mode: VimMode) -> None:
            super().__init__()
            self.mode = mode

    # ── init ────────────────────────────────────────────────────────────────

    def __init__(
        self,
        *,
        model: str | None = None,
        prompt_mode: PromptMode = PromptMode.NORMAL,
        vim_mode: VimMode | None = None,
        hint: str = "",
        placeholder: str = "Ask claude... (Escape to cancel)",
        on_submit: Callable[[str], None] | None = None,
        on_interrupt: Callable[[], None] | None = None,
        on_change: Callable[[str], None] | None = None,
        history: list[str] | None = None,
        suggestion_engine: "SuggestionEngine | None" = None,
        pasted_content_label: str = "",
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._model = model
        self.prompt_mode = prompt_mode
        self.vim_mode = vim_mode
        self.hint = hint
        self.pasted_content_label = pasted_content_label
        self._placeholder = placeholder
        self._on_submit = on_submit
        self._on_interrupt = on_interrupt
        self._on_change = on_change
        # History ring — most-recent entries at the end
        self._history: list[str] = list(history or [])
        self._history_pos: int = -1  # -1 = live buffer
        # Unified suggestion engine (commands + paths + shell history)
        self._engine = suggestion_engine

    # ── compose ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        suggester = CommandSuggester(self._engine) if self._engine else None
        yield Static(self._mode_bar_text(), id="pi-mode-bar")
        yield Input(placeholder=self._placeholder, id="pi-input", suggester=suggester)
        yield Static(self.hint, id="pi-hint")
        yield Static("", id="pi-suggestion-list")

    # ── mode bar ────────────────────────────────────────────────────────────

    def _mode_bar_text(self) -> Text:
        theme = get_theme()
        parts: list[tuple[str, str]] = []

        if self._model:
            parts.append((f"[{self._model}]", "dim"))

        text_muted = theme.colors.get("text_muted", "#888888")
        mode_colors: dict[PromptMode, str] = {
            PromptMode.NORMAL: text_muted,
            PromptMode.PLAN: "yellow",
            PromptMode.AUTO: "cyan",
            PromptMode.BYPASS_PERMISSIONS: "red",
        }
        mode_labels: dict[PromptMode, str] = {
            PromptMode.NORMAL: "",
            PromptMode.PLAN: " [plan] ",
            PromptMode.AUTO: " [auto] ",
            PromptMode.BYPASS_PERMISSIONS: " [bypass] ",
        }
        label = mode_labels.get(self.prompt_mode, "")
        if label:
            parts.append((label, mode_colors.get(self.prompt_mode, "")))

        if self.vim_mode:
            parts.append((f" {self.vim_mode.value} ", "bold"))

        # Pasted content indicator
        if self.pasted_content_label:
            parts.append((f" [paste: {self.pasted_content_label}] ", "yellow"))

        t = Text()
        for text, style in parts:
            t.append(text, style=style or "")
        return t

    # ── reactive watchers ───────────────────────────────────────────────────

    def watch_suggestion_items(self, items: list[object]) -> None:
        """Update the suggestion list display when items change."""
        self._update_suggestion_list()

    def watch_selected_index(self, index: int) -> None:
        """Re-render suggestion list when selection changes."""
        self._update_suggestion_list()

    def _update_suggestion_list(self) -> None:
        """Build and display the suggestion list."""
        try:
            list_widget = self.get_widget_by_id("pi-suggestion-list")
            if not isinstance(list_widget, Static):
                return
            if not self.suggestion_items:
                list_widget.update("")
                return

            theme = get_theme()
            dim = theme.colors.get("text_dim", "#555555")
            muted = theme.colors.get("text_muted", "#888888")
            accent = "yellow"

            lines: list[str] = []
            for i, item in enumerate(self.suggestion_items):
                is_selected = i == self.selected_index
                prefix = "▶" if is_selected else " "

                # Unified Suggestion (ui/typeahead.py)
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

                if is_selected:
                    parts = [f"[{accent}]{prefix} {display}[/]"]
                    if arg_hint:
                        parts.append(f"[dim]{arg_hint}[/]")
                    if desc:
                        parts.append(f"[dim]— {desc}[/]")
                    if type_tag:
                        parts.append(f"[{dim}][{type_tag}][/]")
                    lines.append(" ".join(parts))
                else:
                    line = f"[{dim}]{prefix} {display}[/]"
                    if arg_hint:
                        line += f" [{dim}]{arg_hint}[/]"
                    lines.append(line)

            list_widget.update("\n".join(lines))
        except Exception:
            pass

    def watch_prompt_mode(self, _: PromptMode) -> None:
        try:
            bar = self.get_widget_by_id("pi-mode-bar")
            if isinstance(bar, Static):
                bar.update(self._mode_bar_text())
        except Exception:
            pass

    def watch_vim_mode(self, _: VimMode | None) -> None:
        self.watch_prompt_mode(self.prompt_mode)

    def watch_hint(self, new_hint: str) -> None:
        try:
            hint_widget = self.get_widget_by_id("pi-hint")
            if isinstance(hint_widget, Static):
                hint_widget.update(new_hint)
        except Exception:
            pass

    def watch_pasted_content_label(self, label: str) -> None:
        """Re-render mode bar when pasted content label changes."""
        self.watch_prompt_mode(self.prompt_mode)

    def set_pasted_content(self, content_id: str, label: str) -> None:
        """Set pasted content notice."""
        self.pasted_content_label = label

    def clear_pasted_content(self) -> None:
        """Clear pasted content notice."""
        self.pasted_content_label = ""

    # ── public API ──────────────────────────────────────────────────────────

    def focus_input(self) -> None:
        """Move keyboard focus to the inner Input widget."""
        try:
            self.get_widget_by_id("pi-input").focus()
        except Exception:
            pass

    def clear(self) -> None:
        """Clear the input field and reset history position."""
        try:
            inp = self.get_widget_by_id("pi-input")
            if isinstance(inp, Input):
                inp.value = ""
        except Exception:
            pass
        self._history_pos = -1

    def set_value(self, value: str) -> None:
        """Programmatically set the input text."""
        try:
            inp = self.get_widget_by_id("pi-input")
            if isinstance(inp, Input):
                inp.value = value
        except Exception:
            pass

    def get_value(self) -> str:
        """Return the current input value."""
        try:
            inp = self.get_widget_by_id("pi-input")
            if isinstance(inp, Input):
                return inp.value
        except Exception:
            pass
        return ""

    def add_to_history(self, value: str) -> None:
        """Append a submitted entry to the history ring."""
        if value and (not self._history or self._history[-1] != value):
            self._history.append(value)
        self._history_pos = -1

    def set_suggestion_items(self, items: list[object]) -> None:
        """Set the available suggestion items (from SuggestionEngine)."""
        self.suggestion_items = items  # type: ignore[assignment]
        self.selected_index = -1

    def update_suggestions(self, text: str, cursor_offset: int) -> None:
        """Update suggestion list from the engine based on current input."""
        if not self._engine:
            return
        items = self._engine.get_suggestions(text, cursor_offset)
        self.suggestion_items = items  # type: ignore[assignment]
        self.selected_index = -1

    def apply_selected_suggestion(self) -> bool:
        """Apply the currently selected suggestion to the input. Returns True if applied."""
        if self.selected_index < 0 or self.selected_index >= len(self.suggestion_items):
            return False
        item = self.suggestion_items[self.selected_index]
        from py_claw.ui.typeahead import Suggestion, SuggestionType

        if isinstance(item, Suggestion):
            if item.type == SuggestionType.COMMAND:
                new_value = f"/{item.id} "
            elif item.type == SuggestionType.PATH:
                new_value = item.display_text
            elif item.type == SuggestionType.SHELL_HISTORY:
                new_value = item.display_text
            else:
                new_value = item.display_text
        else:
            # Fallback for old SuggestionItem
            if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
                cmd_name = str(item.metadata.get("name") or item.display_text.strip().lstrip("/").rstrip())
            else:
                cmd_name = item.display_text.strip().lstrip("/").rstrip()
            new_value = f"/{cmd_name} "

        self.set_value(new_value)
        self.suggestion_items = []  # type: ignore[assignment]
        self.selected_index = -1
        return True

    def accept_best_suggestion(self) -> bool:
        """Accept the first/best suggestion without explicit selection. Returns True if applied."""
        if not self.suggestion_items:
            return False
        item = self.suggestion_items[0]
        from py_claw.ui.typeahead import Suggestion, SuggestionType

        if isinstance(item, Suggestion):
            if item.type == SuggestionType.COMMAND:
                new_value = f"/{item.id} "
            elif item.type == SuggestionType.PATH:
                new_value = item.display_text
            elif item.type == SuggestionType.SHELL_HISTORY:
                new_value = item.display_text
            else:
                new_value = item.display_text
        else:
            if hasattr(item, 'metadata') and isinstance(item.metadata, dict):
                cmd_name = str(item.metadata.get("name") or item.display_text.strip().lstrip("/").rstrip())
            else:
                cmd_name = item.display_text.strip().lstrip("/").rstrip()
            new_value = f"/{cmd_name} "

        self.set_value(new_value)
        self.suggestion_items = []  # type: ignore[assignment]
        self.selected_index = -1
        return True

    # ── event handlers ──────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input updates from the inner Input widget."""
        if event.input.id != "pi-input":
            return
        value = event.value
        # ? alone toggles help
        if value == "?":
            self.clear()
            self.post_message(self.HelpToggled())
            return
        if self._on_change:
            self._on_change(value)
        self.post_message(self.Changed(value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter keypress from the inner Input widget."""
        event.stop()
        value = event.value.strip()
        if not value:
            return
        self.add_to_history(value)
        if self._on_submit:
            self._on_submit(value)
        self.post_message(self.Submitted(value))
        self.clear()

    def on_key(self, event: object) -> None:  # type: ignore[override]
        """Handle history navigation, vim mode, Escape, Tab, and arrow keys."""
        from textual.events import Key
        if not isinstance(event, Key):
            return
        try:
            inp = self.get_widget_by_id("pi-input")
        except Exception:
            return
        if not isinstance(inp, Input):
            return

        # ── Vim mode handling ─────────────────────────────────────────────
        if self.vim_mode == VimMode.NORMAL:
            # In NORMAL mode: i=INSERT, a=APPEND (INSERT after cursor), v=VISUAL
            char = getattr(event, "character", None) or ""
            if char == "i":
                event.stop()
                self.vim_mode = VimMode.INSERT
                self.post_message(self.VimModeChanged(VimMode.INSERT))
                return
            if char == "a":
                event.stop()
                self.vim_mode = VimMode.INSERT
                # Move cursor one position forward (append mode)
                if inp.cursor_position < len(inp.value):
                    inp.cursor_position += 1
                self.post_message(self.VimModeChanged(VimMode.INSERT))
                return
            if char == "v":
                event.stop()
                self.vim_mode = VimMode.VISUAL
                self.post_message(self.VimModeChanged(VimMode.VISUAL))
                return
            # In NORMAL mode, arrow keys don't navigate history
            # Let them pass through for cursor movement
            return

        if self.vim_mode == VimMode.VISUAL:
            # esc in VISUAL → back to NORMAL
            if event.key == "escape":
                event.stop()
                self.vim_mode = VimMode.NORMAL
                self.post_message(self.VimModeChanged(VimMode.NORMAL))
                return
            return

        # ── INSERT mode ────────────────────────────────────────────────────

        if event.key == "escape":
            event.stop()
            if self.suggestion_items:
                self.suggestion_items = []  # type: ignore[assignment]
                self.selected_index = -1
                return
            # esc in INSERT → switch to NORMAL vim mode if vim_mode is enabled
            if self.vim_mode == VimMode.INSERT:
                self.vim_mode = VimMode.NORMAL
                self.post_message(self.VimModeChanged(VimMode.NORMAL))
                return
            if self._on_interrupt:
                self._on_interrupt()
            self.post_message(self.Interrupted())
            return

        # Tab: accept ghost text (from suggester) or selected suggestion
        if event.key == "tab":
            event.stop()
            # First: check if Input has ghost text from suggester
            if hasattr(inp, "_suggestion") and inp._suggestion:
                # Accept inline ghost text (mirrors Input.action_cursor_right logic)
                inp.value = inp._suggestion
                inp.cursor_position = len(inp.value)
                # Clear our suggestion list to stay in sync
                self.suggestion_items = []  # type: ignore[assignment]
                self.selected_index = -1
            elif self.suggestion_items:
                # Fall back to suggestion list
                if self.selected_index < 0:
                    self.accept_best_suggestion()
                else:
                    self.apply_selected_suggestion()
            return

        if event.key == "up":
            if not self._history:
                return
            if self._history_pos == -1:
                self._history_pos = len(self._history) - 1
            elif self._history_pos > 0:
                self._history_pos -= 1
            inp.value = self._history[self._history_pos]
            event.stop()

        elif event.key == "down":
            if self._history_pos == -1:
                return
            self._history_pos += 1
            if self._history_pos >= len(self._history):
                self._history_pos = -1
                inp.value = ""
            else:
                inp.value = self._history[self._history_pos]
            event.stop()
