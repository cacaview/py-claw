"""Tests for auto-compact integration with the query engine."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from py_claw.services.compact.auto_trigger import (
    MODEL_CONTEXT_WINDOWS,
    _context_window_for_model,
    _PARTIAL_MODEL_CONTEXT_WINDOWS,
    should_auto_compact,
)
from py_claw.services.compact.types import CompactThresholdInfo


# ---------------------------------------------------------------------------
# MODEL_CONTEXT_WINDOWS updates
# ---------------------------------------------------------------------------


class TestModelContextWindows:
    """Verify that newer Claude models are present in the lookup."""

    @pytest.mark.parametrize(
        "model",
        [
            "claude-sonnet-4-6",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-fable-5",
        ],
    )
    def test_newer_models_present(self, model: str) -> None:
        assert model in MODEL_CONTEXT_WINDOWS
        assert MODEL_CONTEXT_WINDOWS[model] == 200_000

    def test_partial_name_match_sonnet(self) -> None:
        """Models containing 'sonnet' resolve to 200k."""
        assert _context_window_for_model("claude-sonnet-4-20260101") == 200_000

    def test_partial_name_match_opus(self) -> None:
        assert _context_window_for_model("claude-opus-4-20260101") == 200_000

    def test_partial_name_match_haiku(self) -> None:
        assert _context_window_for_model("claude-haiku-4-20260101") == 200_000

    def test_partial_name_match_fable(self) -> None:
        assert _context_window_for_model("some-claude-fable-5-beta") == 200_000

    def test_unknown_model_defaults_to_200k(self) -> None:
        """Unknown model strings default to 200 000."""
        assert _context_window_for_model("gpt-4o") == 200_000

    def test_exact_match_still_works(self) -> None:
        assert _context_window_for_model("claude-sonnet-4-20250514") == 200_000
        assert _context_window_for_model("claude-3-opus") == 200_000


# ---------------------------------------------------------------------------
# check_and_trigger_auto_compact
# ---------------------------------------------------------------------------


class TestCheckAndTriggerAutoCompact:
    """Unit tests for the integration function."""

    def _make_state(
        self,
        *,
        model: str = "claude-sonnet-4-20250514",
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        """Create a minimal RuntimeState-like object."""
        from dataclasses import dataclass, field

        @dataclass
        class FakeState:
            model: str | None = None
            session_input_tokens: int = 0
            session_output_tokens: int = 0

        return FakeState(
            model=model,
            session_input_tokens=input_tokens,
            session_output_tokens=output_tokens,
        )

    def test_low_tokens_no_trigger(self) -> None:
        from py_claw.services.compact.auto_compact_integration import check_and_trigger_auto_compact

        state = self._make_state(input_tokens=10_000, output_tokens=5_000)
        triggered, message = check_and_trigger_auto_compact(state)
        assert not triggered
        assert message == ""

    def test_high_tokens_triggers(self) -> None:
        from py_claw.services.compact.auto_compact_integration import check_and_trigger_auto_compact

        # 200k window - 13k reserve = 187k effective threshold
        # Use 188k to exceed it
        state = self._make_state(input_tokens=150_000, output_tokens=38_000)
        triggered, message = check_and_trigger_auto_compact(state)
        assert triggered
        assert "Auto-compact recommended" in message

    def test_custom_token_counter(self) -> None:
        from py_claw.services.compact.auto_compact_integration import check_and_trigger_auto_compact

        state = self._make_state(input_tokens=0, output_tokens=0)
        # Use a counter that reports high tokens
        triggered, message = check_and_trigger_auto_compact(
            state, token_counter=lambda: 190_000
        )
        assert triggered
        assert "190000" in message

    def test_missing_compact_service_returns_false(self) -> None:
        from py_claw.services.compact.auto_compact_integration import check_and_trigger_auto_compact

        state = self._make_state(input_tokens=150_000, output_tokens=50_000)
        with patch.dict("sys.modules", {"py_claw.services.compact.auto_trigger": None}):
            triggered, message = check_and_trigger_auto_compact(state)
            assert not triggered
            assert message == ""

    def test_default_model_used_when_none(self) -> None:
        from py_claw.services.compact.auto_compact_integration import check_and_trigger_auto_compact

        state = self._make_state(model=None, input_tokens=150_000, output_tokens=38_000)
        triggered, message = check_and_trigger_auto_compact(state)
        # Should still work using the default model
        assert triggered


# ---------------------------------------------------------------------------
# get_context_usage_percentage
# ---------------------------------------------------------------------------


class TestGetContextUsagePercentage:
    def _make_state(
        self,
        *,
        model: str = "claude-sonnet-4-20250514",
        input_tokens: int = 50_000,
        output_tokens: int = 50_000,
    ):
        from dataclasses import dataclass

        @dataclass
        class FakeState:
            model: str | None = None
            session_input_tokens: int = 0
            session_output_tokens: int = 0

        return FakeState(
            model=model,
            session_input_tokens=input_tokens,
            session_output_tokens=output_tokens,
        )

    def test_known_model(self) -> None:
        from py_claw.services.compact.auto_compact_integration import get_context_usage_percentage

        state = self._make_state(input_tokens=50_000, output_tokens=50_000)
        pct = get_context_usage_percentage(state)
        assert pct is not None
        assert pct == pytest.approx(50.0, abs=0.1)

    def test_unknown_model_returns_none(self) -> None:
        from py_claw.services.compact.auto_compact_integration import get_context_usage_percentage

        # Even unknown models now default to 200k, so this should return a value
        state = self._make_state(
            model="totally-unknown-model",
            input_tokens=50_000,
            output_tokens=50_000,
        )
        pct = get_context_usage_percentage(state)
        # With the new default of 200k, unknown models get 50%
        assert pct is not None
        assert pct == pytest.approx(50.0, abs=0.1)

    def test_zero_tokens(self) -> None:
        from py_claw.services.compact.auto_compact_integration import get_context_usage_percentage

        state = self._make_state(input_tokens=0, output_tokens=0)
        pct = get_context_usage_percentage(state)
        assert pct is not None
        assert pct == 0.0


# ---------------------------------------------------------------------------
# QueryRuntime._check_auto_compact
# ---------------------------------------------------------------------------


class TestQueryRuntimeCheckAutoCompact:
    """Test the _check_auto_compact method on QueryRuntime."""

    def test_no_trigger_appends_nothing(self) -> None:
        from py_claw.query.engine import QueryRuntime

        runtime = QueryRuntime()
        runtime.state.model = "claude-sonnet-4-20250514"
        runtime.state.session_input_tokens = 1_000
        runtime.state.session_output_tokens = 500
        tool_outputs: list = []
        result = runtime._check_auto_compact(tool_outputs=tool_outputs)
        assert result is False
        assert len(tool_outputs) == 0

    def test_trigger_appends_warning_message(self) -> None:
        from py_claw.query.engine import QueryRuntime

        runtime = QueryRuntime()
        runtime.state.model = "claude-sonnet-4-20250514"
        # 200k - 13k reserve = 187k threshold
        runtime.state.session_input_tokens = 160_000
        runtime.state.session_output_tokens = 30_000
        tool_outputs: list = []
        result = runtime._check_auto_compact(tool_outputs=tool_outputs)
        assert result is True
        assert len(tool_outputs) == 1
        msg = tool_outputs[0]
        assert msg.type == "system"
        assert msg.subtype == "local_command_output"
        assert "Auto-compact recommended" in msg.content

    def test_new_model_triggers_correctly(self) -> None:
        from py_claw.query.engine import QueryRuntime

        runtime = QueryRuntime()
        runtime.state.model = "claude-opus-4-8"
        runtime.state.session_input_tokens = 160_000
        runtime.state.session_output_tokens = 30_000
        tool_outputs: list = []
        result = runtime._check_auto_compact(tool_outputs=tool_outputs)
        assert result is True
        assert len(tool_outputs) == 1


# ---------------------------------------------------------------------------
# should_auto_compact direct tests
# ---------------------------------------------------------------------------


class TestShouldAutoCompact:
    def test_below_threshold(self) -> None:
        result = should_auto_compact(current_token_count=50_000, model="claude-sonnet-4-20250514")
        assert result.should_trigger is False

    def test_above_threshold(self) -> None:
        # 200k - 13k = 187k
        result = should_auto_compact(current_token_count=188_000, model="claude-sonnet-4-20250514")
        assert result.should_trigger is True
        assert result.threshold_info is not None
        assert result.threshold_info.effective_threshold == 187_000

    def test_warning_zone(self) -> None:
        # 80% of 187k = 149_600
        result = should_auto_compact(current_token_count=150_000, model="claude-sonnet-4-20250514")
        assert result.should_trigger is False
        assert result.reason is not None
        assert result.reason.type == "warning"

    def test_newer_model(self) -> None:
        result = should_auto_compact(current_token_count=188_000, model="claude-opus-4-8")
        assert result.should_trigger is True

    def test_partial_model_name(self) -> None:
        # Test that a model like "claude-sonnet-4-5-20260101" resolves correctly
        result = should_auto_compact(current_token_count=188_000, model="claude-sonnet-4-5-20260101")
        assert result.should_trigger is True
        assert result.threshold_info is not None
        assert result.threshold_info.context_window == 200_000
