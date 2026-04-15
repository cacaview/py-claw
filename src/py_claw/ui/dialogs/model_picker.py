"""
ModelPickerDialog — Model selection dialog.

Allows the user to select from available Claude models.
Triggered by Ctrl+M in the REPL.
"""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.widgets import Input, Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.list_item import ListItem
from py_claw.services.model import model as model_service


class ModelInfo:
    """Model information for display."""

    def __init__(self, id: str, name: str, description: str, series: str) -> None:
        self.id = id
        self.name = name
        self.description = description
        self.series = series  # opus, sonnet, haiku


# Available models for selection
_AVAILABLE_MODELS: list[ModelInfo] = [
    ModelInfo(
        id=model_service.SONNET_46,
        name="Sonnet 4.6",
        description="Best for coding, most capable Sonnet",
        series="sonnet",
    ),
    ModelInfo(
        id=model_service.OPUS_46,
        name="Opus 4.6",
        description="Most capable model for complex tasks",
        series="opus",
    ),
    ModelInfo(
        id=model_service.HAIKU_45,
        name="Haiku 4.5",
        description="Fast and affordable",
        series="haiku",
    ),
    ModelInfo(
        id="claude-sonnet-4-5-20241022",
        name="Sonnet 4.5",
        description="Previous generation Sonnet",
        series="sonnet",
    ),
    ModelInfo(
        id="claude-opus-4-5-20241022",
        name="Opus 4.5",
        description="Previous generation Opus",
        series="opus",
    ),
    ModelInfo(
        id="claude-opus-4-1-20250514",
        name="Opus 4.1",
        description="Opus with extended thinking",
        series="opus",
    ),
]


class ModelPickerDialog(Vertical):
    """Model selection dialog.

    Shows a searchable list of available models.
    """

    BINDINGS = [
        ("up", "move_up", "Move Up"),
        ("down", "move_down", "Move Down"),
        ("enter", "confirm", "Select"),
        ("escape", "cancel", "Cancel"),
    ]

    class Selected(Message):
        """Emitted when a model is selected."""

        def __init__(self, model_id: str) -> None:
            self.model_id = model_id
            super().__init__()

    class Cancelled(Message):
        """Emitted when user presses Escape."""

    def __init__(
        self,
        current_model: str | None = None,
        on_select: Callable[[str], None] | None = None,
        on_close: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._current = current_model or model_service.SONNET_46
        self._on_select = on_select
        self._on_close = on_close
        self._models = _AVAILABLE_MODELS
        self._filtered: list[ModelInfo] = _AVAILABLE_MODELS
        self._selected_index: int = 0
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        theme = get_theme()
        accent = theme.colors.get("accent", "cyan")

        yield Pane(title="Select Model", border_color=accent)
        yield Input(
            placeholder="Search models...",
            id="model-search-input",
        )
        yield Static("↑↓ navigate · Enter: select · Esc: cancel", id="model-hint")
        with ScrollableContainer(id="model-list"):
            with Vertical():
                for model in self._filtered:
                    is_current = model.id == self._current
                    icon = "✓ " if is_current else "  "
                    series_tag = f"[dim][{model.series}][/dim]"
                    yield ListItem(
                        item_id=model.id,
                        label=f"{icon}{model.name}",
                        description=f"{model.description} {series_tag}",
                    )

    def on_mount(self) -> None:
        """Focus search input on mount."""
        self.query_one("#model-search-input", Input).focus()
        self._select_current_model()

    def _select_current_model(self) -> None:
        """Select the current model in the list."""
        for i, model in enumerate(self._filtered):
            if model.id == self._current:
                self._selected_index = i
                break
        self._refresh_selection()

    def _refresh_selection(self) -> None:
        """Update visual selection state."""
        list_container = self.query_one("#model-list", ScrollableContainer)
        for i, child in enumerate(list_container.query(".list-item")):
            if hasattr(child, "item_id"):
                is_selected = i == self._selected_index
                if is_selected:
                    child.add_class("list-item--selected")
                else:
                    child.remove_class("list-item--selected")

    def _filter(self, query: str) -> None:
        """Filter models by query."""
        q = query.lower().strip()
        if not q:
            self._filtered = self._models[:]
        else:
            self._filtered = [
                m for m in self._models
                if q in m.name.lower() or q in m.id.lower() or q in m.description.lower()
            ]
        self._selected_index = 0
        self._refresh_list()

    def _refresh_list(self) -> None:
        """Rebuild the model list."""
        list_container = self.query_one("#model-list", ScrollableContainer)
        list_container.remove_children()

        theme = get_theme()
        accent = theme.colors.get("accent", "cyan")
        dim = theme.colors.get("text_dim", "#555555")

        for i, model in enumerate(self._filtered[:15]):
            is_selected = i == self._selected_index
            is_current = model.id == self._current
            prefix = "▶" if is_selected else " "
            icon = "✓" if is_current else " "
            color = accent if is_selected else (dim if not is_current else "green")

            parts = [f"[{color}]{prefix}{icon}{model.name}[/]"]
            parts.append(f"[{dim}]{model.id}[/]")
            parts.append(f"[{dim}]{model.description} [{model.series}][/]")

            list_container.mount(
                ListItem(
                    item_id=model.id,
                    label=f"{prefix}{icon}{model.name}",
                    description=f"{model.id} — {model.description} [{model.series}]",
                )
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "model-search-input":
            self._filter(event.value)

    def action_move_up(self) -> None:
        """Move selection up."""
        if self._filtered:
            self._selected_index = (self._selected_index - 1) % len(self._filtered)
            self._refresh_selection()

    def action_move_down(self) -> None:
        """Move selection down."""
        if self._filtered:
            self._selected_index = (self._selected_index + 1) % len(self._filtered)
            self._refresh_selection()

    def action_confirm(self) -> None:
        """Confirm selection."""
        if not self._filtered:
            return
        model = self._filtered[self._selected_index]
        self.post_message(self.Selected(model.id))
        if self._on_select:
            self._on_select(model.id)
        self._close()

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.post_message(self.Cancelled())
        self._close()

    def _close(self) -> None:
        """Close the dialog."""
        if self._on_close:
            self._on_close()
        self.remove()
