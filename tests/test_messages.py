"""Tests for messages service."""
from __future__ import annotations

import pytest

from py_claw.services.messages import (
    CANCEL_MESSAGE,
    INTERRUPT_MESSAGE,
    NO_CONTENT_MESSAGE,
    NO_RESPONSE_REQUESTED,
    REJECT_MESSAGE,
    SYNTHETIC_MESSAGES,
    AssistantMessage,
    AttachmentMessage,
    HookResultMessage,
    Message,
    ProgressMessage,
    SystemMessage,
    TombstoneMessage,
    ToolUseSummaryMessage,
    UserMessage,
    build_message_lookups,
    create_assistant_message,
    create_cancel_message,
    create_interrupt_message,
    create_progress_message,
    create_reject_message,
    create_user_message,
    derive_short_message_id,
    derive_uuid,
    get_last_assistant_message,
    get_tool_result_ids,
    get_tool_use_ids,
    has_tool_calls_in_last_assistant_turn,
    is_classifier_denial,
    is_not_empty_message,
    is_synthetic_message,
    is_tool_use_request_message,
    is_tool_use_result_message,
    normalize_messages,
    with_memory_correction_hint,
)


class TestConstants:
    """Tests for message constants."""

    def test_interrupt_message(self):
        """Test INTERRUPT_MESSAGE constant."""
        assert "[Request interrupted by user]" in INTERRUPT_MESSAGE

    def test_cancel_message(self):
        """Test CANCEL_MESSAGE constant."""
        assert "STOP" in CANCEL_MESSAGE
        assert "doesn't want" in CANCEL_MESSAGE

    def test_reject_message(self):
        """Test REJECT_MESSAGE constant."""
        assert "rejected" in REJECT_MESSAGE
        assert "STOP" in REJECT_MESSAGE

    def test_synthetic_messages_set(self):
        """Test SYNTHETIC_MESSAGES contains expected messages."""
        assert INTERRUPT_MESSAGE in SYNTHETIC_MESSAGES
        assert CANCEL_MESSAGE in SYNTHETIC_MESSAGES
        assert REJECT_MESSAGE in SYNTHETIC_MESSAGES
        assert NO_RESPONSE_REQUESTED in SYNTHETIC_MESSAGES

    def test_no_content_message(self):
        """Test NO_CONTENT_MESSAGE constant."""
        assert "(no content)" == NO_CONTENT_MESSAGE


class TestDeriveShortMessageId:
    """Tests for derive_short_message_id function."""

    def test_same_uuid_produces_same_id(self):
        """Same UUID always produces same short ID."""
        uid = "550e8400-e29b-41d4-a716-446655440000"
        id1 = derive_short_message_id(uid)
        id2 = derive_short_message_id(uid)
        assert id1 == id2

    def test_different_uuid_produces_different_id(self):
        """Different UUIDs produce different short IDs."""
        # Use UUIDs that differ significantly in the first 10 hex chars
        id1 = derive_short_message_id("550e8400-e29b-41d4-a716-446655440000")
        id2 = derive_short_message_id("660f8400-e29b-41d4-a716-446655440000")
        assert id1 != id2

    def test_short_id_length(self):
        """Short ID is at most 6 characters."""
        uid = "550e8400-e29b-41d4-a716-446655440000"
        short_id = derive_short_message_id(uid)
        assert len(short_id) <= 6


class TestDeriveUUID:
    """Tests for derive_uuid function."""

    def test_derive_uuid_deterministic(self):
        """Derived UUID is deterministic."""
        parent = "550e8400e29b41d4a716446655440000"
        uuid1 = derive_uuid(parent, 0)
        uuid2 = derive_uuid(parent, 0)
        assert uuid1 == uuid2

    def test_derive_uuid_different_indices(self):
        """Different indices produce different UUIDs."""
        parent = "550e8400e29b41d4a716446655440000"
        uuid1 = derive_uuid(parent, 0)
        uuid2 = derive_uuid(parent, 1)
        assert uuid1 != uuid2


class TestCreateUserMessage:
    """Tests for create_user_message function."""

    def test_create_user_message_with_string(self):
        """Test creating user message with string content."""
        msg = create_user_message("Hello world")
        assert msg.type == "user"
        # String content is wrapped in text block
        assert msg.message["content"] == [{"type": "text", "text": "Hello world"}]
        assert msg.uuid is not None

    def test_create_user_message_with_blocks(self):
        """Test creating user message with content blocks."""
        blocks = [{"type": "text", "text": "Hello"}]
        msg = create_user_message(blocks)
        assert msg.type == "user"
        assert msg.message["content"] == blocks

    def test_create_user_message_with_uuid(self):
        """Test creating user message with custom UUID."""
        custom_uuid = "12345678-1234-1234-1234-123456789012"
        msg = create_user_message("Hello", msg_uuid=custom_uuid)
        assert msg.uuid == custom_uuid

    def test_create_user_message_meta(self):
        """Test creating meta user message."""
        msg = create_user_message("Meta content", is_meta=True)
        assert msg.isMeta is True


