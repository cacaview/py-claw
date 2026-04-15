"""
Claude.ai Rate Limits Service.

Centralized rate limit tracking and message generation.

Provides:
- Current limit state tracking
- Rate limit message generation (error/warning)
- Raw utilization tracking from API headers
- Early warning detection

Basic usage:

    from py_claw.services.rate_limits import get_rate_limits_service, get_rate_limit_message

    svc = get_rate_limits_service()
    svc.initialize()

    # Update from API response headers
    svc.update_from_headers(response_headers)

    # Get message for current limits
    msg = svc.get_rate_limit_message()
    if msg:
        print(f"{msg.severity}: {msg.message}")
"""
from __future__ import annotations

from .types import (
    ClaudeAILimits,
    OverageDisabledReason,
    QuotaStatus,
    RateLimitMessage,
    RateLimitType,
    RawUtilization,
    RawWindowUtilization,
    RATE_LIMIT_DISPLAY_NAMES,
    RATE_LIMIT_ERROR_PREFIXES,
    get_rate_limit_display_name,
)
from .service import (
    RateLimitsService,
    get_rate_limits_service,
    is_rate_limit_error_message,
    get_rate_limit_message,
)

__all__ = [
    # Types
    "ClaudeAILimits",
    "OverageDisabledReason",
    "QuotaStatus",
    "RateLimitMessage",
    "RateLimitType",
    "RawUtilization",
    "RawWindowUtilization",
    # Constants
    "RATE_LIMIT_DISPLAY_NAMES",
    "RATE_LIMIT_ERROR_PREFIXES",
    # Functions
    "get_rate_limit_display_name",
    # Service
    "RateLimitsService",
    "get_rate_limits_service",
    "is_rate_limit_error_message",
    "get_rate_limit_message",
]
