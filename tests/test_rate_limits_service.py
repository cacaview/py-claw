"""
Tests for the rate limits service.
"""
from __future__ import annotations

import time

import pytest

from py_claw.services.rate_limits import (
    ClaudeAILimits,
    OverageDisabledReason,
    QuotaStatus,
    RateLimitMessage,
    RateLimitType,
    RawUtilization,
    RawWindowUtilization,
    RateLimitsService,
    get_rate_limits_service,
    is_rate_limit_error_message,
    get_rate_limit_message,
    get_rate_limit_display_name,
    RATE_LIMIT_ERROR_PREFIXES,
)


class TestRateLimitTypes:
    """Tests for rate limit types."""

    def test_quota_status_values(self) -> None:
        assert QuotaStatus.ALLOWED == "allowed"
        assert QuotaStatus.ALLOWED_WARNING == "allowed_warning"
        assert QuotaStatus.REJECTED == "rejected"

    def test_rate_limit_type_values(self) -> None:
        assert RateLimitType.FIVE_HOUR == "five_hour"
        assert RateLimitType.SEVEN_DAY == "seven_day"
        assert RateLimitType.SEVEN_DAY_OPUS == "seven_day_opus"
        assert RateLimitType.SEVEN_DAY_SONNET == "seven_day_sonnet"
        assert RateLimitType.OVERAGE == "overage"

    def test_overage_disabled_reason_values(self) -> None:
        assert OverageDisabledReason.OUT_OF_CREDITS == "out_of_credits"
        assert OverageDisabledReason.ORG_LEVEL_DISABLED == "org_level_disabled"


class TestClaudeAILimits:
    """Tests for ClaudeAILimits dataclass."""

    def test_defaults(self) -> None:
        limits = ClaudeAILimits()
        assert limits.status == QuotaStatus.ALLOWED
        assert limits.unified_rate_limit_fallback_available is False
        assert limits.is_using_overage is False

    def test_with_values(self) -> None:
        limits = ClaudeAILimits(
            status=QuotaStatus.REJECTED,
            rate_limit_type=RateLimitType.FIVE_HOUR,
            resets_at=time.time() + 3600,
            utilization=0.95,
        )
        assert limits.status == QuotaStatus.REJECTED
        assert limits.rate_limit_type == RateLimitType.FIVE_HOUR
        assert limits.utilization == 0.95


class TestRawUtilization:
    """Tests for RawUtilization."""

    def test_empty(self) -> None:
        raw = RawUtilization()
        assert raw.five_hour is None
        assert raw.seven_day is None

    def test_with_values(self) -> None:
        raw = RawUtilization(
            five_hour=RawWindowUtilization(utilization=0.5, resets_at=time.time() + 3600),
            seven_day=RawWindowUtilization(utilization=0.25, resets_at=time.time() + 86400),
        )
        assert raw.five_hour is not None
        assert raw.five_hour.utilization == 0.5
        assert raw.seven_day.utilization == 0.25