class TestCreateAssistantMessage:
    """Tests for create_assistant_message function."""

    def test_create_assistant_message_with_string(self):
        """Test creating assistant message with string content."""
        msg = create_assistant_message("Hi there!")
        assert msg.type == "assistant"
        assert msg.message["content"][0]["text"] == "Hi there!"

    def test_create_assistant_message_empty_string(self):
        """Test empty string becomes NO_CONTENT_MESSAGE."""
        msg = create_assistant_message("")
        assert msg.message["content"][0]["text"] == NO_CONTENT_MESSAGE

    def test_create_assistant_message_with_blocks(self):
        """Test creating assistant message with content blocks."""
        blocks = [{"type": "text", "text": "Hello"}]
        msg = create_assistant_message(blocks)
        assert msg.type == "assistant"
        assert msg.message["content"] == blocks


class TestCreateInterruptMessage:
    """Tests for create_interrupt_message function."""

    def test_create_interrupt_message(self):
        """Test creating interrupt message."""
        msg = create_interrupt_message()
        assert msg.type == "user"
        assert INTERRUPT_MESSAGE in str(msg.message)


class TestCreateCancelMessage:
    """Tests for create_cancel_message function."""

    def test_create_cancel_message(self):
        """Test creating cancel message."""
        msg = create_cancel_message()
        assert msg.type == "user"
        assert CANCEL_MESSAGE in str(msg.message)


class TestCreateRejectMessage:
    """Tests for create_reject_message function."""

    def test_create_reject_message_without_reason(self):
        """Test creating reject message without reason."""
        msg = create_reject_message()
        assert msg.type == "user"
        assert REJECT_MESSAGE in str(msg.message)

    def test_create_reject_message_with_reason(self):
        """Test creating reject message with reason."""
        msg = create_reject_message(reason="User said no")
        assert msg.type == "user"
        assert "User said no" in str(msg.message)


class TestCreateProgressMessage:
    """Tests for create_progress_message function."""

    def test_create_progress_message(self):
        """Test creating progress message."""
        progress_data = {"text": "Processing..."}
        msg = create_progress_message(progress_data)
        assert msg["type"] == "progress"
        assert msg["progress"] == progress_data
        assert "uuid" in msg


class TestIsSyntheticMessage:
    """Tests for is_synthetic_message function."""

    def test_interrupt_message_is_synthetic(self):
        """Test interrupt message is synthetic."""
        msg = create_interrupt_message()
        assert is_synthetic_message(msg) is True

    def test_cancel_message_is_synthetic(self):
        """Test cancel message is synthetic."""
        msg = create_cancel_message()
        assert is_synthetic_message(msg) is True

    def test_regular_user_message_not_synthetic(self):
        """Test regular user message is not synthetic."""
        msg = create_user_message("Hello world")
        assert is_synthetic_message(msg) is False

    def test_progress_message_not_synthetic(self):
        """Test progress message is not synthetic."""
        msg = {"type": "progress", "progress": {}}
        assert is_synthetic_message(msg) is False


class TestGetLastAssistantMessage:
    """Tests for get_last_assistant_message function."""

    def test_get_last_assistant_message(self):
        """Test getting last assistant message."""
        messages = [
            create_user_message("Hello"),
            create_assistant_message("Hi!"),
            create_user_message("How are you?"),
            create_assistant_message("I'm good!"),
        ]
        last = get_last_assistant_message(messages)
        assert last is not None
        assert last.type == "assistant"
        assert "I'm good!" in str(last.message)

    def test_no_assistant_message(self):
        """Test when no assistant message exists."""
        messages = [create_user_message("Hello")]
        last = get_last_assistant_message(messages)
        assert last is None


class TestHasToolCallsInLastAssistantTurn:
    """Tests for has_tool_calls_in_last_assistant_turn function."""

    def test_has_tool_calls(self):
        """Test detecting tool calls in last assistant turn."""
        messages = [
            create_user_message("Run ls"),
            create_assistant_message(
                content=[{"type": "tool_use", "id": "1", "name": "bash"}]
            ),
        ]
        assert has_tool_calls_in_last_assistant_turn(messages) is True

    def test_no_tool_calls(self):
        """Test when no tool calls in last assistant turn."""
        messages = [
            create_user_message("Hello"),
            create_assistant_message("Hi!"),
        ]
        assert has_tool_calls_in_last_assistant_turn(messages) is False


