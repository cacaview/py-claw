"""Tests for the /rewind command and QueryRuntime rewind API."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure src is on path (conftest.py does this too, but be explicit)
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from py_claw.cli.runtime import RuntimeState
from py_claw.schemas.common import SDKUserMessage


def _make_runtime():
    """Create a QueryRuntime with real state, avoiding import at module level."""
    from py_claw.query.engine import QueryRuntime

    state = RuntimeState()
    return QueryRuntime(state=state)


def _populate_transcript(rt, count: int) -> None:
    """Add dummy messages to the transcript."""
    for i in range(count):
        rt._transcript.append(
            SDKUserMessage(
                type="user",
                message=f"msg {i}",
                parent_tool_use_id="",
                uuid=f"uuid-{i}",
                session_id="test-session",
            )
        )


@pytest.fixture()
def runtime():
    return _make_runtime()


class TestRewindMessages:
    def test_rewind_messages_valid_count(self, runtime) -> None:
        _populate_transcript(runtime, 10)
        assert runtime.message_count() == 10

        success, message = runtime.rewind_messages(3)
        assert success is True
        assert "Rewound 3 messages" in message
        assert "(7 remaining)" in message
        assert runtime.message_count() == 7

    def test_rewind_messages_count_greater_than_history(self, runtime) -> None:
        _populate_transcript(runtime, 5)
        success, message = runtime.rewind_messages(10)
        assert success is False
        assert "Cannot rewind 10 messages" in message
        assert "only 5 messages in history" in message
        assert runtime.message_count() == 5

    def test_rewind_messages_count_zero(self, runtime) -> None:
        _populate_transcript(runtime, 5)
        success, message = runtime.rewind_messages(0)
        assert success is False
        assert "positive integer" in message
        assert runtime.message_count() == 5

    def test_rewind_messages_negative_count(self, runtime) -> None:
        _populate_transcript(runtime, 5)
        success, message = runtime.rewind_messages(-1)
        assert success is False
        assert "positive integer" in message

    def test_rewind_messages_exact_count(self, runtime) -> None:
        """Rewinding exactly N when N == len(transcript) should fail."""
        _populate_transcript(runtime, 3)
        success, message = runtime.rewind_messages(3)
        assert success is False
        assert "Cannot rewind 3 messages" in message

    def test_rewind_messages_removes_correct_messages(self, runtime) -> None:
        _populate_transcript(runtime, 5)
        runtime.rewind_messages(2)
        remaining = runtime.get_message_history()
        assert len(remaining) == 3
        last_msg = remaining[-1]
        assert hasattr(last_msg, "message")
        assert last_msg.message == "msg 2"

    def test_rewind_messages_updates_active_turn_state(self, runtime) -> None:
        from py_claw.query.engine import QueryTurnState, PreparedTurn

        _populate_transcript(runtime, 5)
        runtime._active_turn_state = QueryTurnState(
            session_id="test",
            prepared=PreparedTurn(),
            transcript=list(runtime._transcript),
        )
        runtime.rewind_messages(2)
        assert len(runtime._active_turn_state.transcript) == 3

    def test_rewind_messages_saves_session_state(self, runtime) -> None:
        _populate_transcript(runtime, 5)
        runtime._session_id = "test-session"
        runtime.rewind_messages(2)
        saved = runtime._saved_sessions.get("test-session")
        assert saved is not None
        assert len(saved.transcript) == 3


class TestMessageCount:
    def test_message_count_empty(self, runtime) -> None:
        assert runtime.message_count() == 0

    def test_message_count_populated(self, runtime) -> None:
        _populate_transcript(runtime, 7)
        assert runtime.message_count() == 7


class TestGetMessageHistory:
    def test_get_message_history_returns_copy(self, runtime) -> None:
        _populate_transcript(runtime, 3)
        history = runtime.get_message_history()
        assert len(history) == 3
        history.pop()
        assert runtime.message_count() == 3

    def test_get_message_history_empty(self, runtime) -> None:
        assert runtime.get_message_history() == []


class TestFileMutations:
    def test_record_file_mutation(self, runtime) -> None:
        runtime._turn_count = 5
        runtime._session_id = "sess-1"
        runtime.record_file_mutation("/path/to/file.py", "write", old_content="old", new_content="new")
        mutations = runtime.get_file_mutations()
        assert len(mutations) == 1
        m = mutations[0]
        assert m["path"] == "/path/to/file.py"
        assert m["operation"] == "write"
        assert m["old_content"] == "old"
        assert m["new_content"] == "new"
        assert m["turn_count"] == 5
        assert m["session_id"] == "sess-1"

    def test_get_file_mutations_no_filter(self, runtime) -> None:
        runtime._turn_count = 1
        runtime.record_file_mutation("/a", "create")
        runtime._turn_count = 3
        runtime.record_file_mutation("/b", "write")
        assert len(runtime.get_file_mutations()) == 2

    def test_get_file_mutations_filter_by_turn(self, runtime) -> None:
        runtime._turn_count = 1
        runtime.record_file_mutation("/a", "create")
        runtime._turn_count = 3
        runtime.record_file_mutation("/b", "write")
        runtime._turn_count = 5
        runtime.record_file_mutation("/c", "delete")
        filtered = runtime.get_file_mutations(since_turn=3)
        assert len(filtered) == 2
        assert all(m["turn_count"] >= 3 for m in filtered)

    def test_get_file_mutations_returns_copy(self, runtime) -> None:
        runtime._turn_count = 1
        runtime.record_file_mutation("/a", "create")
        mutations = runtime.get_file_mutations()
        mutations.clear()
        assert len(runtime.get_file_mutations()) == 1


class TestRewindCommandHandler:
    def test_rewind_handler_valid(self) -> None:
        from py_claw.commands import _rewind_handler, CommandDefinition
        from py_claw.settings.loader import SettingsLoadResult

        rt = _make_runtime()
        _populate_transcript(rt, 10)

        state = MagicMock()
        state.query_runtime = rt
        state.hook_runtime = MagicMock()
        state.cwd = "/tmp"

        settings = MagicMock(spec=SettingsLoadResult)
        result = _rewind_handler(
            MagicMock(spec=CommandDefinition),
            arguments="3",
            state=state,
            settings=settings,
            registry=MagicMock(),
            session_id="test",
            transcript_size=10,
        )
        assert "Rewound 3 messages" in result
        assert rt.message_count() == 7

    def test_rewind_handler_no_args(self) -> None:
        from py_claw.commands import _rewind_handler, CommandDefinition

        state = MagicMock()
        state.query_runtime = _make_runtime()

        result = _rewind_handler(
            MagicMock(spec=CommandDefinition),
            arguments="",
            state=state,
            settings=MagicMock(),
            registry=MagicMock(),
            session_id="test",
            transcript_size=0,
        )
        assert "Usage" in result

    def test_rewind_handler_invalid_number(self) -> None:
        from py_claw.commands import _rewind_handler, CommandDefinition

        state = MagicMock()
        state.query_runtime = _make_runtime()

        result = _rewind_handler(
            MagicMock(spec=CommandDefinition),
            arguments="abc",
            state=state,
            settings=MagicMock(),
            registry=MagicMock(),
            session_id="test",
            transcript_size=0,
        )
        assert "not a valid number" in result

    def test_rewind_handler_no_runtime(self) -> None:
        from py_claw.commands import _rewind_handler, CommandDefinition

        state = MagicMock()
        state.query_runtime = None

        result = _rewind_handler(
            MagicMock(spec=CommandDefinition),
            arguments="3",
            state=state,
            settings=MagicMock(),
            registry=MagicMock(),
            session_id="test",
            transcript_size=0,
        )
        assert "no active query runtime" in result

    def test_rewind_handler_count_too_large(self) -> None:
        from py_claw.commands import _rewind_handler, CommandDefinition

        rt = _make_runtime()
        _populate_transcript(rt, 3)

        state = MagicMock()
        state.query_runtime = rt

        result = _rewind_handler(
            MagicMock(spec=CommandDefinition),
            arguments="10",
            state=state,
            settings=MagicMock(),
            registry=MagicMock(),
            session_id="test",
            transcript_size=3,
        )
        assert "Error" in result

    def test_rewind_handler_fires_stop_hook(self) -> None:
        from py_claw.commands import _rewind_handler, CommandDefinition
        from py_claw.settings.loader import SettingsLoadResult

        rt = _make_runtime()
        _populate_transcript(rt, 5)

        hook_runtime = MagicMock()
        state = MagicMock()
        state.query_runtime = rt
        state.hook_runtime = hook_runtime
        state.cwd = "/tmp"

        settings = MagicMock(spec=SettingsLoadResult)
        _rewind_handler(
            MagicMock(spec=CommandDefinition),
            arguments="2",
            state=state,
            settings=settings,
            registry=MagicMock(),
            session_id="test",
            transcript_size=5,
        )
        hook_runtime.run_stop.assert_called_once()
        call_kwargs = hook_runtime.run_stop.call_args
        assert "Rewound 2 messages" in call_kwargs.kwargs["last_assistant_message"]

    def test_rewind_handler_hook_failure_does_not_block(self) -> None:
        from py_claw.commands import _rewind_handler, CommandDefinition
        from py_claw.settings.loader import SettingsLoadResult

        rt = _make_runtime()
        _populate_transcript(rt, 5)

        hook_runtime = MagicMock()
        hook_runtime.run_stop.side_effect = RuntimeError("hook crash")
        state = MagicMock()
        state.query_runtime = rt
        state.hook_runtime = hook_runtime
        state.cwd = "/tmp"

        settings = MagicMock(spec=SettingsLoadResult)
        result = _rewind_handler(
            MagicMock(spec=CommandDefinition),
            arguments="2",
            state=state,
            settings=settings,
            registry=MagicMock(),
            session_id="test",
            transcript_size=5,
        )
        assert "Rewound 2 messages" in result
        assert rt.message_count() == 3
