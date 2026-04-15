"""
Claude AI Limits service implementation.

Tracks API rate limits, usage warnings, and throttling.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class QuotaStatus(str, Enum):
    """Quota status enumeration."""
    ALLOWED = "allowed"
    ALLOWED_WARNING = "allowed_warning"
    REJECTED = "rejected"


class RateLimitType(str, Enum):
    """Rate limit type enumeration."""
    FIVE_HOUR = "five_hour"
    SEVEN_DAY = "seven_day"
    SEVEN_DAY_OPUS = "seven_day_opus"
    SEVEN_DAY_SONNET = "seven_day_sonnet"
    OVERAGE = "overage"


# Rate limit display names
RATE_LIMIT_DISPLAY_NAMES: dict[RateLimitType, str] = {
    RateLimitType.FIVE_HOUR: "session limit",
    RateLimitType.SEVEN_DAY: "weekly limit",
    RateLimitType.SEVEN_DAY_OPUS: "Opus limit",
    RateLimitType.SEVEN_DAY_SONNET: "Sonnet limit",
    RateLimitType.OVERAGE: "extra usage limit",
}


def get_rate_limit_display_name(rate_limit_type: RateLimitType) -> str:
    """Get the display name for a rate limit type."""
    return RATE_LIMIT_DISPLAY_NAMES.get(rate_limit_type, rate_limit_type.value)


@dataclass
class EarlyWarningThreshold:
    """Early warning threshold configuration."""
    utilization: float  # 0-1 scale: trigger warning when usage >= this
    time_pct: float  # 0-1 scale: trigger warning when time elapsed <= this


@dataclass
class EarlyWarningConfig:
    """Early warning configuration for rate limits."""
    rate_limit_type: RateLimitType
    claim_abbrev: str  # '5h' or '7d'
    window_seconds: int
    thresholds: list[EarlyWarningThreshold]


# Early warning configurations in priority order
EARLY_WARNING_CONFIGS: list[EarlyWarningConfig] = [
    EarlyWarningConfig(
        rate_limit_type=RateLimitType.FIVE_HOUR,
        claim_abbrev="5h",
        window_seconds=5 * 60 * 60,
        thresholds=[
            EarlyWarningThreshold(utilization=0.9, time_pct=0.72),
        ],
    ),
    EarlyWarningConfig(
        rate_limit_type=RateLimitType.SEVEN_DAY,
        claim_abbrev="7d",
        window_seconds=7 * 24 * 60 * 60,
        thresholds=[
            EarlyWarningThreshold(utilization=0.75, time_pct=0.6),
            EarlyWarningThreshold(utilization=0.5, time_pct=0.35),
            EarlyWarningThreshold(utilization=0.25, time_pct=0.15),
        ],
    ),
]


# Maps claim abbreviations to rate limit types
EARLY_WARNING_CLAIM_MAP: dict[str, RateLimitType] = {
    "5h": RateLimitType.FIVE_HOUR,
    "7d": RateLimitType.SEVEN_DAY,
    "overage": RateLimitType.OVERAGE,
}


def _is_non_interactive_session() -> bool:
    """Check if running in non-interactive session."""
    return os.environ.get("CLAUDE_CODE_NON_INTERACTIVE", "").lower() in ("1", "true", "yes")


def should_process_rate_limits() -> bool:
    """
    Check if rate limits should be processed.

    Rate limits are processed for:
    - Claude.ai subscribers
    - Non-bare mode
    - Interactive sessions
    """
    # Skip in non-interactive sessions
    if _is_non_interactive_session():
        return False

    # Check if authenticated with Anthropic
    try:
        from py_claw.services.auth.auth import is_anthropic_auth_enabled, is_claude_ai_subscriber

        if not is_anthropic_auth_enabled():
            return False
        return is_claude_ai_subscriber()
    except ImportError:
        return False


def _compute_time_progress(resets_at: float, window_seconds: int) -> float:
    """
    Calculate what fraction of a time window has elapsed.

    Args:
        resets_at: Unix epoch timestamp in seconds when the limit resets
        window_seconds: Duration of the window in seconds

    Returns:
        Fraction (0-1) of the window that has elapsed
    """
    now_seconds = time.time()
    window_start = resets_at - window_seconds
    elapsed = now_seconds - window_start
    return max(0.0, min(1.0, elapsed / window_seconds))


@dataclass
class RateLimitHeaderInfo:
    """Parsed rate limit header information."""
    type: RateLimitType
    limit: int | None = None
    remaining: int | None = None
    resets_at: float | None = None
    surpassed: bool | None = None


def process_rate_limit_headers(headers: dict[str, str]) -> dict[RateLimitType, RateLimitHeaderInfo]:
    """
    Process rate limit headers from API response.

    Args:
        headers: Response headers dict

    Returns:
        Dict mapping rate limit type to header info
    """
    result: dict[RateLimitType, RateLimitHeaderInfo] = {}

    # Look for 5h (five hour) headers
    if "x-5h-limit" in headers:
        info = RateLimitHeaderInfo(type=RateLimitType.FIVE_HOUR)
        info.limit = _parse_int_header(headers.get("x-5h-limit"))
        info.remaining = _parse_int_header(headers.get("x-5h-remaining"))
        info.resets_at = _parse_float_header(headers.get("x-5h-reset-at"))
        info.surpassed = headers.get("x-5h-surpassed") == "true"
        result[RateLimitType.FIVE_HOUR] = info

    # Look for 7d (seven day) headers
    if "x-7d-limit" in headers:
        info = RateLimitHeaderInfo(type=RateLimitType.SEVEN_DAY)
        info.limit = _parse_int_header(headers.get("x-7d-limit"))
        info.remaining = _parse_int_header(headers.get("x-7d-remaining"))
        info.resets_at = _parse_float_header(headers.get("x-7d-reset-at"))
        info.surpassed = headers.get("x-7d-surpassed") == "true"
        result[RateLimitType.SEVEN_DAY] = info

    # Look for overage headers
    if "x-usage-limit" in headers:
        info = RateLimitHeaderInfo(type=RateLimitType.OVERAGE)
        info.limit = _parse_int_header(headers.get("x-usage-limit"))
        info.remaining = _parse_int_header(headers.get("x-usage-remaining"))
        result[RateLimitType.OVERAGE] = info

    return result


def _parse_int_header(value: str | None) -> int | None:
    """Parse integer from header value."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float_header(value: str | None) -> float | None:
    """Parse float from header value."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def get_early_warning_config(rate_limit_type: RateLimitType) -> EarlyWarningConfig | None:
    """Get the early warning configuration for a rate limit type."""
    for config in EARLY_WARNING_CONFIGS:
        if config.rate_limit_type == rate_limit_type:
            return config
    return None


def check_rate_limit_warning(
    rate_limit_type: RateLimitType,
    usage: float,
    resets_at: float | None,
) -> tuple[bool, str | None]:
    """
    Check if a rate limit warning should be shown.

    Args:
        rate_limit_type: Type of rate limit
        usage: Current usage (0-1 scale)
        resets_at: Unix timestamp when limit resets

    Returns:
        Tuple of (should_warn, warning_message)
    """
    config = get_early_warning_config(rate_limit_type)
    if not config:
        return False, None

    # Check if surpassed header was set (high confidence)
    # This is handled separately via headers

    # Check time-relative thresholds as fallback
    for threshold in config.thresholds:
        if usage >= threshold.utilization:
            if resets_at:
                time_pct = _compute_time_progress(resets_at, config.window_seconds)
                if time_pct <= threshold.time_pct:
                    return True, f"Approaching {config.claim_abbrev} limit"
            else:
                return True, f"Approaching {config.claim_abbrev} limit"

    return False, None
