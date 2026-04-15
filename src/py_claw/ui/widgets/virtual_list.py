"""VirtualMessageList — Virtualized message list for large conversations.

Re-implements ClaudeCode-main/src/components/design-system/VirtualMessageList.tsx
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.widgets import Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.themed_text import ThemedText


class MessageRole(Enum):
    """Message sender role."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass(slots=True)
class MessageItem:
    """A single message in the list."""

    role: MessageRole
    content: str
    timestamp: datetime | None = None
    tool_name: str | None = None
    status: str | None = None
    tool_use_id: str | None = None


class VirtualMessageList(ScrollableContainer):
    """A virtualized message list for large conversations.

    Uses windowing to only render visible messages, enabling
    efficient display of 1000+ message conversations.
    """

    class MessageClicked(Message):
        """Message sent when a message is clicked."""

        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    WINDOW_SIZE = 50  # Number of messages to render at once

    def __init__(
        self,
        messages: list[MessageItem] | None = None,
        on_message_click: Callable[[int], None] | None = None,
        show_timestamps: bool = True,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._all_messages = messages or []
        self._visible_start = 0
        self._on_message_click = on_message_click
        self._show_timestamps = show_timestamps
        self._scroll_offset = 0
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the virtual message list."""
        # Show window of messages
        visible_messages = self._all_messages[
            self._visible_start : self._visible_start + self.WINDOW_SIZE
        ]

        with Vertical(id="virtual-message-list"):
            # Padding at top for scroll position
            if self._visible_start > 0:
                yield Static(f"--- {self._visible_start} earlier messages ---", id="virtual-padding-top")

            for i, msg in enumerate(visible_messages):
                yield self._make_message_widget(msg, self._visible_start + i)

            # Padding at bottom
            remaining = len(self._all_messages) - (self._visible_start + self.WINDOW_SIZE)
            if remaining > 0:
                yield Static(f"--- {remaining} more messages ---", id="virtual-padding-bottom")

    def _make_message_widget(self, msg: MessageItem, index: int) -> Vertical:
        """Create a widget for a message."""
        theme = get_theme()

        # Role styling
        role_colors = {
            MessageRole.USER: theme.colors.get("primary", "#3b82f6"),
            MessageRole.ASSISTANT: theme.colors.get("success", "#22c55e"),
            MessageRole.SYSTEM: theme.colors.get("warning", "#f59e0b"),
            MessageRole.TOOL: theme.colors.get("info", "#06b6d4"),
        }

        role_labels = {
            MessageRole.USER: "You",
            MessageRole.ASSISTANT: "Assistant",
            MessageRole.SYSTEM: "System",
            MessageRole.TOOL: f"Tool: {msg.tool_name}" if msg.tool_name else "Tool",
        }

        color = role_colors.get(msg.role, theme.colors.get("text", "#ffffff"))
        label = role_labels.get(msg.role, "Unknown")

        msg_container = Vertical(id=f"vmessage-{index}", classes="vmessage-item")

        # Header
        header_parts = [f"[{color}]{label}[/{color}]"]
        if self._show_timestamps and msg.timestamp:
            header_parts.append(f" [/{theme.colors.get('text_dim', '#555555')}]"f"{msg.timestamp.strftime('%H:%M:%S')}[/]")
        if msg.status:
            status_colors = {"pending": "warning", "complete": "success", "error": "error"}
            status_color = status_colors.get(msg.status, "muted")
            header_parts.append(f" [/{theme.colors.get(status_color, '#888888')}] {msg.status}[/]")

        msg_container.mount(ThemedText(" ".join(header_parts), variant="normal"))

        # Content - truncate if too long
        content = msg.content
        if len(content) > 5000:
            content = content[:5000] + "..."

        msg_container.mount(ThemedText(content, variant="normal"))

        return msg_container

    def on_scroll(self) -> None:
        """Handle scroll to update visible window."""
        # This is a simplified implementation
        # Real implementation would calculate visible range based on scroll position
        pass

    def scroll_to_bottom(self) -> None:
        """Scroll to the end of the message list."""
        self._visible_start = max(0, len(self._all_messages) - self.WINDOW_SIZE)
        self.refresh()

    def scroll_to_top(self) -> None:
        """Scroll to the beginning of the message list."""
        self._visible_start = 0
        self.refresh()

    def add_message(self, msg: MessageItem) -> None:
        """Add a new message."""
        self._all_messages.append(msg)
        # Auto-scroll if at bottom
        if self._visible_start + self.WINDOW_SIZE >= len(self._all_messages) - 1:
            self.scroll_to_bottom()
        else:
            self.refresh()

    def clear_messages(self) -> None:
        """Clear all messages."""
        self._all_messages.clear()
        self._visible_start = 0
        self.refresh()

    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self._all_messages)
