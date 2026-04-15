"""
Claude.ai rate limits types.

Types for rate limit tracking and Claude.ai quota management.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QuotaStatus(str, Enum):
    """Quota status."""
    ALLOWED = "allowed"
    ALLOWED_WARNING = "allowed_warning"
    REJECTED = "rejected"


class RateLimitType(str, Enum):
    """Type of rate limit."""
    FIVE_HOUR = "five_hour"
    SEVEN_DAY = "seven_day"
    SEVEN_DAY_OPUS = "seven_day_opus"
    SEVEN_DAY_SONNET = "seven_day_sonnet"
    OVERAGE = "overage"


class OverageDisabledReason(str, Enum):
    """Reason why overage is disabled."""
    OVERAGE_NOT_PROVISIONED = "overage_not_provisioned"
    ORG_LEVEL_DISABLED = "org_level_disabled"
    ORG_LEVEL_DISABLED_UNTIL = "org_level_disabled_until"
    OUT_OF_CREDITS = "out_of_credits"
    SEAT_TIER_LEVEL_DISABLED = "seat_tier_level_disabled"
    MEMBER_LEVEL_DISABLED = "member_level_disabled"
    SEAT_TIER_ZERO_CREDIT_LIMIT = "seat_tier_zero_credit_limit"
    GROUP_ZERO_CREDIT_LIMIT = "group_zero_credit_limit"
    MEMBER_ZERO_CREDIT_LIMIT = "member_zero_credit_limit"
    ORG_SERVICE_LEVEL_DISABLED = "org_service_level_disabled"
    ORG_SERVICE_ZERO_CREDIT_LIMIT = "org_service_zero_credit_limit"
    NO_LIMITS_CONFIGURED = "no_limits_configured"
    UNKNOWN = "unknown"


@dataclass
class RawWindowUtilization:
    """Raw per-window utilization from API response headers."""
    utilization: float  # 0-1 fraction
    resets_at: float  # unix epoch seconds


@dataclass
class RawUtilization:
    """Raw utilization data for all windows."""
    five_hour: RawWindowUtilization | None = None
    seven_day: RawWindowUtilization | None = None


@dataclass
class ClaudeAILimits:
    """
    Claude.ai rate limit state.

    Mirrors TS ClaudeAILimits type.
    """
    status: QuotaStatus = QuotaStatus.ALLOWED
    unified_rate_limit_fallback_available: bool = False
    resets_at: float | None = None
    rate_limit_type: RateLimitType | None = None
    utilization: float | None = None  # 0-1 fraction
    overage_status: QuotaStatus | None = None
    overage_resets_at: float | None = None
    overage_disabled_reason: OverageDisabledReason | None = None
    is_using_overage: bool = False
    surpassed_threshold: float | None = None


@dataclass
class RateLimitMessage:
    """Rate limit message for display."""
    message: str
    severity: str = "warning"  # "error" or "warning"


# Rate limit error message prefixes
RATE_LIMIT_ERROR_PREFIXES = [
    "You've hit your",
    "You've used",
    "You're now using extra usage",
    "You're close to",
    "You're out of extra usage",
]

# Display names for rate limit types
RATE_LIMIT_DISPLAY_NAMES = {
    RateLimitType.FIVE_HOUR: "session limit",
    RateLimitType.SEVEN_DAY: "weekly limit",
    RateLimitType.SEVEN_DAY_OPUS: "Opus limit",
    RateLimitType.SEVEN_DAY_SONNET: "Sonnet limit",
    RateLimitType.OVERAGE: "extra usage limit",
}


def get_rate_limit_display_name(rate_type: RateLimitType) -> str:
    """Get display name for a rate limit type."""
    return RATE_LIMIT_DISPLAY_NAMES.get(rate_type, rate_type.value)
