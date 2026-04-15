"""Tests for compact module."""
from __future__ import annotations

from py_claw.services.compact import (
    DEFAULT_COMPACT_CONFIG,
    CompactConfig,
    get_compact_config,
    set_compact_config,
    CompactionResult,
    RecompactionInfo,
    group_messages_by_api_round,
    preserve_tool_result_pairs,
    strip_images_from_messages,
    truncate_head_for_ptl_retry,
    build_post_compact_messages,
    compact_conversation,
    auto_compact_if_needed,
    compute_effective_threshold,
    should_auto_compact,
    get_compact_levels,
)


def test_default_config() -> None:
    config = DEFAULT_COMPACT_CONFIG
    assert config.compact_token_reserve == 13_000
    assert config.max_compact_streaming_retries == 2
    assert config.post_compact_max_files_to_restore == 5


def test_get_and_set_config() -> None:
    original = get_compact_config()
    assert original.compact_token_reserve == 13_000

    new_config = CompactConfig(
        compact_token_reserve=15000,
        max_compact_streaming_retries=3,
    )
    set_compact_config(new_config)

    updated = get_compact_config()
    assert updated.compact_token_reserve == 15_000
    assert updated.max_compact_streaming_retries == 3

    # Reset
    set_compact_config(DEFAULT_COMPACT_CONFIG)


def test_group_messages_by_api_round() -> None:
    # Create mock messages with assistant/user types and IDs
    messages = [
        _make_message("user", "msg-1", "Hello"),
        _make_message("assistant", "msg-2", "Hi there"),
        _make_message("user", "msg-3", "How are you?"),
        _make_message("assistant", "msg-4", "I'm fine"),
        _make_message("user", "msg-5", "Great"),
    ]

    groups = group_messages_by_api_round(messages)

    # All messages in one group since they share the same assistant ID sequence
    # (the algorithm groups by round-trip, not by individual messages)
    assert len(groups) >= 1
    # Total number of messages should be preserved
    total = sum(len(g) for g in groups)
    assert total == 5


def test_group_messages_single_round() -> None:
    # Single assistant message = single group
    messages = [
        _make_message("user", "msg-1", "Hello"),
        _make_message("assistant", "msg-2", "Hi there"),
    ]

    groups = group_messages_by_api_round(messages)
    assert len(groups) == 1


def test_preserve_tool_result_pairs_drops_orphans() -> None:
    messages = [
        _make_message("assistant", "a1", [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]),
        _make_message("user", "u1", [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]),
        _make_message("assistant", "a2", [{"type": "tool_use", "id": "t2", "name": "Bash", "input": {}}]),
        _make_message("user", "u2", "plain text"),
        _make_message("user", "u3", [{"type": "tool_result", "tool_use_id": "missing", "content": "orphan"}]),
    ]

    preserved = preserve_tool_result_pairs(messages)

    assert len(preserved) == 3
    assert preserved[0]["id"] == "a1"
    assert preserved[1]["id"] == "u1"
    assert preserved[2]["id"] == "u2"


def test_preserve_tool_result_pairs_keeps_balanced_pairs() -> None:
    messages = [
        _make_message("assistant", "a1", [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]),
        _make_message("user", "u1", [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]),
    ]

    preserved = preserve_tool_result_pairs(messages)

    assert preserved == messages


def test_strip_images_preserves_non_image_messages() -> None:
    messages = [
        _make_message("user", "msg-1", "Hello world"),
        _make_message("assistant", "msg-2", "Hi there"),
    ]

    stripped = strip_images_from_messages(messages)
    assert len(stripped) == 2
    assert stripped[0]["message"]["content"] == "Hello world"


def test_compaction_result_creation() -> None:
    result = CompactionResult(
        boundary_marker={"type": "system", "subtype": "compact_boundary"},
        summary_messages=[
            {"type": "user", "message": {"role": "user", "content": "Summary"}}
        ],
        messages_to_keep=[_make_message("assistant", "msg-2", "Recent response")],
        pre_compact_token_count=50000,
        post_compact_token_count=15000,
    )

    assert result.boundary_marker["subtype"] == "compact_boundary"
    assert len(result.summary_messages) == 1
    assert len(result.messages_to_keep) == 1
    assert result.pre_compact_token_count == 50000


def test_build_post_compact_messages() -> None:
    result = CompactionResult(
        boundary_marker={"type": "system", "subtype": "compact_boundary"},
        summary_messages=[
            {"type": "user", "message": {"role": "user", "content": "Summary"}}
        ],
        messages_to_keep=[
            {"type": "assistant", "message": {"id": "msg-2", "content": "Recent"}},
        ],
        attachments=[{"type": "attachment", "content": "file.txt"}],
        hook_results=[{"type": "hook_result", "content": "hook output"}],
    )

    messages = build_post_compact_messages(result)

    # Should be: boundary + summary + kept + attachments + hooks = 5
    assert len(messages) == 5


def test_compute_effective_threshold() -> None:
    threshold = compute_effective_threshold("claude-sonnet-4-20250514")

    assert threshold.effective_threshold == 200_000 - 13_000  # 187000
    assert threshold.context_window == 200_000
    assert threshold.reserve == 13_000


def test_should_auto_compact_not_needed() -> None:
    # 50K tokens on a 200K context should not trigger
    result = should_auto_compact(50000, "claude-sonnet-4-20250514")

    assert result.should_trigger is False
    assert result.reason is None


def test_should_auto_compact_warning_zone() -> None:
    # 150K tokens on a 200K context should be in warning zone
    result = should_auto_compact(150000, "claude-sonnet-4-20250514")

    assert result.should_trigger is False
    assert result.reason is not None
    assert result.reason.type == "warning"


def test_should_auto_compact_trigger() -> None:
    # 190K tokens on a 200K context should trigger
    result = should_auto_compact(190000, "claude-sonnet-4-20250514")

    assert result.should_trigger is True
    assert result.reason is not None
    assert result.reason.type == "auto"


def test_get_compact_levels() -> None:
    levels = get_compact_levels(100000, "claude-sonnet-4-20250514")

    assert "warning_threshold" in levels
    assert "error_threshold" in levels
    assert "blocking_threshold" in levels
    assert levels["current_tokens"] == 100000
    assert levels["context_window"] == 200_000


def test_truncate_head_for_ptl_retry() -> None:
    # Test with single message - should return None (nothing to truncate)
    single_msg = [_make_message("user", "msg-1", "Hello")]

    def estimator(msgs):
        return len(msgs) * 10

    result = truncate_head_for_ptl_retry(single_msg, None, estimator)
    # Single group can't be truncated
    assert result is None


def test_compact_conversation_validation() -> None:
    import asyncio

    # Empty messages should raise
    try:
        asyncio.run(compact_conversation([], lambda x: 0))
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not enough messages" in str(e).lower()


def _make_message(msg_type: str, msg_id: str, text: str, content_blocks=None):
    """Helper to create mock messages."""
    if content_blocks is None:
        content = text
    else:
        content = content_blocks

    return {
        "type": msg_type,
        "id": msg_id,
        "message": {
            "id": msg_id,
            "role": msg_type,
            "content": content,
        },
    }
