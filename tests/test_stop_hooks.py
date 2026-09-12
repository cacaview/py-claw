"""Tests for stop hooks mechanism in the query engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Import RuntimeState first to break circular import chain:
# tools/agent_tools.py -> query/engine.py -> tools/__init__.py -> tools/agent_tools.py
from py_claw.cli.runtime import RuntimeState  # noqa: F401
from py_claw.hooks.runtime import HookDispatchResult, HookExecutionRecord
from py_claw.query.engine import ExecutedTurn, QueryRuntime
from py_claw.query.stop_hooks import StopHookResult, handle_stop_hooks


# ---------------------------------------------------------------------------
# StopHookResult dataclass tests
# ---------------------------------------------------------------------------


class TestStopHookResult:
    def test_defaults(self) -> None:
        result = StopHookResult()
        assert result.blocking_errors == []
        assert result.prevent_continuation is False
        assert result.additional_context is None
        assert result.updated_input is None

    def test_custom_values(self) -> None:
        result = StopHookResult(
            blocking_errors=["err1", "err2"],
            prevent_continuation=True,
            additional_context="extra",
            updated_input="new input",
        )
        assert result.blocking_errors == ["err1", "err2"]
        assert result.prevent_continuation is True
        assert result.additional_context == "extra"
        assert result.updated_input == "new input"

    def test_blocking_errors_mutable(self) -> None:
        result = StopHookResult()
        result.blocking_errors.append("error")
        assert result.blocking_errors == ["error"]


# ---------------------------------------------------------------------------
# handle_stop_hooks tests
# ---------------------------------------------------------------------------


def _make_state(
    *,
    hook_runtime: Any = None,
    cwd: str = "/tmp",
    home_dir: str | None = None,
) -> MagicMock:
    state = MagicMock()
    state.hook_runtime = hook_runtime
    state.cwd = cwd
    state.home_dir = home_dir
    return state


class TestHandleStopHooksNoRuntime:
    def test_returns_default_when_hook_runtime_is_none(self) -> None:
        state = _make_state(hook_runtime=None)
        result = handle_stop_hooks(state, session_id="s1")
        assert result.blocking_errors == []
        assert result.prevent_continuation is False
        assert result.additional_context is None
        assert result.updated_input is None


class TestHandleStopHooksWithMockRuntime:
    def test_run_stop_called_for_main_session(self) -> None:
        hook_runtime = MagicMock()
        hook_runtime.run_stop.return_value = HookDispatchResult()
        state = _make_state(hook_runtime=hook_runtime)

        with patch("py_claw.settings.loader.get_settings_with_sources") as mock_settings:
            mock_settings.return_value = MagicMock(settings=MagicMock())
            handle_stop_hooks(state, session_id="s1", last_assistant_message="hello")

        hook_runtime.run_stop.assert_called_once()
        hook_runtime.run_subagent_stop.assert_not_called()

    def test_run_subagent_stop_called_when_subagent_id_set(self) -> None:
        hook_runtime = MagicMock()
        hook_runtime.run_subagent_stop.return_value = HookDispatchResult()
        state = _make_state(hook_runtime=hook_runtime)

        with patch("py_claw.settings.loader.get_settings_with_sources") as mock_settings:
            mock_settings.return_value = MagicMock(settings=MagicMock())
            handle_stop_hooks(state, session_id="s1", subagent_id="agent-1")

        hook_runtime.run_subagent_stop.assert_called_once()
        hook_runtime.run_stop.assert_not_called()

    def test_blocking_error_from_nonzero_exit_code(self) -> None:
        execution = HookExecutionRecord(
            event="Stop",
            command="echo fail",
            exit_code=1,
            stdout="",
            stderr="something went wrong",
            structured_output=None,
        )
        hook_runtime = MagicMock()
        hook_runtime.run_stop.return_value = HookDispatchResult(executions=[execution])
        state = _make_state(hook_runtime=hook_runtime)

        with patch("py_claw.settings.loader.get_settings_with_sources") as mock_settings:
            mock_settings.return_value = MagicMock(settings=MagicMock())
            result = handle_stop_hooks(state, session_id="s1")

        assert result.blocking_errors == ["something went wrong"]
        assert result.prevent_continuation is False  # continue_ defaults True

    def test_prevent_continuation_when_continue_false(self) -> None:
        hook_runtime = MagicMock()
        hook_runtime.run_stop.return_value = HookDispatchResult(continue_=False)
        state = _make_state(hook_runtime=hook_runtime)

        with patch("py_claw.settings.loader.get_settings_with_sources") as mock_settings:
            mock_settings.return_value = MagicMock(settings=MagicMock())
            result = handle_stop_hooks(state, session_id="s1")

        assert result.prevent_continuation is True

    def test_additional_context_from_hook_content(self) -> None:
        hook_runtime = MagicMock()
        hook_runtime.run_stop.return_value = HookDispatchResult(
            content={"additionalContext": "extra info"}
        )
        state = _make_state(hook_runtime=hook_runtime)

        with patch("py_claw.settings.loader.get_settings_with_sources") as mock_settings:
            mock_settings.return_value = MagicMock(settings=MagicMock())
            result = handle_stop_hooks(state, session_id="s1")

        assert result.additional_context == "extra info"

    def test_no_additional_context_when_content_none(self) -> None:
        hook_runtime = MagicMock()
        hook_runtime.run_stop.return_value = HookDispatchResult(content=None)
        state = _make_state(hook_runtime=hook_runtime)

        with patch("py_claw.settings.loader.get_settings_with_sources") as mock_settings:
            mock_settings.return_value = MagicMock(settings=MagicMock())
            result = handle_stop_hooks(state, session_id="s1")

        assert result.additional_context is None

    def test_blocking_error_from_stdout_when_stderr_empty(self) -> None:
        execution = HookExecutionRecord(
            event="Stop",
            command="cmd",
            exit_code=2,
            stdout="output message",
            stderr="",
            structured_output=None,
        )
        hook_runtime = MagicMock()
        hook_runtime.run_stop.return_value = HookDispatchResult(executions=[execution])
        state = _make_state(hook_runtime=hook_runtime)

        with patch("py_claw.settings.loader.get_settings_with_sources") as mock_settings:
            mock_settings.return_value = MagicMock(settings=MagicMock())
            result = handle_stop_hooks(state, session_id="s1")

        assert result.blocking_errors == ["output message"]

    def test_blocking_error_generic_when_no_output(self) -> None:
        execution = HookExecutionRecord(
            event="Stop",
            command="cmd",
            exit_code=5,
            stdout="",
            stderr="",
            structured_output=None,
        )
        hook_runtime = MagicMock()
        hook_runtime.run_stop.return_value = HookDispatchResult(executions=[execution])
        state = _make_state(hook_runtime=hook_runtime)

        with patch("py_claw.settings.loader.get_settings_with_sources") as mock_settings:
            mock_settings.return_value = MagicMock(settings=MagicMock())
            result = handle_stop_hooks(state, session_id="s1")

        assert len(result.blocking_errors) == 1
        assert "exit code 5" in result.blocking_errors[0]


# ---------------------------------------------------------------------------
# QueryRuntime._run_stop_hooks tests
# ---------------------------------------------------------------------------


class TestQueryRuntimeRunStopHooks:
    def test_returns_default_on_exception(self) -> None:
        """_run_stop_hooks should catch exceptions and return a safe default."""
        runtime = QueryRuntime()

        with patch("py_claw.query.stop_hooks.handle_stop_hooks", side_effect=RuntimeError("boom")):
            result = runtime._run_stop_hooks(
                ExecutedTurn(assistant_text="hi"),
                session_id="s1",
            )

        assert isinstance(result, StopHookResult)
        assert result.blocking_errors == []
        assert result.prevent_continuation is False

    def test_delegates_to_handle_stop_hooks(self) -> None:
        runtime = QueryRuntime()
        expected = StopHookResult(additional_context="ctx")

        with patch("py_claw.query.stop_hooks.handle_stop_hooks", return_value=expected) as mock_fn:
            result = runtime._run_stop_hooks(
                ExecutedTurn(assistant_text="hello world"),
                session_id="s1",
            )

        assert result is expected
        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args
        assert call_kwargs[1]["session_id"] == "s1"
        assert call_kwargs[1]["last_assistant_message"] == "hello world"
        assert call_kwargs[1]["subagent_id"] is None

    def test_truncates_long_assistant_text(self) -> None:
        runtime = QueryRuntime()
        long_text = "x" * 5000

        with patch("py_claw.query.stop_hooks.handle_stop_hooks") as mock_fn:
            mock_fn.return_value = StopHookResult()
            runtime._run_stop_hooks(
                ExecutedTurn(assistant_text=long_text),
                session_id="s1",
            )

        call_kwargs = mock_fn.call_args[1]
        assert len(call_kwargs["last_assistant_message"]) == 2000

    def test_passes_subagent_id(self) -> None:
        runtime = QueryRuntime()

        with patch("py_claw.query.stop_hooks.handle_stop_hooks") as mock_fn:
            mock_fn.return_value = StopHookResult()
            runtime._run_stop_hooks(
                ExecutedTurn(assistant_text=""),
                session_id="s1",
                subagent_id="agent-42",
            )

        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["subagent_id"] == "agent-42"
