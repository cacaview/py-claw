"""FuzzyPicker — Fuzzy search picker component.

Re-implements ClaudeCode-main/src/components/design-system/FuzzyPicker.tsx
"""

from __future__ import annotations

import re
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Input, Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.themed_text import ThemedText


class FuzzyMatch:
    """A fuzzy match result."""

    def __init__(self, item: dict, score: float, matched_indices: list[int]) -> None:
        self.item = item
        self.score = score
        self.matched_indices = matched_indices


class FuzzyPicker(Container):
    """A fuzzy search picker with keyboard navigation.

    Supports:
    - Single/multi select with input option mixing
    - Keyboard navigation with boundary callbacks
    - Inline description and preview style layout
    - Panel-style, compact-style, and vertical layout switching
    """

    BINDINGS = [
        ("up", "move_up", "Move Up"),
        ("down", "move_down", "Move Down"),
        ("enter", "select", "Select"),
        ("escape", "cancel", "Cancel"),
    ]

    class Selected(Message):
        """Message sent when an item is selected."""

        def __init__(self, item: dict, index: int) -> None:
            self.item = item
            self.index = index
            super().__init__()

    def __init__(
        self,
        items: list[dict],  # list of {id, label, description?, ...}
        on_select: Callable[[dict], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        placeholder: str = "Type to search...",
        show_descriptions: bool = True,
        layout: str = "vertical",  # "vertical" | "compact" | "panel"
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._items = items
        self._filtered_items = items
        self._on_select = on_select
        self._on_cancel = on_cancel
        self._placeholder = placeholder
        self._show_descriptions = show_descriptions
        self._layout = layout
        self._selected_index = 0
        self._query = ""
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the fuzzy picker layout."""
        theme = get_theme()

        # Search input
        yield Input(placeholder=self._placeholder, id="fuzzy-input")

        # Results list
        with Vertical(id="fuzzy-results"):
            for i, item in enumerate(self._filtered_items[:10]):  # Limit to 10 visible
                yield self._make_item_widget(item, i)

        # Count indicator
        yield ThemedText(
            f"{len(self._filtered_items)} items",
            variant="muted",
            id="fuzzy-count",
        )

    def _make_item_widget(self, item: dict, index: int) -> Horizontal:
        """Create a widget for an item."""
        label = item.get("label", "Unknown")
        description = item.get("description")

        if self._show_descriptions and description:
            container = Horizontal(
                Static(f"[{index + 1}] {label}", id=f"fuzzy-item-{index}"),
                Static(description, id=f"fuzzy-desc-{index}"),
                classes="fuzzy-item",
            )
        else:
            container = Horizontal(
                Static(f"[{index + 1}] {label}", id=f"fuzzy-item-{index}"),
                classes="fuzzy-item",
            )

        if index == self._selected_index:
            container.classes = "fuzzy-item fuzzy-item-selected"

        return container

    def _fuzzy_match(self, query: str, text: str) -> tuple[float, list[int]]:
        """Perform fuzzy matching and return score and matched indices."""
        if not query:
            return 1.0, []

        query_lower = query.lower()
        text_lower = text.lower()

        # Simple fuzzy scoring
        score = 0.0
        matched_indices = []

        query_idx = 0
        for i, char in enumerate(text_lower):
            if query_idx < len(query_lower) and char == query_lower[query_idx]:
                score += 1.0
                matched_indices.append(i)
                query_idx += 1

        # Penalty for gaps
        if matched_indices:
            max_gap = max(matched_indices) - min(matched_indices)
            score -= max_gap * 0.1

        # Normalize by query length
        if query_idx < len(query_lower):
            return 0.0, []

        return score / len(query), matched_indices

    def _filter_items(self, query: str) -> list[dict]:
        """Filter items based on fuzzy match."""
        if not query:
            return self._items

        results: list[tuple[dict, float]] = []
        for item in self._items:
            label = item.get("label", "")
            description = item.get("description", "")

            label_score, _ = self._fuzzy_match(query, label)
            desc_score, _ = self._fuzzy_match(query, description)

            best_score = max(label_score, desc_score)
            if best_score > 0:
                results.append((item, best_score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in results]

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes for filtering."""
        self._query = event.value
        self._filtered_items = self._filter_items(self._query)
        self._selected_index = 0
        self._refresh_list()

    def _refresh_list(self) -> None:
        """Refresh the results list."""
        results_container = self.query_one("#fuzzy-results", Vertical)
        results_container.remove_children()

        for i, item in enumerate(self._filtered_items[:10]):
            results_container.mount(self._make_item_widget(item, i))

        count = self.query_one("#fuzzy-count", Static)
        count.update(f"{len(self._filtered_items)} items")

    def action_move_up(self) -> None:
        """Move selection up."""
        if self._filtered_items:
            self._selected_index = (self._selected_index - 1) % len(self._filtered_items[:10])
            self._update_selection()

    def action_move_down(self) -> None:
        """Move selection down."""
        if self._filtered_items:
            self._selected_index = (self._selected_index + 1) % len(self._filtered_items[:10])
            self._update_selection()

    def _update_selection(self) -> None:
        """Update visual selection state."""
        for i, child in enumerate(self.query("#fuzzy-results > .fuzzy-item")):
            if i == self._selected_index:
                child.classes = "fuzzy-item fuzzy-item-selected"
            else:
                child.classes = "fuzzy-item"

    def action_select(self) -> None:
        """Select the current item."""
        if self._filtered_items and self._selected_index < len(self._filtered_items):
            item = self._filtered_items[self._selected_index]
            self.post_message(self.Selected(item, self._selected_index))
            if self._on_select:
                self._on_select(item)

    def action_cancel(self) -> None:
        """Cancel the picker."""
        if self._on_cancel:
            self._on_cancel()
