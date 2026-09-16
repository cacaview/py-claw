"""P2-5: tests for the minimal advisor mechanism.

Covers:
- /advisor subcommands reading/writing state.advisor_model
- the advisor review appended to a completed turn's response
- zero advisor calls when state.advisor_model is unset
- silent degradation on advisor timeout / exception / empty reply
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

# Import RuntimeState first to break circular import chain:
# tools/agent_tools.py -> query/engine.py -> tools/__init__.py -> tools/agent_tools.py
from py_claw.cli.runtime import RuntimeState  # noqa: F401
from py_claw.commands import CommandDefinition, CommandRegistry
from py_claw.query.backend import BackendTurnResult
from py_claw.query.engine import ExecutedTurn, QueryRuntime, PreparedTurn
from py_claw.schemas.common import SDKUserMessage
from py_claw.services.advisor import (
    ADVISOR_LABEL,
    build_review_prompt,
    format_review_block,
    run_review,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _turn(text: str) -> BackendTurnResult:
    return BackendTurnResult(assistant_text=text, stop_reason="end_turn")


class ScriptedBackend:
    """Query backend fake: records every call and delegates to a handler."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self.calls: list[tuple[PreparedTurn, Any]] = []

    def run_turn(self, prepared: PreparedTurn, context: Any) -> BackendTurnResult:
        self.calls.append((prepared, context))
        return self._handler(prepared, context)


class _FixedTurnExecutor:
    """Turn executor that always returns a fixed main-model answer."""

    def __init__(self, text: str) -> None:
        self._text = text

    def execute(self, prepared: PreparedTurn, context: Any) -> ExecutedTurn:
        return ExecutedTurn(assistant_text=self._text, stop_reason="end_turn")


def _user_message(text: str = "What is 2+2?") -> SDKUserMessage:
    return SDKUserMessage(
        type="user",
        message={"role": "user", "content": text},
        parent_tool_use_id=None,
    )


def _assistant_content(outputs: list[Any]) -> str:
    assistant = [o for o in outputs if getattr(o, "type", None) == "assistant"]
    assert len(assistant) == 1, f"expected exactly one assistant message, got {len(assistant)}"
    return assistant[0].message["content"]


# ---------------------------------------------------------------------------
# /advisor subcommands
# ---------------------------------------------------------------------------


def _run_advisor_command(arguments: str, state: RuntimeState) -> str:
    return CommandRegistry.build(skills=[]).execute(
        "advisor",
        arguments=arguments,
        state=state,
        settings=MagicMock(effective={}),
        session_id=None,
        transcript_size=0,
    ).output_text


class TestAdvisorCommand:
    def test_set_model_writes_state(self) -> None:
        state = RuntimeState()
        assert state.advisor_model is None

        out = _run_advisor_command("my-advisor-model", state)
        assert out == "Advisor set to my-advisor-model."
        assert state.advisor_model == "my-advisor-model"

    def test_set_model_normalizes_alias(self) -> None:
        state = RuntimeState()
        _run_advisor_command("opus", state)
        assert state.advisor_model == "opus-4-6-20251114"

    def test_status_shows_current_model(self) -> None:
        state = RuntimeState()
        state.advisor_model = "my-advisor-model"

        out = _run_advisor_command("status", state)
        assert out.startswith("Advisor: my-advisor-model\n")
        # status must not change state
        assert state.advisor_model == "my-advisor-model"

    def test_status_without_argument_shows_current_model(self) -> None:
        state = RuntimeState()
        state.advisor_model = "my-advisor-model"
        assert _run_advisor_command("", state).startswith("Advisor: my-advisor-model\n")

    def test_status_when_unset(self) -> None:
        state = RuntimeState()
        out = _run_advisor_command("status", state)
        assert "Advisor: not set" in out

    def test_off_clears_state(self) -> None:
        state = RuntimeState()
        state.advisor_model = "my-advisor-model"

        out = _run_advisor_command("off", state)
        assert out == "Advisor disabled (was my-advisor-model)."
        assert state.advisor_model is None

    def test_unset_clears_state(self) -> None:
        state = RuntimeState()
        state.advisor_model = "my-advisor-model"
        _run_advisor_command("unset", state)
        assert state.advisor_model is None

    def test_off_when_unset(self) -> None:
        state = RuntimeState()
        assert "already unset" in _run_advisor_command("off", state)

    def test_command_is_user_invocable(self) -> None:
        registry = CommandRegistry.build(skills=[])
        advisor = [c for c in registry.list() if c.name == "advisor"]
        assert len(advisor) == 1
        assert advisor[0].user_invocable is True
        names = [c["name"] for c in registry.slash_commands()]
        assert "advisor" in names


# ---------------------------------------------------------------------------
# Turn integration: advisor review appended to the response
# ---------------------------------------------------------------------------


