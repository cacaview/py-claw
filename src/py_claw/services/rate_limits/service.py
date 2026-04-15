"""
Claude.ai rate limits service.

Centralized rate limit tracking and message generation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .types import (
    ClaudeAILimits,
    OverageDisabledReason,
    QuotaStatus,
    RateLimitMessage,
    RateLimitType,
    RATE_LIMIT_DISPLAY_NAMES,
    RATE_LIMIT_ERROR_PREFIXES,
    RawUtilization,
    RawWindowUtilization,
    get_rate_limit_display_name,
)


@dataclass
class EarlyWarningThreshold:
    """Early warning threshold configuration."""
    utilization: float  # 0-1 scale: trigger when usage >= this
    time_pct: float  # 0-1 scale: trigger when time elapsed <= this


# Early warning configurations in priority order
EARLY_WARNING_CONFIGS = [
    {
        "rate_limit_type": RateLimitType.FIVE_HOUR,
        "window_seconds": 5 * 60 * 60,
        "thresholds": [
            EarlyWarningThreshold(utilization=0.9, time_pct=0.72),
        ],
    },
    {
        "rate_limit_type": RateLimitType.SEVEN_DAY,
        "window_seconds": 7 * 24 * 60 * 60,
        "thresholds": [
            EarlyWarningThreshold(utilization=0.75, time_pct=0.6),
            EarlyWarningThreshold(utilization=0.5, time_pct=0.35),
            EarlyWarningThreshold(utilization=0.25, time_pct=0.15),
        ],
    },
]

# Maps claim abbreviations to rate limit types
EARLY_WARNING_CLAIM_MAP = {
    "5h": RateLimitType.FIVE_HOUR,
    "7d": RateLimitType.SEVEN_DAY,
    "overage": RateLimitType.OVERAGE,
}


class RateLimitsService:
    """
    Service for tracking Claude.ai rate limits and generating messages.

    Provides:
    - Current limit state tracking
    - Rate limit message generation
    - Raw utilization tracking from API headers
    - Early warning detection
    """

    def __init__(self) -> None:
        self._current_limits = ClaudeAILimits()
        self._raw_utilization = RawUtilization()
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        """Initialize the rate limits service."""
        self._initialized = True

    def get_current_limits(self) -> ClaudeAILimits:
        """Get current rate limit state."""
        return self._current_limits

    def update_limits(self, limits: ClaudeAILimits) -> None:
        """Update current rate limit state."""
        self._current_limits = limits

    def update_from_headers(self, headers: dict[str, str]) -> None:
        """
        Update raw utilization from API response headers.

        Args:
            headers: Dict of response headers
        """
        for key, abbrev in [("five_hour", "5h"), ("seven_day", "7d")]:
            util_header = f"anthropic-ratelimit-unified-{abbrev}-utilization"
            reset_header = f"anthropic-ratelimit-unified-{abbrev}-reset"

            util_val = headers.get(util_header)
            reset_val = headers.get(reset_header)

            if util_val is not None and reset_val is not None:
                try:
                    raw = RawWindowUtilization(
                        utilization=float(util_val),
                        resets_at=float(reset_val),
                    )
                    if key == "five_hour":
                        self._raw_utilization.five_hour = raw
                    else:
                        self._raw_utilization.seven_day = raw
                except ValueError:
                    pass

    def get_raw_utilization(self) -> RawUtilization:
        """Get raw utilization data."""
        return self._raw_utilization

    def is_rate_limit_error_message(self, text: str) -> bool:
        """Check if a message is a rate limit error."""
        return any(text.startswith(prefix) for prefix in RATE_LIMIT_ERROR_PREFIXES)

    def get_rate_limit_message(
        self,
        limits: ClaudeAILimits | None = None,
        model: str = "claude",
    ) -> RateLimitMessage | None:
        """
        Get the appropriate rate limit message based on limit state.

        Args:
            limits: Rate limit state (uses current if not provided)
            model: Model name for message

        Returns:
            RateLimitMessage or None if no message should be shown
        """
        if limits is None:
            limits = self._current_limits

        # Check overage scenarios first
        if limits.is_using_overage:
            if limits.overage_status == QuotaStatus.ALLOWED_WARNING:
                return RateLimitMessage(
                    message="You're close to your extra usage spending limit",
                    severity="warning",
                )
            return None

        # ERROR STATES - when limits are rejected
        if limits.status == QuotaStatus.REJECTED:
            return RateLimitMessage(
                message=self._get_limit_reached_text(limits, model),
                severity="error",
            )

        # WARNING STATES - when approaching limits
        if limits.status == QuotaStatus.ALLOWED_WARNING:
            # Only show warnings when utilization is above threshold (70%)
            WARNING_THRESHOLD = 0.7
            if limits.utilization is not None and limits.utilization < WARNING_THRESHOLD:
                return None

            text = self._get_early_warning_text(limits)
            if text:
                return RateLimitMessage(message=text, severity="warning")

        return None

    def get_rate_limit_error_message(
        self,
        limits: ClaudeAILimits | None = None,
        model: str = "claude",
    ) -> str | None:
        """
        Get error message for API errors.

        Returns the message string or None if no error message should be shown.
        """
        message = self.get_rate_limit_message(limits, model)
        if message and message.severity == "error":
            return message.message
        return None

    def get_rate_limit_warning(
        self,
        limits: ClaudeAILimits | None = None,
        model: str = "claude",
    ) -> str | None:
        """
        Get warning message for UI footer.

        Returns the warning message string or None if no warning should be shown.
        """
        message = self.get_rate_limit_message(limits, model)
        if message and message.severity == "warning":
            return message.message
        return None

    def get_using_overage_text(self, limits: ClaudeAILimits | None = None) -> str:
        """Get notification text for overage mode transitions."""
        if limits is None:
            limits = self._current_limits

        reset_time = self._format_reset_time(limits.resets_at) if limits.resets_at else ""

        limit_name = ""
        if limits.rate_limit_type == RateLimitType.FIVE_HOUR:
            limit_name = "session limit"
        elif limits.rate_limit_type == RateLimitType.SEVEN_DAY:
            limit_name = "weekly limit"
        elif limits.rate_limit_type == RateLimitType.SEVEN_DAY_OPUS:
            limit_name = "Opus limit"
        elif limits.rate_limit_type == RateLimitType.SEVEN_DAY_SONNET:
            limit_name = "Sonnet limit"

        if not limit_name:
            return "Now using extra usage"

        if reset_time:
            return f"You're now using extra usage · Your {limit_name} resets {reset_time}"
        return f"You're now using extra usage"

    def _get_limit_reached_text(self, limits: ClaudeAILimits, model: str) -> str:
        """Generate limit reached error message."""
        resets_at = limits.resets_at
        reset_time = self._format_reset_time(resets_at) if resets_at else ""
        reset_msg = f" · resets {reset_time}" if reset_time else ""

        # Overage exhausted
        if limits.overage_status == QuotaStatus.REJECTED:
            if limits.overage_disabled_reason == OverageDisabledReason.OUT_OF_CREDITS:
                return f"You're out of extra usage{reset_msg}"
            return self._format_limit_reached_text("limit", reset_msg, model)

        # Sonnet limit
        if limits.rate_limit_type == RateLimitType.SEVEN_DAY_SONNET:
            return self._format_limit_reached_text("Sonnet limit", reset_msg, model)

        # Opus limit
        if limits.rate_limit_type == RateLimitType.SEVEN_DAY_OPUS:
            return self._format_limit_reached_text("Opus limit", reset_msg, model)

        # Weekly limit
        if limits.rate_limit_type == RateLimitType.SEVEN_DAY:
            return self._format_limit_reached_text("weekly limit", reset_msg, model)

        # Session limit
        if limits.rate_limit_type == RateLimitType.FIVE_HOUR:
            return self._format_limit_reached_text("session limit", reset_msg, model)

        return self._format_limit_reached_text("usage limit", reset_msg, model)

    def _get_early_warning_text(self, limits: ClaudeAILimits) -> str | None:
        """Generate early warning text."""
        if limits.rate_limit_type is None:
            return None

        limit_name = get_rate_limit_display_name(limits.rate_limit_type)

        used = None
        if limits.utilization is not None:
            used = int(limits.utilization * 100)

        reset_time = self._format_reset_time(limits.resets_at) if limits.resets_at else None

        if used and reset_time:
            base = f"You've used {used}% of your {limit_name} · resets {reset_time}"
        elif used:
            base = f"You've used {used}% of your {limit_name}"
        elif reset_time:
            base = f"Approaching {limit_name} · resets {reset_time}"
        else:
            base = f"Approaching {limit_name}"

        return base

    def _format_limit_reached_text(self, limit: str, reset_msg: str, model: str) -> str:
        """Format limit reached message."""
        return f"You've hit your {limit}{reset_msg}"

    def _format_reset_time(self, timestamp: float | None) -> str | None:
        """Format a reset timestamp as relative time."""
        if timestamp is None:
            return None

        now = time.time()
        seconds_until = timestamp - now

        if seconds_until <= 0:
            return "soon"

        if seconds_until < 60:
            return f"{int(seconds_until)}s"
        elif seconds_until < 3600:
            return f"{int(seconds_until / 60)}m"
        elif seconds_until < 86400:
            return f"{int(seconds_until / 3600)}h"
        else:
            return f"{int(seconds_until / 86400)}d"


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_service: RateLimitsService | None = None


def get_rate_limits_service() -> RateLimitsService:
    """Get the global rate limits service."""
    global _service
    if _service is None:
        _service = RateLimitsService()
    return _service


def is_rate_limit_error_message(text: str) -> bool:
    """Check if a message is a rate limit error."""
    return get_rate_limits_service().is_rate_limit_error_message(text)


def get_rate_limit_message(
    limits: ClaudeAILimits | None = None,
    model: str = "claude",
) -> RateLimitMessage | None:
    """Get rate limit message."""
    return get_rate_limits_service().get_rate_limit_message(limits, model)
