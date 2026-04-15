"""
Rate Limits Mocking Service.

Provides mock rate limiting for testing purposes.
Allows simulating rate limit responses without hitting real API limits.

Mirrors TS rateLimitMocking.ts behavior.
"""
from __future__ import annotations

import os
import threading
from typing import Any


# Global mock state
_mock_headers: dict[str, str] | None = None
_mock_fast_mode_rate_limit: bool = False
_mock_headerless_429_message: str | None = None
_is_mock_active: bool = False
_mock_lock = threading.Lock()


def _is_ant_employee() -> bool:
    """Check if current user is an Anthropic employee."""
    return os.environ.get("USER_TYPE") == "ant"


def should_process_mock_limits() -> bool:
    """
    Check if mock rate limits should be processed.

    Only active for Ant employees using /mock-limits command.

    Returns:
        True if mock limits are active
    """
    if not _is_ant_employee():
        return False
    return _is_mock_active


def set_mock_limits_active(active: bool) -> None:
    """
    Enable or disable mock rate limiting.

    Args:
        active: Whether mock limits should be active
    """
    global _is_mock_active
    with _mock_lock:
        _is_mock_active = active


def get_mock_headers() -> dict[str, str] | None:
    """
    Get the current mock headers.

    Returns:
        Mock headers dict or None if not set
    """
    return _mock_headers


def set_mock_headers(headers: dict[str, str] | None) -> None:
    """
    Set mock response headers for rate limiting.

    Args:
        headers: Headers to use for mock responses
    """
    global _mock_headers
    with _mock_lock:
        _mock_headers = headers


def is_mock_fast_mode_rate_limit_scenario() -> bool:
    """
    Check if we should simulate fast mode rate limits.

    Returns:
        True if in mock fast mode rate limit scenario
    """
    return _mock_fast_mode_rate_limit


def set_mock_fast_mode_rate_limit(active: bool) -> None:
    """
    Enable or disable mock fast mode rate limiting.

    Args:
        active: Whether fast mode mock is active
    """
    global _mock_fast_mode_rate_limit
    with _mock_lock:
        _mock_fast_mode_rate_limit = active


def get_mock_headerless_429_message() -> str | None:
    """
    Get the mock headerless 429 error message.

    Returns:
        Message for headerless 429 or None
    """
    return _mock_headerless_429_message


def set_mock_headerless_429_message(message: str | None) -> None:
    """
    Set the mock headerless 429 error message.

    Args:
        message: Error message for headerless 429
    """
    global _mock_headerless_429_message
    with _mock_lock:
        _mock_headerless_429_message = message


def apply_mock_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Apply mock headers to a response.

    Args:
        headers: Original response headers

    Returns:
        Headers with mock data applied
    """
    if not should_process_mock_limits() or _mock_headers is None:
        return headers

    # Apply mock headers
    result = dict(headers)
    result.update(_mock_headers)
    return result


def check_mock_fast_mode_rate_limit(
    is_fast_mode_active: bool | None = None,
) -> dict[str, Any] | None:
    """
    Check if mock fast mode rate limit should apply.

    Args:
        is_fast_mode_active: Whether fast mode is currently active

    Returns:
        Mock headers dict or None
    """
    if not should_process_mock_limits():
        return None

    if not is_mock_fast_mode_rate_limit_scenario():
        return None

    # Return mock fast mode headers
    return {
        "anthropic-ratelimit-unified-status": "rejected",
        "anthropic-ratelimit-unified-reset": "1800",  # 30 minutes
    }


def reset_mock_limits() -> None:
    """Reset all mock state to defaults."""
    global _mock_headers, _mock_fast_mode_rate_limit, _mock_headerless_429_message, _is_mock_active
    with _mock_lock:
        _mock_headers = None
        _mock_fast_mode_rate_limit = False
        _mock_headerless_429_message = None
        _is_mock_active = False
