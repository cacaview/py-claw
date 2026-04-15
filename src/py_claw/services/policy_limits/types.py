"""
Policy limits types.

Organization-level policy restrictions from the API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyRestriction:
    """A single policy restriction."""
    allowed: bool


PolicyRestrictions = dict[str, PolicyRestriction]


@dataclass
class PolicyLimitsResponse:
    """Response from the policy limits API."""
    restrictions: PolicyRestrictions


@dataclass
class PolicyLimitsFetchResult:
    """Result of fetching policy limits."""
    success: bool
    restrictions: PolicyRestrictions | None = None
    error: str | None = None
    skip_retry: bool = False