class TestAdvisorTurnIntegration:
    def test_review_appended_after_main_response(self) -> None:
        """Advisor set: the turn output ends with an 'Advisor:' block."""
        backend = ScriptedBackend(
            lambda prepared, context: (
                _turn("LGTM") if prepared.model == "advisor-model" else _turn("Main answer.")
            )
        )
        state = RuntimeState()
        state.advisor_model = "advisor-model"
        state.query_backend = backend
        runtime = QueryRuntime(state=state)

        outputs = list(runtime.handle_user_message(_user_message()))

        assert _assistant_content(outputs) == "Main answer.\n\nAdvisor: LGTM"

        # The advisor call used the advisor model with an isolated prompt.
        advisor_calls = [(p, c) for p, c in backend.calls if p.model == "advisor-model"]
        assert len(advisor_calls) == 1
        prompt, context = advisor_calls[0]
        assert "What is 2+2?" in prompt.query_text
        assert "Main answer." in prompt.query_text
        assert context.transcript == []  # isolated review conversation
        # The main turn call is separate and carries the user request.
        main_calls = [(p, c) for p, c in backend.calls if p.model != "advisor-model"]
        assert len(main_calls) == 1
        assert main_calls[0][0].query_text == "What is 2+2?"

    def test_no_advisor_call_when_unset(self) -> None:
        """advisor_model unset: zero advisor API calls, output unchanged."""
        backend = ScriptedBackend(lambda prepared, context: _turn("SHOULD NOT BE CALLED"))
        state = RuntimeState()
        state.advisor_model = None
        state.query_backend = backend
        runtime = QueryRuntime(state=state, turn_executor=_FixedTurnExecutor("Main answer."))

        outputs = list(runtime.handle_user_message(_user_message()))

        assert backend.calls == []
        assert _assistant_content(outputs) == "Main answer."
        assert "Advisor:" not in _assistant_content(outputs)

    def test_advisor_timeout_degrades_silently(self, monkeypatch) -> None:
        """Advisor slower than the timeout: main response intact, no block."""
        def slow_handler(prepared: PreparedTurn, context: Any) -> BackendTurnResult:
            time.sleep(2.0)
            return _turn("LGTM")

        backend = ScriptedBackend(slow_handler)
        state = RuntimeState()
        state.advisor_model = "advisor-model"
        state.query_backend = backend
        runtime = QueryRuntime(state=state, turn_executor=_FixedTurnExecutor("Main answer."))
        monkeypatch.setattr("py_claw.services.advisor.ADVISOR_TIMEOUT_SECONDS", 0.2)

        started = time.monotonic()
        outputs = list(runtime.handle_user_message(_user_message()))  # must not raise
        elapsed = time.monotonic() - started

        assert _assistant_content(outputs) == "Main answer."
        assert "Advisor:" not in _assistant_content(outputs)
        # The turn was not blocked for the full (2s) review duration.
        assert elapsed < 2.0

    def test_advisor_exception_degrades_silently(self) -> None:
        """Advisor backend raising: main response intact, no block, no error."""
        def broken_handler(prepared: PreparedTurn, context: Any) -> BackendTurnResult:
            raise RuntimeError("advisor exploded")

        backend = ScriptedBackend(broken_handler)
        state = RuntimeState()
        state.advisor_model = "advisor-model"
        state.query_backend = backend
        runtime = QueryRuntime(state=state, turn_executor=_FixedTurnExecutor("Main answer."))

        outputs = list(runtime.handle_user_message(_user_message()))

        assert _assistant_content(outputs) == "Main answer."
        assert "Advisor:" not in _assistant_content(outputs)
        # No error result was emitted for the main turn.
        result = [o for o in outputs if getattr(o, "type", None) == "result"]
        assert len(result) == 1
        assert getattr(result[0], "is_error", False) is False

    def test_advisor_empty_reply_degrades_silently(self) -> None:
        backend = ScriptedBackend(lambda prepared, context: _turn("   "))
        state = RuntimeState()
        state.advisor_model = "advisor-model"
        state.query_backend = backend
        runtime = QueryRuntime(state=state, turn_executor=_FixedTurnExecutor("Main answer."))

        outputs = list(runtime.handle_user_message(_user_message()))

        assert _assistant_content(outputs) == "Main answer."


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


class TestAdvisorService:
    def test_build_review_prompt_contains_request_answer_and_instruction(self) -> None:
        prompt = build_review_prompt("What is 2+2?", "The answer is 4.")
        assert "What is 2+2?" in prompt
        assert "The answer is 4." in prompt
        assert "2-3 sentences" in prompt
        assert "LGTM" in prompt

    def test_format_review_block_prefix(self) -> None:
        assert format_review_block("LGTM") == f"{ADVISOR_LABEL} LGTM"
        assert format_review_block("  has a bug  ") == f"{ADVISOR_LABEL} has a bug"

    def test_run_review_returns_none_on_empty_inputs_without_calling_backend(self) -> None:
        backend = ScriptedBackend(lambda prepared, context: _turn("LGTM"))
        assert run_review(backend, advisor_model="m", query_text="", answer_text="a") is None
        assert run_review(backend, advisor_model="m", query_text="q", answer_text="") is None
        assert backend.calls == []

    def test_run_review_returns_none_when_backend_raises(self) -> None:
        def broken(prepared: PreparedTurn, context: Any) -> BackendTurnResult:
            raise RuntimeError("boom")

        backend = ScriptedBackend(broken)
        result = run_review(backend, advisor_model="m", query_text="q", answer_text="a", timeout=5.0)
        assert result is None

    def test_run_review_returns_review_text(self) -> None:
        backend = ScriptedBackend(lambda prepared, context: _turn("LGTM"))
        result = run_review(backend, advisor_model="m", query_text="q", answer_text="a", timeout=5.0)
        assert result == "LGTM"
        assert backend.calls[0][0].model == "m"
