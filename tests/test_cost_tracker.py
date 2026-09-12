from __future__ import annotations

import pytest

from py_claw.cli.runtime import RuntimeState
from py_claw.services.cost_tracker import (
    DEFAULT_PRICING,
    MODEL_PRICING,
    accumulate_session_cost,
    calculate_cost,
    check_budget_exceeded,
    format_cost_report,
)


class TestCalculateCost:
    """Tests for calculate_cost function."""

    def test_basic_input_output(self) -> None:
        """Calculate cost with input and output tokens only."""
        cost = calculate_cost(
            "claude-sonnet-4-20250514",
            input_tokens=1_000_000,
            output_tokens=500_000,
        )
        # Sonnet: $3/M input, $15/M output
        expected = 3.0 + 7.5
        assert abs(cost - expected) < 0.0001

    def test_with_cache_tokens(self) -> None:
        """Calculate cost with cache tokens."""
        cost = calculate_cost(
            "claude-sonnet-4-20250514",
            input_tokens=100_000,
            output_tokens=50_000,
            cache_read=200_000,
            cache_creation=100_000,
        )
        # Sonnet: $3/M input, $15/M output, $0.3/M cache_read, $3.75/M cache_creation
        expected = 0.3 + 0.75 + 0.06 + 0.375
        assert abs(cost - expected) < 0.0001

    def test_opus_pricing(self) -> None:
        """Verify Opus pricing."""
        cost = calculate_cost(
            "claude-opus-4-20250514",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Opus: $15/M input, $75/M output
        expected = 15.0 + 75.0
        assert abs(cost - expected) < 0.0001

    def test_haiku_pricing(self) -> None:
        """Verify Haiku pricing."""
        cost = calculate_cost(
            "claude-haiku-3-5-20241022",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Haiku: $0.80/M input, $4/M output
        expected = 0.80 + 4.0
        assert abs(cost - expected) < 0.0001

    def test_unknown_model_uses_default(self) -> None:
        """Unknown models should use default pricing."""
        cost = calculate_cost(
            "some-unknown-model",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        expected = DEFAULT_PRICING["input"] + DEFAULT_PRICING["output"]
        assert abs(cost - expected) < 0.0001

    def test_partial_model_name_match(self) -> None:
        """Partial model names should match."""
        cost = calculate_cost(
            "claude-sonnet-4-20250514-custom",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        expected = 3.0  # Sonnet input pricing
        assert abs(cost - expected) < 0.0001

    def test_zero_tokens(self) -> None:
        """Zero tokens should return zero cost."""
        cost = calculate_cost("claude-sonnet-4-20250514", 0, 0, 0, 0)
        assert cost == 0.0

    def test_pricing_table_completeness(self) -> None:
        """Verify pricing table has all required fields."""
        for model, pricing in MODEL_PRICING.items():
            assert "input" in pricing, f"{model} missing 'input'"
            assert "output" in pricing, f"{model} missing 'output'"
            assert "cache_read" in pricing, f"{model} missing 'cache_read'"
            assert "cache_creation" in pricing, f"{model} missing 'cache_creation'"


class TestAccumulateSessionCost:
    """Tests for accumulate_session_cost function."""

    def test_basic_accumulation(self) -> None:
        """Verify basic cost accumulation."""
        state = RuntimeState()
        usage = {
            "inputTokens": 1000,
            "outputTokens": 500,
            "cacheReadInputTokens": 200,
            "cacheCreationInputTokens": 100,
        }
        model_usage = {}
        accumulate_session_cost(state, usage, model_usage, 0.05, 1500.0)

        assert state.session_cost_usd == 0.05
        assert state.session_input_tokens == 1000
        assert state.session_output_tokens == 500
        assert state.session_cache_read_tokens == 200
        assert state.session_cache_creation_tokens == 100
        assert state.session_api_duration_ms == 1500.0

    def test_multiple_accumulations(self) -> None:
        """Verify accumulation across multiple calls."""
        state = RuntimeState()

        usage1 = {"inputTokens": 1000, "outputTokens": 500}
        accumulate_session_cost(state, usage1, {}, 0.05, 1000.0)

        usage2 = {"inputTokens": 2000, "outputTokens": 1000}
        accumulate_session_cost(state, usage2, {}, 0.10, 2000.0)

        assert abs(state.session_cost_usd - 0.15) < 1e-10
        assert state.session_input_tokens == 3000
        assert state.session_output_tokens == 1500
        assert state.session_api_duration_ms == 3000.0

    def test_missing_fields_defaults_to_zero(self) -> None:
        """Missing usage fields should default to zero."""
        state = RuntimeState()
        accumulate_session_cost(state, {}, {}, 0.0, 0.0)

        assert state.session_input_tokens == 0
        assert state.session_output_tokens == 0
        assert state.session_cache_read_tokens == 0
        assert state.session_cache_creation_tokens == 0


class TestFormatCostReport:
    """Tests for format_cost_report function."""

    def test_basic_report(self) -> None:
        """Verify basic report format."""
        state = RuntimeState()
        state.session_cost_usd = 1.2345
        state.session_input_tokens = 50000
        state.session_output_tokens = 25000
        state.session_cache_read_tokens = 10000
        state.session_cache_creation_tokens = 5000
        state.session_api_duration_ms = 3500.0
        state.session_turn_count = 5

        report = format_cost_report(state)

        assert "Session Cost Report" in report
        assert "$1.2345" in report
        assert "50,000" in report
        assert "25,000" in report
        assert "10,000" in report
        assert "5,000" in report
        assert "90,000" in report  # total
        assert "3500ms" in report
        assert "5" in report

    def test_report_with_budgets(self) -> None:
        """Verify budget section in report."""
        state = RuntimeState()
        state.session_cost_usd = 0.50
        state.cost_budget_usd = 10.0
        state.token_budget = 1_000_000
        state.session_input_tokens = 100_000
        state.session_output_tokens = 50_000

        report = format_cost_report(state)

        assert "Budget:" in report
        assert "$10.00" in report
        assert "$9.5000" in report  # remaining
        assert "1,000,000" in report
        assert "850,000" in report  # token remaining

    def test_report_without_budgets(self) -> None:
        """Report should work without budgets set."""
        state = RuntimeState()
        report = format_cost_report(state)

        assert "Session Cost Report" in report
        assert "Budget:" not in report

    def test_zero_state(self) -> None:
        """Report should work with zero values."""
        state = RuntimeState()
        report = format_cost_report(state)

        assert "$0.0000" in report
        assert "0" in report


class TestCheckBudgetExceeded:
    """Tests for check_budget_exceeded function."""

    def test_no_budget_set(self) -> None:
        """No budget should return not exceeded."""
        state = RuntimeState()
        exceeded, reason = check_budget_exceeded(state)
        assert not exceeded
        assert reason == ""

    def test_cost_budget_not_exceeded(self) -> None:
        """Cost under budget should return not exceeded."""
        state = RuntimeState()
        state.session_cost_usd = 5.0
        state.cost_budget_usd = 10.0

        exceeded, reason = check_budget_exceeded(state)
        assert not exceeded
        assert reason == ""

    def test_cost_budget_exceeded(self) -> None:
        """Cost over budget should return exceeded."""
        state = RuntimeState()
        state.session_cost_usd = 15.0
        state.cost_budget_usd = 10.0

        exceeded, reason = check_budget_exceeded(state)
        assert exceeded
        assert "Cost budget exceeded" in reason
        assert "$15.0000" in reason
        assert "$10.00" in reason

    def test_token_budget_not_exceeded(self) -> None:
        """Tokens under budget should return not exceeded."""
        state = RuntimeState()
        state.session_input_tokens = 50000
        state.session_output_tokens = 25000
        state.token_budget = 100_000

        exceeded, reason = check_budget_exceeded(state)
        assert not exceeded

    def test_token_budget_exceeded(self) -> None:
        """Tokens over budget should return exceeded."""
        state = RuntimeState()
        state.session_input_tokens = 80000
        state.session_output_tokens = 30000
        state.token_budget = 100_000

        exceeded, reason = check_budget_exceeded(state)
        assert exceeded
        assert "Token budget exceeded" in reason
        assert "110,000" in reason
        assert "100,000" in reason

    def test_both_budgets_exceeded(self) -> None:
        """Should report cost budget first if both exceeded."""
        state = RuntimeState()
        state.session_cost_usd = 15.0
        state.cost_budget_usd = 10.0
        state.session_input_tokens = 80000
        state.session_output_tokens = 30000
        state.token_budget = 100_000

        exceeded, reason = check_budget_exceeded(state)
        assert exceeded
        # Cost check happens first
        assert "Cost budget exceeded" in reason


class TestRuntimeStateFields:
    """Tests for RuntimeState cost tracking fields."""

    def test_default_values(self) -> None:
        """Verify default values for new fields."""
        state = RuntimeState()

        assert state.session_cost_usd == 0.0
        assert state.session_input_tokens == 0
        assert state.session_output_tokens == 0
        assert state.session_cache_read_tokens == 0
        assert state.session_cache_creation_tokens == 0
        assert state.session_api_duration_ms == 0.0
        assert state.session_turn_count == 0
        assert state.cost_budget_usd is None
        assert state.token_budget is None

    def test_budget_initialization(self) -> None:
        """Verify budgets can be set during initialization."""
        state = RuntimeState(cost_budget_usd=100.0, token_budget=1_000_000)

        assert state.cost_budget_usd == 100.0
        assert state.token_budget == 1_000_000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
