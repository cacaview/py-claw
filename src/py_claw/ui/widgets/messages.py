"""MessageList — Scrollable message list component.

Re-implements ClaudeCode-main/src/components/design-system/MessageList.tsx
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
    status: str | None = None  # "pending", "complete", "error"


class MessageList(ScrollableContainer):
    """A scrollable list of messages.

    Displays conversation messages with:
    - Role-based styling (user/assistant/system/tool)
    - Timestamp display
    - Tool execution status
    - Auto-scroll to bottom on new messages
    """

    class MessageClicked(Message):
        """Message sent when a message is clicked."""

        def __init__(self, index: int) -> None:
            self.index = index
            super().__init__()

    def __init__(
        self,
        messages: list[MessageItem] | None = None,
        on_message_click: Callable[[int], None] | None = None,
        show_timestamps: bool = True,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._messages = messages or []
        self._on_message_click = on_message_click
        self._show_timestamps = show_timestamps
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the message list."""
        with Vertical(id="message-list-content"):
            for i, msg in enumerate(self._messages):
                yield self._make_message_widget(msg, i)

    def _make_message_widget(self, msg: MessageItem, index: int) -> Vertical:
        """Create a widget for a message."""
        theme = get_theme()

        # Role label and styling
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

        # Header with role and optional timestamp
        header_parts = [f"[{color}]{label}[/{color}]"]

        if self._show_timestamps and msg.timestamp:
            time_str = msg.timestamp.strftime("%H:%M:%S")
            header_parts.append(f" [{theme.colors.get('text_dim', '#555555')}]{time_str}[/]")

        if msg.status:
            status_colors = {"pending": "warning", "complete": "success", "error": "error"}
            status_color = status_colors.get(msg.status, "muted")
            header_parts.append(f" [{theme.colors.get(status_color, '#888888')}]{msg.status}[/]")

        # Build message container
        msg_container = Vertical(
            ThemedText(" ".join(header_parts), variant="normal"),
            ThemedText(msg.content, variant="normal"),
            id=f"message-{index}",
            classes="message-item",
        )

        return msg_container

    def add_message(self, msg: MessageItem) -> None:
        """Add a new message to the list."""
        self._messages.append(msg)
        container = self.query_one("#message-list-content", Vertical)
        container.mount(self._make_message_widget(msg, len(self._messages) - 1))
        self.scroll_end(animate=False)

    def update_last_message(self, new_content: str, append: bool = False) -> None:
        """Update or append to the content of the last message in the list.
        
        Args:
            new_content: The text to set or append.
            append: If True, append to existing content, otherwise replace it.
        """
        if not self._messages:
            return

        idx = len(self._messages) - 1
        msg = self._messages[idx]
        
        if append:
            msg.content += new_content
        else:
            msg.content = new_content

        # Find the message container and its content text widget
        # Index 1 is the content ThemedText (index 0 is the header)
        try:
            container = self.query_one(f"#message-{idx}", Vertical)
            content_widget = container.children[1]
            if hasattr(content_widget, 'update'):
                content_widget.update(msg.content)
            self.scroll_end(animate=False)
        except Exception:
            pass

    def clear_messages(self) -> None:
        """Clear all messages."""
        self._messages.clear()
        container = self.query_one("#message-list-content", Vertical)
        container.remove_children()

    def get_messages(self) -> list[MessageItem]:
        """Get all messages."""
        return self._messages.copy()
