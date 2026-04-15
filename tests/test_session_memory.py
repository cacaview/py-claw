"""Tests for session memory module."""
from __future__ import annotations

from py_claw.services.session_memory import (
    DEFAULT_SESSION_MEMORY_CONFIG,
    SessionMemoryConfig,
    get_session_memory_config,
    set_session_memory_config,
    SessionMemoryState,
    get_last_summarized_message_id,
    set_last_summarized_message_id,
    mark_extraction_started,
    mark_extraction_completed,
    mark_session_memory_initialized,
    record_extraction_token_count,
    has_met_initialization_threshold,
    has_met_update_threshold,
    should_trigger_update,
    reset_session_memory_state,
    get_state,
    get_memory_path,
    get_memory_dir,
    get_session_memory_content,
    is_session_memory_empty,
    setup_session_memory_file,
    build_session_memory_update_prompt,
    extract_session_memory,
    should_extract_memory,
    truncate_session_memory_for_compact,
)
from pathlib import Path


def test_default_config() -> None:
    config = DEFAULT_SESSION_MEMORY_CONFIG
    assert config.minimum_message_tokens_to_init == 10_000
    assert config.minimum_tokens_between_update == 5_000
    assert config.tool_calls_between_updates == 3


def test_get_and_set_config() -> None:
    reset_session_memory_state()
    original = get_session_memory_config()
    assert original.minimum_message_tokens_to_init == 10_000

    new_config = SessionMemoryConfig(
        minimum_message_tokens_to_init=15000,
        minimum_tokens_between_update=7000,
        tool_calls_between_updates=5,
    )
    set_session_memory_config(new_config)

    updated = get_session_memory_config()
    assert updated.minimum_message_tokens_to_init == 15_000
    assert updated.minimum_tokens_between_update == 7_000
    assert updated.tool_calls_between_updates == 5

    # Reset to default
    set_session_memory_config(DEFAULT_SESSION_MEMORY_CONFIG)


def test_state_initialization() -> None:
    reset_session_memory_state()
    state = get_state()
    assert state.last_summarized_message_id is None
    assert state.tokens_at_last_extraction == 0
    assert state.initialized is False
    assert state.extraction_started_at is None


def test_last_summarized_message_id() -> None:
    reset_session_memory_state()
    assert get_last_summarized_message_id() is None

    set_last_summarized_message_id("msg-123")
    assert get_last_summarized_message_id() == "msg-123"

    set_last_summarized_message_id(None)
    assert get_last_summarized_message_id() is None


def test_extraction_started_completed() -> None:
    reset_session_memory_state()
    state = get_state()

    assert state.extraction_started_at is None

    mark_extraction_started()
    assert state.extraction_started_at is not None

    mark_extraction_completed()
    assert state.extraction_started_at is None


def test_record_extraction_token_count() -> None:
    reset_session_memory_state()
    record_extraction_token_count(15000)
    state = get_state()
    assert state.tokens_at_last_extraction == 15000


def test_initialization_threshold() -> None:
    reset_session_memory_state()

    # Below threshold
    assert has_met_initialization_threshold(5000) is False

    # At threshold
    assert has_met_initialization_threshold(10000) is True

    # Above threshold
    assert has_met_initialization_threshold(15000) is True


def test_update_threshold_requires_initialization() -> None:
    reset_session_memory_state()
    set_session_memory_config(SessionMemoryConfig(
        minimum_message_tokens_to_init=10000,
        minimum_tokens_between_update=5000,
        tool_calls_between_updates=3,
    ))

    # Not initialized yet
    assert has_met_update_threshold(20000) is False


def test_update_threshold_after_initialization() -> None:
    reset_session_memory_state()
    set_session_memory_config(SessionMemoryConfig(
        minimum_message_tokens_to_init=10000,
        minimum_tokens_between_update=5000,
        tool_calls_between_updates=3,
    ))
    # Mark as initialized
    mark_session_memory_initialized()
    record_extraction_token_count(12000)

    # Token growth below threshold
    assert has_met_update_threshold(15000) is False

    # Token growth at threshold
    assert has_met_update_threshold(17000) is True