class TestNormalizeMessages:
    """Tests for normalize_messages function."""

    def test_normalize_single_block_messages(self):
        """Test normalizing messages with single content blocks."""
        messages = [
            create_user_message("Hello"),
            create_assistant_message("Hi!"),
        ]
        normalized = normalize_messages(messages)
        assert len(normalized) == 2
        assert normalized[0]["type"] == "user"
        assert normalized[1]["type"] == "assistant"

    def test_normalize_multi_block_assistant_message(self):
        """Test normalizing assistant message with multiple blocks."""
        msg = create_assistant_message(
            "Hello",
            msg_uuid="550e8400-e29b-41d4-a716-446655440000"
        )
        msg.message["content"] = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        normalized = normalize_messages([msg])
        assert len(normalized) == 2
        assert normalized[0]["message"]["content"][0]["text"] == "Hello"
        assert normalized[1]["message"]["content"][0]["text"] == "World"


class TestBuildMessageLookups:
    """Tests for build_message_lookups function."""

    def test_build_lookups_with_tool_calls(self):
        """Test building lookups with tool calls."""
        messages = [
            create_user_message("Run ls"),
            create_assistant_message("Running ls", [
                {"type": "tool_use", "id": "tool_1", "name": "bash"},
                {"type": "tool_use", "id": "tool_2", "name": "bash"},
            ]),
            create_user_message("Here you go", [
                {"type": "tool_result", "tool_use_id": "tool_1", "content": "file1\nfile2"},
            ]),
        ]
        lookups = build_message_lookups(messages)
        assert "toolUseIds" in lookups
        assert "toolResultIds" in lookups
        assert "progressMessages" in lookups


class TestIsClassifierDenial:
    """Tests for is_classifier_denial function."""

    def test_classifier_denial(self):
        """Test detecting classifier denial."""
        content = "Permission for this action has been denied. Reason: tool not allowed"
        assert is_classifier_denial(content) is True

    def test_not_classifier_denial(self):
        """Test non-denial content."""
        content = "This is a normal message"
        assert is_classifier_denial(content) is False


class TestWithMemoryCorrectionHint:
    """Tests for with_memory_correction_hint function."""

    def test_without_auto_memory(self):
        """Test without auto memory enabled."""
        result = with_memory_correction_hint("Hello", is_auto_memory_enabled=False)
        assert result == "Hello"

    def test_with_auto_memory(self):
        """Test with auto memory enabled."""
        result = with_memory_correction_hint("Hello", is_auto_memory_enabled=True)
        assert "MEMORY_CORRECTION_HINT" in result or "correction" in result.lower()


class TestIsToolUseRequestMessage:
    """Tests for is_tool_use_request_message function."""

    def test_tool_use_request(self):
        """Test detecting tool use request."""
        msg = create_assistant_message(
            content=[{"type": "text", "text": "Using tool"}, {"type": "tool_use", "id": "1", "name": "bash"}]
        )
        assert is_tool_use_request_message(msg) is True

    def test_regular_message(self):
        """Test regular message is not tool use request."""
        msg = create_assistant_message("Hello")
        assert is_tool_use_request_message(msg) is False


class TestIsToolUseResultMessage:
    """Tests for is_tool_use_result_message function."""

    def test_tool_result_message(self):
        """Test detecting tool result message."""
        msg = create_user_message([
            {"type": "tool_result", "tool_use_id": "1", "content": "result"}
        ])
        assert is_tool_use_result_message(msg) is True

    def test_regular_message(self):
        """Test regular message is not tool result."""
        msg = create_user_message("Hello")
        assert is_tool_use_result_message(msg) is False


class TestGetToolUseIds:
    """Tests for get_tool_use_ids function."""

    def test_extract_tool_use_ids(self):
        """Test extracting tool use IDs."""
        messages = [
            create_assistant_message(
                content=[
                    {"type": "text", "text": "Using tools"},
                    {"type": "tool_use", "id": "tool_1", "name": "bash"},
                    {"type": "tool_use", "id": "tool_2", "name": "bash"},
                ]
            )
        ]
        ids = get_tool_use_ids(messages)
        assert len(ids) == 2
        assert "tool_1" in ids
        assert "tool_2" in ids


class TestGetToolResultIds:
    """Tests for get_tool_result_ids function."""

    def test_extract_tool_result_ids(self):
        """Test extracting tool result IDs."""
        messages = [
            create_user_message(
                content=[
                    {"type": "tool_result", "tool_use_id": "tool_1", "content": "result1"},
                    {"type": "tool_result", "tool_use_id": "tool_2", "content": "result2"},
                ]
            )
        ]
        ids = get_tool_result_ids(messages)
        assert len(ids) == 2
        assert "tool_1" in ids
        assert "tool_2" in ids
