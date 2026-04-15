"""
Mock Rate Limits service implementation.

Mocks rate limit headers for testing without hitting actual limits.
⚠️ WARNING: For internal testing/demo purposes only!
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class MockScenario(str, Enum):
    """Mock rate limit scenarios for testing."""
    NORMAL = "normal"
    SESSION_LIMIT_REACHED = "session-limit-reached"
    APPROACHING_WEEKLY_LIMIT = "approaching-weekly-limit"
    WEEKLY_LIMIT_REACHED = "weekly-limit-reached"
    OVERAGE_ACTIVE = "overage-active"
    OVERAGE_WARNING = "overage-warning"
    OVERAGE_EXHAUSTED = "overage-exhausted"
    OUT_OF_CREDITS = "out-of-credits"
    ORG_ZERO_CREDIT_LIMIT = "org-zero-credit-limit"
    ORG_SPEND_CAP_HIT = "org-spend-cap-hit"
    MEMBER_ZERO_CREDIT_LIMIT = "member-zero-credit-limit"
    SEAT_TIER_ZERO_CREDIT_LIMIT = "seat-tier-zero-credit-limit"
    OPUS_LIMIT = "opus-limit"
    OPUS_WARNING = "opus-warning"
    SONNET_LIMIT = "sonnet-limit"
    SONNET_WARNING = "sonnet-warning"
    FAST_MODE_LIMIT = "fast-mode-limit"
    FAST_MODE_SHORT_LIMIT = "fast-mode-short-limit"
    EXTRA_USAGE_REQUIRED = "extra-usage-required"
    CLEAR = "clear"


class MockHeaderKey(str, Enum):
    """Keys for mock headers."""
    STATUS = "status"
    RESET = "reset"
    CLAIM = "claim"
    OVERAGE_STATUS = "overage-status"
    OVERAGE_RESET = "overage-reset"
    OVERAGE_DISABLED_REASON = "overage-disabled-reason"
    FALLBACK = "fallback"
    FALLBACK_PERCENTAGE = "fallback-percentage"
    RETRY_AFTER = "retry-after"
    FIVE_H_UTILIZATION = "5h-utilization"
    FIVE_H_RESET = "5h-reset"
    FIVE_H_SURPASSED_THRESHOLD = "5h-surpassed-threshold"
    SEVEN_D_UTILIZATION = "7d-utilization"
    SEVEN_D_RESET = "7d-reset"
    SEVEN_D_SURPASSED_THRESHOLD = "7d-surpassed-threshold"


# Current mock scenario
_mock_scenario: MockScenario | None = None


def is_mock_rate_limits_enabled() -> bool:
    """Check if mock rate limits are enabled."""
    return _mock_scenario is not None and _mock_scenario != MockScenario.CLEAR


def set_mock_scenario(scenario: MockScenario | None) -> None:
    """
    Set the mock rate limit scenario.

    Args:
        scenario: The mock scenario to set, or None to disable mocking
    """
    global _mock_scenario
    _mock_scenario = scenario


def clear_mock_scenario() -> None:
    """Clear the mock scenario, disabling mocking."""
    global _mock_scenario
    _mock_scenario = MockScenario.CLEAR


@dataclass
class MockHeaders:
    """Container for mock rate limit headers."""
    anthropic_ratelimit_unified_status: str | None = None
    anthropic_ratelimit_unified_reset: str | None = None
    anthropic_ratelimit_unified_representative_claim: str | None = None
    anthropic_ratelimit_unified_overage_status: str | None = None
    anthropic_ratelimit_unified_overage_reset: str | None = None
    anthropic_ratelimit_unified_overage_disabled_reason: str | None = None
    anthropic_ratelimit_unified_fallback: str | None = None
    anthropic_ratelimit_unified_fallback_percentage: str | None = None
    retry_after: str | None = None
    anthropic_ratelimit_unified_5h_utilization: str | None = None
    anthropic_ratelimit_unified_5h_reset: str | None = None
    anthropic_ratelimit_unified_5h_surpassed_threshold: str | None = None
    anthropic_ratelimit_unified_7d_utilization: str | None = None
    anthropic_ratelimit_unified_7d_reset: str | None = None
    anthropic_ratelimit_unified_7d_surpassed_threshold: str | None = None
    anthropic_ratelimit_unified_overage_utilization: str | None = None
    anthropic_ratelimit_unified_overage_surpassed_threshold: str | None = None


def _get_mock_headers_for_scenario(scenario: MockScenario) -> MockHeaders:
    """Get mock headers for a specific scenario."""
    now = time.time()
    five_hour_reset = str(int(now + 5 * 60 * 60))
    seven_day_reset = str(int(now + 7 * 24 * 60 * 60))

    headers = MockHeaders()

    if scenario == MockScenario.NORMAL:
        headers.anthropic_ratelimit_unified_status = "allowed"
        return headers

    elif scenario == MockScenario.SESSION_LIMIT_REACHED:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_reset = five_hour_reset
        headers.anthropic_ratelimit_unified_representative_claim = "five_hour"
        headers.retry_after = "1800"
        return headers

    elif scenario == MockScenario.APPROACHING_WEEKLY_LIMIT:
        headers.anthropic_ratelimit_unified_status = "allowed_warning"
        headers.anthropic_ratelimit_unified_reset = seven_day_reset
        headers.anthropic_ratelimit_unified_representative_claim = "seven_day"
        headers.anthropic_ratelimit_unified_7d_utilization = "0.85"
        headers.anthropic_ratelimit_unified_7d_surpassed_threshold = "true"
        return headers

    elif scenario == MockScenario.WEEKLY_LIMIT_REACHED:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_reset = seven_day_reset
        headers.anthropic_ratelimit_unified_representative_claim = "seven_day"
        headers.retry_after = str(7 * 24 * 60 * 60)
        return headers

    elif scenario == MockScenario.OVERAGE_ACTIVE:
        headers.anthropic_ratelimit_unified_status = "allowed"
        headers.anthropic_ratelimit_unified_overage_status = "allowed"
        return headers

    elif scenario == MockScenario.OVERAGE_WARNING:
        headers.anthropic_ratelimit_unified_status = "allowed_warning"
        headers.anthropic_ratelimit_unified_overage_status = "allowed_warning"
        return headers

    elif scenario == MockScenario.OVERAGE_EXHAUSTED:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_reset = seven_day_reset
        headers.retry_after = str(7 * 24 * 60 * 60)
        return headers

    elif scenario == MockScenario.OUT_OF_CREDITS:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_disabled_reason = "out_of_credits"
        return headers

    elif scenario == MockScenario.ORG_ZERO_CREDIT_LIMIT:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_disabled_reason = "org_zero_credit_limit"
        return headers

    elif scenario == MockScenario.ORG_SPEND_CAP_HIT:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_disabled_reason = "org_spend_cap_hit"
        return headers

    elif scenario == MockScenario.MEMBER_ZERO_CREDIT_LIMIT:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_disabled_reason = "member_zero_credit_limit"
        return headers

    elif scenario == MockScenario.SEAT_TIER_ZERO_CREDIT_LIMIT:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_disabled_reason = "seat_tier_zero_credit_limit"
        return headers

    elif scenario == MockScenario.OPUS_LIMIT:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_representative_claim = "seven_day_opus"
        headers.anthropic_ratelimit_unified_reset = seven_day_reset
        return headers

    elif scenario == MockScenario.OPUS_WARNING:
        headers.anthropic_ratelimit_unified_status = "allowed_warning"
        headers.anthropic_ratelimit_unified_representative_claim = "seven_day_opus"
        return headers

    elif scenario == MockScenario.SONNET_LIMIT:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_representative_claim = "seven_day_sonnet"
        headers.anthropic_ratelimit_unified_reset = seven_day_reset
        return headers

    elif scenario == MockScenario.SONNET_WARNING:
        headers.anthropic_ratelimit_unified_status = "allowed_warning"
        headers.anthropic_ratelimit_unified_representative_claim = "seven_day_sonnet"
        return headers

    elif scenario == MockScenario.FAST_MODE_LIMIT:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_reset = five_hour_reset
        headers.anthropic_ratelimit_unified_representative_claim = "five_hour"
        return headers

    elif scenario == MockScenario.FAST_MODE_SHORT_LIMIT:
        headers.anthropic_ratelimit_unified_status = "rejected"
        headers.anthropic_ratelimit_unified_reset = five_hour_reset
        headers.anthropic_ratelimit_unified_representative_claim = "five_hour"
        return headers

    elif scenario == MockScenario.EXTRA_USAGE_REQUIRED:
        headers.anthropic_ratelimit_unified_status = "allowed"
        headers.anthropic_ratelimit_unified_overage_status = "rejected"
        headers.anthropic_ratelimit_unified_overage_disabled_reason = "extra_usage_required"
        return headers

    # Default - CLEAR or unknown
    return MockHeaders()


def get_mock_headers() -> dict[str, str]:
    """
    Get mock rate limit headers for the current scenario.

    Returns:
        Dict of header name to value mappings
    """
    if _mock_scenario is None or _mock_scenario == MockScenario.CLEAR:
        return {}

    headers = _get_mock_headers_for_scenario(_mock_scenario)
    result: dict[str, str] = {}

    # Convert dataclass to dict with header names
    if headers.anthropic_ratelimit_unified_status:
        result["anthropic-ratelimit-unified-status"] = headers.anthropic_ratelimit_unified_status
    if headers.anthropic_ratelimit_unified_reset:
        result["anthropic-ratelimit-unified-reset"] = headers.anthropic_ratelimit_unified_reset
    if headers.anthropic_ratelimit_unified_representative_claim:
        result["anthropic-ratelimit-unified-representative-claim"] = headers.anthropic_ratelimit_unified_representative_claim
    if headers.anthropic_ratelimit_unified_overage_status:
        result["anthropic-ratelimit-unified-overage-status"] = headers.anthropic_ratelimit_unified_overage_status
    if headers.anthropic_ratelimit_unified_overage_reset:
        result["anthropic-ratelimit-unified-overage-reset"] = headers.anthropic_ratelimit_unified_overage_reset
    if headers.anthropic_ratelimit_unified_overage_disabled_reason:
        result["anthropic-ratelimit-unified-overage-disabled-reason"] = headers.anthropic_ratelimit_unified_overage_disabled_reason
    if headers.anthropic_ratelimit_unified_fallback:
        result["anthropic-ratelimit-unified-fallback"] = headers.anthropic_ratelimit_unified_fallback
    if headers.anthropic_ratelimit_unified_fallback_percentage:
        result["anthropic-ratelimit-unified-fallback-percentage"] = headers.anthropic_ratelimit_unified_fallback_percentage
    if headers.retry_after:
        result["retry-after"] = headers.retry_after
    if headers.anthropic_ratelimit_unified_5h_utilization:
        result["anthropic-ratelimit-unified-5h-utilization"] = headers.anthropic_ratelimit_unified_5h_utilization
    if headers.anthropic_ratelimit_unified_5h_reset:
        result["anthropic-ratelimit-unified-5h-reset"] = headers.anthropic_ratelimit_unified_5h_reset
    if headers.anthropic_ratelimit_unified_5h_surpassed_threshold:
        result["anthropic-ratelimit-unified-5h-surpassed-threshold"] = headers.anthropic_ratelimit_unified_5h_surpassed_threshold
    if headers.anthropic_ratelimit_unified_7d_utilization:
        result["anthropic-ratelimit-unified-7d-utilization"] = headers.anthropic_ratelimit_unified_7d_utilization
    if headers.anthropic_ratelimit_unified_7d_reset:
        result["anthropic-ratelimit-unified-7d-reset"] = headers.anthropic_ratelimit_unified_7d_reset
    if headers.anthropic_ratelimit_unified_7d_surpassed_threshold:
        result["anthropic-ratelimit-unified-7d-surpassed-threshold"] = headers.anthropic_ratelimit_unified_7d_surpassed_threshold
    if headers.anthropic_ratelimit_unified_overage_utilization:
        result["anthropic-ratelimit-unified-overage-utilization"] = headers.anthropic_ratelimit_unified_overage_utilization
    if headers.anthropic_ratelimit_unified_overage_surpassed_threshold:
        result["anthropic-ratelimit-unified-overage-surpassed-threshold"] = headers.anthropic_ratelimit_unified_overage_surpassed_threshold

    return result