def test_should_trigger_update() -> None:
    reset_session_memory_state()
    set_session_memory_config(SessionMemoryConfig(
        minimum_message_tokens_to_init=10000,
        minimum_tokens_between_update=5000,
        tool_calls_between_updates=3,
    ))

    # Token count below initialization threshold
    should_extract, reason = should_extract_memory(5000, 5)
    assert should_extract is False
    assert reason == "not_yet_initialized"

    # Token count at initialization threshold but no last_summarized_id
    # This triggers initialization_threshold_met
    should_extract, reason = should_extract_memory(10000, 5)
    assert should_extract is True
    assert reason == "initialization_threshold_met"

    # After first extraction, set last_summarized_id and tokens_at_last_extraction
    # to simulate having done an extraction
    set_last_summarized_message_id("msg-001")
    record_extraction_token_count(12000)

    # Token growth below threshold (15000 - 12000 = 3000 < 5000)
    should_extract, reason = should_extract_memory(15000, 5)
    assert should_extract is False

    # Token growth at threshold (17000 - 12000 = 5000 >= 5000) with enough tool calls
    should_extract, reason = should_extract_memory(17000, 5)
    assert should_extract is True
    assert reason == "update_threshold_met_with_tool_calls"

    # Token growth at threshold with tool calls
    should_extract, reason = should_extract_memory(17000, 5)
    assert should_extract is True
    assert reason == "update_threshold_met_with_tool_calls"

    # Token growth significantly above threshold (2x)
    should_extract, reason = should_extract_memory(25000, 1)
    assert should_extract is True
    assert reason == "update_threshold_significantly_exceeded"


def test_memory_paths() -> None:
    memory_dir = get_memory_dir()
    assert memory_dir.name == "session-memory"
    assert memory_dir.parent.name == ".claude"

    memory_path = get_memory_path()
    assert memory_path.name == "memory.md"
    assert memory_path.parent == memory_dir


def test_is_session_memory_empty() -> None:
    import asyncio
    # The function checks if content matches the default template
    # Empty string doesn't match template, so it's not "empty" in this sense
    # But actually, the logic is: content.trim() === template.trim()
    # An empty string trimmed is "" which doesn't equal the template
    # So actually "" is NOT considered empty

    # Test with empty string
    result = asyncio.run(is_session_memory_empty(""))
    assert result is False  # "" != template

    # Test with actual content that differs from template
    actual_content = """# Session Title
My Session Title

# Current State
Working on task X
"""
    result = asyncio.run(is_session_memory_empty(actual_content))
    assert result is False


def test_truncate_session_memory() -> None:
    # Create a long section
    long_content = """# Session Title
_A short title_

# Current State
_Description_
Short content here.

# Files and Functions
_What are the important files?_
""" + "\n".join([f"Line {i}" for i in range(1000)])

    truncated, was_truncated = truncate_session_memory_for_compact(long_content)
    assert was_truncated is True
    # Should contain the truncation marker
    assert "[... section truncated for length ...]" in truncated


def test_build_update_prompt(tmp_path: Path) -> None:
    current_notes = """# Session Title
My Session

# Current State
Working on task X
"""
    memory_path = tmp_path / "memory.md"

    import asyncio
    prompt = asyncio.run(
        build_session_memory_update_prompt(current_notes, memory_path)
    )

    # The prompt should be a non-empty string
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_reset_state() -> None:
    reset_session_memory_state()
    state = get_state()
    assert state.last_summarized_message_id is None
    assert state.tokens_at_last_extraction == 0
    assert state.initialized is False


def test_extract_session_memory_with_api_client(tmp_path: Path) -> None:
    import asyncio
    from unittest.mock import patch

    reset_session_memory_state()

    class DummyMessage:
        def __init__(self, message_id: str, text: str) -> None:
            self.id = message_id
            self.message = {"content": text}

    class DummyResponse:
        def __init__(self) -> None:
            self.content = [{"text": "# Session Title\nUpdated title\n"}]

    class DummyClient:
        def __init__(self) -> None:
            self.requests: list[object] = []

        def create_message(self, params):
            self.requests.append(params)
            return DummyResponse()

    dummy_client = DummyClient()
    messages = [DummyMessage("msg-1", "Hello")]

    with patch.object(Path, "home", return_value=tmp_path):
        from py_claw.services.session_memory.memory_file import get_memory_path

        memory_path = get_memory_path()
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text("# Session Title\nOld title\n", encoding="utf-8")

        result = asyncio.run(
            extract_session_memory(messages, 15000, dummy_client)
        )

        assert result["success"] is True
        assert result["api_used"] is True
        assert result["memory_written"] is True
        assert dummy_client.requests
        assert memory_path.read_text(encoding="utf-8") == "# Session Title\nUpdated title\n"