class TestRateLimitsService:
    """Tests for RateLimitsService."""

    def setup_method(self) -> None:
        import py_claw.services.rate_limits.service as svc_module
        svc_module._service = None

    def test_singleton(self) -> None:
        svc1 = get_rate_limits_service()
        svc2 = get_rate_limits_service()
        assert svc1 is svc2

    def test_initialize(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        assert svc.initialized

    def test_get_current_limits(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        limits = svc.get_current_limits()
        assert isinstance(limits, ClaudeAILimits)

    def test_update_limits(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        new_limits = ClaudeAILimits(
            status=QuotaStatus.ALLOWED_WARNING,
            rate_limit_type=RateLimitType.SEVEN_DAY,
            utilization=0.8,
        )
        svc.update_limits(new_limits)
        updated = svc.get_current_limits()
        assert updated.status == QuotaStatus.ALLOWED_WARNING
        assert updated.utilization == 0.8

    def test_update_from_headers(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        headers = {
            "anthropic-ratelimit-unified-5h-utilization": "0.5",
            "anthropic-ratelimit-unified-5h-reset": str(time.time() + 3600),
        }
        svc.update_from_headers(headers)
        raw = svc.get_raw_utilization()
        assert raw.five_hour is not None
        assert raw.five_hour.utilization == 0.5

    def test_is_rate_limit_error_message_true(self) -> None:
        svc = get_rate_limits_service()
        assert svc.is_rate_limit_error_message("You've hit your session limit") is True
        assert svc.is_rate_limit_error_message("You've used 75% of your weekly limit") is True
        assert svc.is_rate_limit_error_message("You're out of extra usage") is True

    def test_is_rate_limit_error_message_false(self) -> None:
        svc = get_rate_limits_service()
        assert svc.is_rate_limit_error_message("Hello, world!") is False
        assert svc.is_rate_limit_error_message("Something went wrong") is False

    def test_get_rate_limit_message_rejected(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        limits = ClaudeAILimits(
            status=QuotaStatus.REJECTED,
            rate_limit_type=RateLimitType.FIVE_HOUR,
            resets_at=time.time() + 3600,
        )
        msg = svc.get_rate_limit_message(limits)
        assert msg is not None
        assert msg.severity == "error"
        assert "session limit" in msg.message

    def test_get_rate_limit_message_warning_low_utilization(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        # Below 70% threshold, no warning
        limits = ClaudeAILimits(
            status=QuotaStatus.ALLOWED_WARNING,
            utilization=0.5,
        )
        msg = svc.get_rate_limit_message(limits)
        assert msg is None

    def test_get_rate_limit_message_warning_high_utilization(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        limits = ClaudeAILimits(
            status=QuotaStatus.ALLOWED_WARNING,
            rate_limit_type=RateLimitType.SEVEN_DAY,
            utilization=0.8,
            resets_at=time.time() + 86400,
        )
        msg = svc.get_rate_limit_message(limits)
        assert msg is not None
        assert msg.severity == "warning"
        assert "weekly limit" in msg.message

    def test_get_rate_limit_message_overage_warning(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        limits = ClaudeAILimits(
            status=QuotaStatus.ALLOWED,
            is_using_overage=True,
            overage_status=QuotaStatus.ALLOWED_WARNING,
        )
        msg = svc.get_rate_limit_message(limits)
        assert msg is not None
        assert msg.severity == "warning"
        assert "extra usage" in msg.message

    def test_get_rate_limit_error_message(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        limits = ClaudeAILimits(status=QuotaStatus.REJECTED)
        msg = svc.get_rate_limit_error_message(limits)
        assert msg is not None
        assert svc.is_rate_limit_error_message(msg) is True

    def test_get_rate_limit_error_message_none_for_warning(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        limits = ClaudeAILimits(status=QuotaStatus.ALLOWED_WARNING, utilization=0.8)
        msg = svc.get_rate_limit_error_message(limits)
        assert msg is None

    def test_get_using_overage_text(self) -> None:
        svc = get_rate_limits_service()
        svc.initialize()
        limits = ClaudeAILimits(
            rate_limit_type=RateLimitType.SEVEN_DAY,
            resets_at=time.time() + 86400,
        )
        text = svc.get_using_overage_text(limits)
        assert "extra usage" in text
        assert "weekly limit" in text


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self) -> None:
        import py_claw.services.rate_limits.service as svc_module
        svc_module._service = None

    def test_is_rate_limit_error_message(self) -> None:
        assert is_rate_limit_error_message("You've hit your limit") is True
        assert is_rate_limit_error_message("Hello") is False

    def test_get_rate_limit_display_name(self) -> None:
        assert get_rate_limit_display_name(RateLimitType.FIVE_HOUR) == "session limit"
        assert get_rate_limit_display_name(RateLimitType.SEVEN_DAY) == "weekly limit"
        assert get_rate_limit_display_name(RateLimitType.SEVEN_DAY_OPUS) == "Opus limit"
        assert get_rate_limit_display_name(RateLimitType.SEVEN_DAY_SONNET) == "Sonnet limit"
        assert get_rate_limit_display_name(RateLimitType.OVERAGE) == "extra usage limit"


class TestRateLimitMessage:
    """Tests for RateLimitMessage."""

    def test_defaults(self) -> None:
        msg = RateLimitMessage(message="Test")
        assert msg.message == "Test"
        assert msg.severity == "warning"

    def test_with_severity(self) -> None:
        msg = RateLimitMessage(message="Error!", severity="error")
        assert msg.severity == "error"


class TestRateLimitErrorPrefixes:
    """Tests for RATE_LIMIT_ERROR_PREFIXES constant."""

    def test_contains_expected_prefixes(self) -> None:
        assert "You've hit your" in RATE_LIMIT_ERROR_PREFIXES
        assert "You've used" in RATE_LIMIT_ERROR_PREFIXES
        assert "You're out of extra usage" in RATE_LIMIT_ERROR_PREFIXES
