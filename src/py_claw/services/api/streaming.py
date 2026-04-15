from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from py_claw.services.api.types import (
    ContentBlock,
    Message,
    MessageDelta,
    MessageStartEvent,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
)


@dataclass
class AssistantMessageBuilder:
    """Build an assistant message from stream events."""

    message_id: str | None = None
    role: str = "assistant"
    model: str | None = None
    content: list[ContentBlock] = field(default_factory=list)
    stop_reason: str | None = None
    usage: Usage | None = None
    _current_block: dict[str, Any] | None = None
    _current_block_index: int = -1

    def apply(self, event: StreamEvent) -> None:
        """Apply a stream event to build the message."""
        if event.type == "message_start":
            e = event  # type: MessageStartEvent
            self.message_id = e.message.id
            self.role = e.message.role
            self.model = e.message.model
            self.usage = e.message.usage
            return

        if event.type == "content_block_start":
            index = event.index
            block = event.content_block
            self._current_block_index = index
            self._current_block = {
                "type": block.type,
                "text": "",
                "thinking": "",
                "id": "",
                "name": "",
                "input": {},
            }
            return

        if event.type == "content_block_delta":
            delta = event.delta
            if self._current_block is None:
                return

            if delta.type == "text_delta" and delta.text:
                self._current_block["text"] = (self._current_block.get("text") or "") + delta.text
            elif delta.type == "thinking_delta" and delta.thinking:
                self._current_block["thinking"] = (self._current_block.get("thinking") or "") + delta.thinking
            elif delta.type == "input_json_delta" and delta.input_json:
                # Accumulate tool input JSON
                existing = self._current_block.get("input_str", "")
                self._current_block["input_str"] = existing + delta.input_json
            return

        if event.type == "content_block_stop":
            # Finalize the current block
            if self._current_block is not None:
                block_type = self._current_block["type"]
                if block_type == "text":
                    self.content.append(TextBlock(
                        type="text",
                        text=self._current_block.get("text", ""),
                    ))
                elif block_type == "thinking":
                    self.content.append(ThinkingBlock(
                        type="thinking",
                        thinking=self._current_block.get("thinking", ""),
                    ))
                elif block_type == "tool_use":
                    input_str = self._current_block.get("input_str", "{}")
                    try:
                        import json
                        input_data = json.loads(input_str)
                    except (json.JSONDecodeError, TypeError):
                        input_data = {}
                    self.content.append(ToolUseBlock(
                        type="tool_use",
                        id=self._current_block.get("id", ""),
                        name=self._current_block.get("name", ""),
                        input=input_data,
                    ))
                self._current_block = None
            return

        if event.type == "message_delta":
            e = event  # type: MessageDeltaEvent
            if e.delta.stop_reason:
                self.stop_reason = e.delta.stop_reason
            if e.delta.usage:
                self.usage = e.delta.usage
            return

    def build(self) -> Message:
        """Build the final message."""
        if self.message_id is None:
            self.message_id = "unknown"
        if self.stop_reason is None:
            self.stop_reason = "end_turn"
        if self.usage is None:
            self.usage = Usage(input_tokens=0, output_tokens=0)
        return Message(
            id=self.message_id,
            type="message",
            role=self.role,
            content=self.content,
            model=self.model or "unknown",
            stop_reason=self.stop_reason,
            usage=self.usage,
        )


def parse_stream_events(
    raw_events: Iterator[dict[str, Any]],
) -> Iterator[StreamEvent]:
    """Parse raw event dicts into StreamEvent objects.

    This is useful when events come as plain dicts rather than
    typed objects (e.g., from SSE data parsing).
    """
    for raw in raw_events:
        event_type = raw.get("type", "")
        if event_type == "message_start":
            msg_raw = raw.get("message", {})
            from py_claw.services.api.types import Message
            msg = Message(
                id=msg_raw.get("id", ""),
                type="message",
                role=msg_raw.get("role", "assistant"),
                content=[],
                model=msg_raw.get("model", ""),
                usage=Usage(
                    input_tokens=msg_raw.get("usage", {}).get("input_tokens", 0),
                    output_tokens=msg_raw.get("usage", {}).get("output_tokens", 0),
                ),
            )
            yield MessageStartEvent(type="message_start", message=msg)

        elif event_type == "content_block_start":
            block_raw = raw.get("content_block", {})
            from py_claw.services.api.types import ContentBlock, ContentBlockStartEvent
            yield ContentBlockStartEvent(
                type="content_block_start",
                index=raw.get("index", 0),
                content_block=ContentBlock(
                    type=block_raw.get("type", "text"),
                    text="",
                ),
            )

        elif event_type == "content_block_delta":
            delta_raw = raw.get("delta", {})
            delta_type = delta_raw.get("type", "text_delta")
            from py_claw.services.api.types import ContentBlockDeltaEvent, ContentDelta
            yield ContentBlockDeltaEvent(
                type="content_block_delta",
                index=raw.get("index", 0),
                delta=ContentDelta(
                    type=delta_type,
                    text=delta_raw.get("text"),
                    thinking=delta_raw.get("thinking"),
                    input_json=delta_raw.get("input_json"),
                ),
            )

        elif event_type == "content_block_stop":
            from py_claw.services.api.types import ContentBlockStopEvent
            yield ContentBlockStopEvent(
                type="content_block_stop",
                index=raw.get("index", 0),
            )

        elif event_type == "message_delta":
            delta_raw = raw.get("delta", {})
            usage_raw = delta_raw.get("usage", {})
            from py_claw.services.api.types import MessageDelta, MessageDeltaEvent
            yield MessageDeltaEvent(
                type="message_delta",
                delta=MessageDelta(
                    stop_reason=delta_raw.get("stop_reason"),
                    usage=Usage(
                        input_tokens=usage_raw.get("input_tokens", 0),
                        output_tokens=usage_raw.get("output_tokens", 0),
                    ) if usage_raw else None,
                ),
            )

        elif event_type == "message_stop":
            from py_claw.services.api.types import MessageStopEvent
            yield MessageStopEvent(type="message_stop")

        elif event_type == "error":
            from py_claw.services.api.types import ErrorEvent
            error_raw = raw.get("error", {})
            yield ErrorEvent(
                type="error",
                error=error_raw.get("message", str(raw)),
                code=error_raw.get("type"),
            )


@dataclass
class StreamingResult:
    """Result of a streaming message creation."""

    message: Message
    finish_reason: str | None

    @property
    def text(self) -> str:
        """Extract text content from the message."""
        parts = []
        for block in self.message.content:
            if hasattr(block, "text") and block.text:
                parts.append(block.text)
        return "".join(parts)

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        """Extract tool use blocks from the message."""
        return [b for b in self.message.content if isinstance(b, ToolUseBlock)]
