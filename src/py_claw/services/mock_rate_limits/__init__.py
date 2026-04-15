"""
Mock Rate Limits service for testing.

Mocks rate limit headers for testing without hitting actual limits.
⚠️ WARNING: For internal testing/demo purposes only!
"""
from __future__ import annotations

from .service import (
    MockScenario,
    MockHeaderKey,
    get_mock_headers,
    set_mock_scenario,
    clear_mock_scenario,
    is_mock_rate_limits_enabled,
)

__all__ = [
    "MockScenario",
    "MockHeaderKey",
    "get_mock_headers",
    "set_mock_scenario",
    "clear_mock_scenario",
    "is_mock_rate_limits_enabled",
]
