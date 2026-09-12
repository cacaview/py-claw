"""MessageList — Scrollable message list component.

Re-implements ClaudeCode-main/src/components/design-system/MessageList.tsx
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


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

    DEFAULT_CSS = """
    MessageList {
        /* The content box must grow with its messages. A plain Vertical
           defaults to height: 1fr, which locks the content box to the
           viewport: the scrollable container then reports a virtual size no
           larger than itself and can never scroll. */
        #message-list-content {
            height: auto;
        }

        /* Each message is a plain Vertical, which also defaults to
           height: 1fr. Inside a fixed-height box the 1fr children split the
           viewport equally and their `overflow: hidden` clips long message
           text (only the first N lines show, N shrinking with pane height).
           height: auto lets every message size itself to its full text so the
           MessageList can scroll through it. */
        .message-item {
            height: auto;
        }
    }
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
        # Direct references to each message's content widget, keyed by message
        # index. Avoids query_one/children-index lookups on update, which can
        # fail while a freshly mounted message is not yet in the DOM.
        self._content_widgets: dict[int, ThemedText] = {}
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
        header_text = ThemedText(" ".join(header_parts), variant="normal")
        content_text = ThemedText(msg.content, variant="normal", classes="message-content")
        self._content_widgets[index] = content_text
        msg_container = Vertical(
            header_text,
            content_text,
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

    def watch_virtual_size(self, old_size, new_size) -> None:
        """Keep the log pinned to the bottom while content grows.

        scroll_end() called right after content is added/updated computes
        max_scroll_y from a *stale* virtual_size — layout has not run yet, so
        the log can stay parked at the top, showing only the first lines of a
        freshly added long message (the "long reply looks truncated" bug).
        Deferring from this watcher runs the scroll after the layout that
        changed virtual_size, so max_scroll_y is final and the scroll lands
        at the true bottom.
        """
        self.scroll_end(animate=False)

    def _update_content_widget(self, index: int, content: str) -> None:
        """Push new content into a message's content widget.

        Uses the direct widget reference recorded at mount time, falling back
        to a DOM query if the widget was not tracked (e.g. initial compose).
        Failures are logged instead of silently swallowed so streaming bugs
        are visible.
        """
        content_widget = self._content_widgets.get(index)
        if content_widget is None:
            try:
                container = self.query_one(f"#message-{index}", Vertical)
                content_widget = container.children[1]
            except Exception:
                logger.warning(
                    "MessageList: content widget for message %s not available for update",
                    index,
                    exc_info=True,
                )
                return
        try:
            content_widget.update(content)
            self.scroll_end(animate=False)
        except Exception:
            logger.warning(
                "MessageList: failed to update content of message %s",
                index,
                exc_info=True,
            )

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

        self._update_content_widget(idx, msg.content)

    def update_item(self, item: MessageItem, new_content: str, append: bool = False) -> None:
        """Update the content of a specific message (by identity, not position)."""
        # Identity lookup: MessageItem is an eq=True dataclass, so list.index()
        # would happily match a *different* message with equal field values.
        idx = next((i for i, m in enumerate(self._messages) if m is item), None)
        if idx is None:
            return
        if append:
            item.content += new_content
        else:
            item.content = new_content
        self._update_content_widget(idx, item.content)

    def clear_messages(self) -> None:
        """Clear all messages."""
        self._messages.clear()
        self._content_widgets.clear()
        container = self.query_one("#message-list-content", Vertical)
        container.remove_children()

    def get_messages(self) -> list[MessageItem]:
        """Get all messages."""
        return self._messages.copy()
