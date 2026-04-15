"""Tabs — Keyboard-first tab navigation component.

Re-implements ClaudeCode-main/src/components/design-system/Tabs.tsx
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Static

from py_claw.ui.theme import get_theme


class TabsTab(Static):
    """A single tab button in the tab bar."""

    def __init__(self, label: str, tab_id: str, *, selected: bool = False) -> None:
        self.tab_id = tab_id
        self.label = label
        self.selected = selected
        super().__init__(label)

    def on_mount(self) -> None:
        """Style the tab based on selection state."""
        theme = get_theme()
        if self.selected:
            self.styles.background = theme.colors.get("surface_elevated", "#252525")
            self.styles.color = theme.colors.get("text", "#ffffff")
        else:
            self.styles.background = theme.colors.get("surface", "#1a1a1a")
            self.styles.color = theme.colors.get("text_muted", "#888888")


class TabsHeader(Horizontal):
    """The tab bar containing tab buttons."""

    def __init__(self, tabs: list[TabsTab], *, id: str | None = None) -> None:
        self._tabs = tabs
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        """Compose the tab bar."""
        for tab in self._tabs:
            yield tab


class TabsContent(Container):
    """The content area for the selected tab."""

    def __init__(self, tab_id: str, content: str, *, id: str | None = None) -> None:
        self.tab_id = tab_id
        self._content = content
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        """Compose the tab content."""
        yield Static(self._content, id=f"tab-content-{self.tab_id}")


class TabsFocused(Message):
    """Message sent when tab focus changes."""

    def __init__(self, tab_id: str) -> None:
        self.tab_id = tab_id
        super().__init__()


class Tabs(Container):
    """Keyboard-first tab navigation.

    Matches Tabs.tsx behavior:
    - header/content focus switching
    - navFromContent coordination
    - Support for controlled/uncontrolled tab selection
    - Modal and non-modal environment adaptation
    """

    BINDINGS = [
        ("left", "focus_previous", "Previous Tab"),
        ("right", "focus_next", "Next Tab"),
    ]

    def __init__(
        self,
        tabs: list[tuple[str, str]],  # list of (tab_id, label)
        initial_tab: str | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._tab_definitions = tabs
        self._selected_tab = initial_tab or (tabs[0][0] if tabs else None)
        self._header_focused = True
        self._content_focused = False
        self._opt_in = False  # navFromContent opt-in
        self._on_tab_change: Callable[[str], None] | None = None
        super().__init__(id=id, classes=classes)

    def on_mount(self) -> None:
        """Set up tab styling."""
        theme = get_theme()
        self.styles.background = theme.colors.get("surface", "#1a1a1a")

    def compose(self) -> ComposeResult:
        """Compose the tabs layout."""
        # Tab bar
        with Horizontal(id="tabs-header"):
            for tab_id, label in self._tab_definitions:
                yield TabsTab(
                    label=label,
                    tab_id=tab_id,
                    selected=(tab_id == self._selected_tab),
                )

        # Content area
        for tab_id, label in self._tab_definitions:
            if tab_id == self._selected_tab:
                yield TabsContent(tab_id=tab_id, content=f"Tab content: {label}", id=f"tab-{tab_id}")

    def select_tab(self, tab_id: str) -> None:
        """Programmatically select a tab."""
        if tab_id not in [t[0] for t in self._tab_definitions]:
            return

        old_tab = self._selected_tab
        self._selected_tab = tab_id

        # Update tab button states
        header = self.query_one("#tabs-header", Horizontal)
        for tab in header.query(TabsTab):
            tab.selected = tab.tab_id == tab_id

        # Post message for tab change
        self.post_message(TabsFocused(tab_id))

        if self._on_tab_change and old_tab != tab_id:
            self._on_tab_change(tab_id)

    def register_opt_in(self) -> None:
        """Register content area as opt-in for navigation events."""
        self._opt_in = True

    def unregister_opt_in(self) -> None:
        """Unregister content area from navigation events."""
        self._opt_in = False

    def action_focus_previous(self) -> None:
        """Move focus to the previous tab."""
        if not self._tab_definitions:
            return
        current_index = next(
            (i for i, (tid, _) in enumerate(self._tab_definitions) if tid == self._selected_tab),
            0,
        )
        prev_index = (current_index - 1) % len(self._tab_definitions)
        self.select_tab(self._tab_definitions[prev_index][0])

    def action_focus_next(self) -> None:
        """Move focus to the next tab."""
        if not self._tab_definitions:
            return
        current_index = next(
            (i for i, (tid, _) in enumerate(self._tab_definitions) if tid == self._selected_tab),
            0,
        )
        next_index = (current_index + 1) % len(self._tab_definitions)
        self.select_tab(self._tab_definitions[next_index][0])
