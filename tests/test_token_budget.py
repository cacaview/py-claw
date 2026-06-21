"""Tests for token budget enforcement in the query engine."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from py_claw.cli.runtime import RuntimeState
from py_claw.query.engine import ExecutedTurn, QueryRuntime


class TestCheckBudgetAndMaybeCompact:
    """Test _check_budget_and_maybe_compact method."""

    def _make_runtime(self, *, cost_budget=None, token_budget=None, cost=0.0, input_tokens=0, output_tokens=0):
        runtime = QueryRuntime()
        runtime.state.cost_budget_usd = cost_budget
        runtime.state.token_budget = token_budget
        runtime.state.session_cost_usd = cost
        runtime.state.session_input_tokens = input_tokens
        runtime.state.session_output_tokens = output_tokens
        return runtime

    def _make_executed(self, cost=0.0):
        return ExecutedTurn(
            assistant_text="test",
            stop_reason="end_turn",
            total_cost_usd=cost,
            usage={},
            model_usage={},
        )

    def test_no_budget_returns_none(self) -> None:
        runtime = self._make_runtime()
        executed = self._make_executed()
        result = runtime._check_budget_and_maybe_compact(executed, tool_outputs=[])
        assert result is None

    def test_cost_budget_not_exceeded(self) -> None:
        runtime = self._make_runtime(cost_budget=10.0, cost=5.0)
        executed = self._make_executed(cost=5.0)
        result = runtime._check_budget_and_maybe_compact(executed, tool_outputs=[])
        assert result is None

    def test_cost_budget_exceeded(self) -> None:
        runtime = self._make_runtime(cost_budget=10.0, cost=15.0)
        executed = self._make_executed(cost=15.0)
        result = runtime._check_budget_and_maybe_compact(executed, tool_outputs=[])
        assert result is not None
        assert result.stop_reason == "budget_exceeded"
        assert result.tool_calls == []

    def test_token_budget_not_exceeded(self) -> None:
        runtime = self._make_runtime(token_budget=100_000, input_tokens=50_000, output_tokens=30_000)
        executed = self._make_executed()
        result = runtime._check_budget_and_maybe_compact(executed, tool_outputs=[])
        assert result is None

    def test_token_budget_exceeded(self) -> None:
        runtime = self._make_runtime(token_budget=100_000, input_tokens=80_000, output_tokens=30_000)
        executed = self._make_executed()
        result = runtime._check_budget_and_maybe_compact(executed, tool_outputs=[])
        assert result is not None
        assert result.stop_reason == "budget_exceeded"
        assert "budget" in result.assistant_text.lower() or "Budget" in result.assistant_text

    def test_budget_exceeded_preserves_usage(self) -> None:
        usage = {"inputTokens": 1000, "outputTokens": 500}
        runtime = self._make_runtime(cost_budget=1.0, cost=5.0)
        executed = ExecutedTurn(
            assistant_text="test",
            stop_reason="end_turn",
            total_cost_usd=5.0,
            usage=usage,
            model_usage={},
        )
        result = runtime._check_budget_and_maybe_compact(executed, tool_outputs=[])
        assert result is not None
        assert result.usage == usage

    def test_budget_exceeded_preserves_cost(self) -> None:
        runtime = self._make_runtime(cost_budget=1.0, cost=5.0)
        executed = self._make_executed(cost=5.0)
        result = runtime._check_budget_and_maybe_compact(executed, tool_outputs=[])
        assert result is not None
        assert result.total_cost_usd == 5.0


class TestBuildBudgetWarningMessage:
    """Test _build_budget_warning_message method."""

    def test_basic_warning(self) -> None:
        runtime = QueryRuntime()
        runtime._session_id = "test-session"
        msg = runtime._build_budget_warning_message("Cost limit exceeded")
        assert msg is not None
        assert msg.type == "system"
        assert "Cost limit exceeded" in msg.content

    def test_auto_compacting_suffix(self) -> None:
        runtime = QueryRuntime()
        runtime._session_id = "test-session"
        msg = runtime._build_budget_warning_message("Token limit", auto_compacting=True)
        assert msg is not None
        assert "Auto-compacting" in msg.content

    def test_no_auto_compacting_suffix(self) -> None:
        runtime = QueryRuntime()
        runtime._session_id = "test-session"
        msg = runtime._build_budget_warning_message("Token limit", auto_compacting=False)
        assert msg is not None
        assert "Auto-compacting" not in msg.content


class TestRuntimeStateBudgetFields:
    """Test RuntimeState budget-related fields."""

    def test_default_budget_fields(self) -> None:
        state = RuntimeState()
        assert state.cost_budget_usd is None
        assert state.token_budget is None
        assert state.session_cost_usd == 0.0
        assert state.session_input_tokens == 0
        assert state.session_output_tokens == 0

    def test_budget_can_be_set(self) -> None:
        state = RuntimeState()
        state.cost_budget_usd = 10.0
        state.token_budget = 200_000
        assert state.cost_budget_usd == 10.0
        assert state.token_budget == 200_000
