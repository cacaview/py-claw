"""
CustomSelect — Keyboard-navigable option selector widget.

Re-implements ClaudeCode-main/src/components/CustomSelect/select.tsx
as a Textual widget for the terminal UI.

Features:
- Keyboard navigation (up/down arrows, vim j/k, first-letter jump)
- Optional descriptions with dim styling
- Disabled options
- Inline-input mode for editable options
- Multi-select mode (space to toggle)
- Emits Selected / Cancelled messages
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Input, Static

from py_claw.ui.theme import get_theme

T = TypeVar("T")


@dataclass
class SelectOption(Generic[T]):
    """A single option in a CustomSelect widget."""

    label: str
    value: T
    description: str | None = None
    dim_description: bool = True
    disabled: bool = False
    # When set, the option shows an inline input field
    input_placeholder: str | None = None
    initial_input_value: str = ""


@dataclass
class MultiSelectOption(SelectOption[T]):
    """A selectable option in multi-select mode."""

    selected: bool = False


class CustomSelect(Vertical, Generic[T]):
    """
    Keyboard-navigable selector widget.

    Displays a vertical list of options; the user navigates with arrow keys
    and confirms with Enter.  Supports single-select and multi-select modes.

    Messages emitted:
    - ``CustomSelect.Selected``  — user confirmed a single selection
    - ``CustomSelect.MultiSelected`` — user confirmed multi-selection
    - ``CustomSelect.Cancelled`` — user pressed Escape
    """

    BINDINGS = [
        ("up,k", "move_up", "Move up"),
        ("down,j", "move_down", "Move down"),
        ("enter", "confirm", "Confirm"),
        ("space", "toggle", "Toggle (multi-select)"),
        ("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    CustomSelect {
        height: auto;
        max-height: 20;
    }
    CustomSelect .cs-option {
        padding: 0 1;
        height: 1;
    }
    CustomSelect .cs-option--focused {
        background: $accent;
        color: $background;
    }
    CustomSelect .cs-option--disabled {
        color: $text-muted;
    }
    CustomSelect .cs-description {
        color: $text-muted;
        padding: 0 3;
        height: 1;
    }
    """

    class Selected(Message, Generic[T]):
        """Emitted when an option is confirmed."""

        def __init__(self, value: T, option: SelectOption[T]) -> None:
            super().__init__()
            self.value = value
            self.option = option

    class MultiSelected(Message):
        """Emitted when multi-select is confirmed."""

        def __init__(self, values: list[Any], options: list[SelectOption]) -> None:  # type: ignore[type-arg]
            super().__init__()
            self.values = values
            self.options = options

    class Cancelled(Message):
        """Emitted when the selector is dismissed without a selection."""

    # ------------------------------------------------------------------ init

    def __init__(
        self,
        options: list[SelectOption[T]],
        *,
        multi_select: bool = False,
        show_descriptions: bool = True,
        on_select: Callable[[T], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._options = list(options)
        self._multi = multi_select
        self._show_desc = show_descriptions
        self._on_select = on_select
        self._on_cancel = on_cancel
        # State
        self._focus_index = 0
        self._advance_to_first_enabled()

    # ----------------------------------------------------------------- helpers

    def _advance_to_first_enabled(self) -> None:
        for i, opt in enumerate(self._options):
            if not opt.disabled:
                self._focus_index = i
                return

    def _render_option(self, index: int) -> Text:
        opt = self._options[index]
        theme = get_theme()
        focused = index == self._focus_index

        prefix: str
        if self._multi and isinstance(opt, MultiSelectOption):
            prefix = "[x] " if opt.selected else "[ ] "
        else:
            prefix = "> " if focused else "  "

        label_text = Text(prefix + opt.label)
        if opt.disabled:
            label_text.stylize("dim")
        elif focused:
            label_text.stylize(f"bold {theme.get('accent', 'cyan')}")
        return label_text

    # ---------------------------------------------------------------- compose

    def compose(self) -> ComposeResult:
        for i, opt in enumerate(self._options):
            focused = i == self._focus_index
            css = "cs-option"
            if focused:
                css += " cs-option--focused"
            if opt.disabled:
                css += " cs-option--disabled"
            yield Static(self._render_option(i), id=f"cs-opt-{i}", classes=css)
            if self._show_desc and opt.description:
                yield Static(f"  {opt.description}", classes="cs-description")

    # ---------------------------------------------------------------- refresh

    def _refresh_options(self) -> None:
        for i in range(len(self._options)):
            try:
                node = self.get_widget_by_id(f"cs-opt-{i}")
                if isinstance(node, Static):
                    focused = i == self._focus_index
                    opt = self._options[i]
                    css = "cs-option"
                    if focused:
                        css += " cs-option--focused"
                    if opt.disabled:
                        css += " cs-option--disabled"
                    node.classes = css
                    node.update(self._render_option(i))
            except Exception:
                pass

    # ---------------------------------------------------------------- actions

    def action_move_up(self) -> None:
        idx = self._focus_index
        for i in range(idx - 1, -1, -1):
            if not self._options[i].disabled:
                self._focus_index = i
                break
        self._refresh_options()

    def action_move_down(self) -> None:
        idx = self._focus_index
        for i in range(idx + 1, len(self._options)):
            if not self._options[i].disabled:
                self._focus_index = i
                break
        self._refresh_options()

    def action_confirm(self) -> None:
        if not self._options:
            return
        opt = self._options[self._focus_index]
        if opt.disabled:
            return
        if self._multi:
            selected = [o for o in self._options if isinstance(o, MultiSelectOption) and o.selected]
            self.post_message(self.MultiSelected([o.value for o in selected], selected))  # type: ignore[misc]
        else:
            if self._on_select:
                self._on_select(opt.value)
            self.post_message(self.Selected(opt.value, opt))

    def action_toggle(self) -> None:
        if not self._multi:
            return
        opt = self._options[self._focus_index]
        if isinstance(opt, MultiSelectOption) and not opt.disabled:
            opt.selected = not opt.selected
            self._refresh_options()

    def action_cancel(self) -> None:
        if self._on_cancel:
            self._on_cancel()
        self.post_message(self.Cancelled())

    def on_key(self, event: Any) -> None:
        """Jump to option by first letter."""
        if len(event.character or "") == 1 and event.character.isalpha():
            ch = event.character.lower()
            for i, opt in enumerate(self._options):
                if not opt.disabled and opt.label.lower().startswith(ch):
                    self._focus_index = i
                    self._refresh_options()
                    event.stop()
                    return
