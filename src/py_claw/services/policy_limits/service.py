"""
Policy limits service.

Fetches organization-level policy restrictions and checks if policies are allowed.

This is a simplified implementation that returns True (allowed) for all policies.
A full implementation would fetch from the CCR API with OAuth authentication.
"""
from __future__ import annotations

import threading

from .types import PolicyRestriction, PolicyRestrictions


class PolicyLimitsService:
    """
    Service for checking organization-level policy restrictions.

    Simplified implementation:
    - Returns True (allowed) for all policies
    - A full implementation would fetch restrictions from the API

    The TS reference implementation fetches from:
    GET /api/claude_code/policy_limits

    with OAuth or API key authentication.
    """

    def __init__(self) -> None:
        self._restrictions: PolicyRestrictions | None = None
        self._initialized = False
        self._lock = threading.RLock()

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        """Initialize the policy limits service."""
        with self._lock:
            if self._initialized:
                return
            # In simplified mode, we don't fetch from API
            # Just mark as initialized with empty restrictions
            self._restrictions = {}
            self._initialized = True

    def is_policy_allowed(self, policy: str) -> bool:
        """
        Check if a specific policy is allowed.

        Returns True if:
        - Policy is unknown (fail-open)
        - Policy is explicitly allowed
        - Service is not initialized

        Returns False only if policy is explicitly disallowed.
        """
        if not self._initialized:
            self.initialize()

        restrictions = self._restrictions
        if restrictions is None:
            # Not initialized or fetch failed - fail open
            return True

        restriction = restrictions.get(policy)
        if restriction is None:
            # Unknown policy = allowed
            return True

        return restriction.allowed

    def get_restrictions(self) -> PolicyRestrictions | None:
        """Get current policy restrictions."""
        return self._restrictions

    def set_restrictions(self, restrictions: PolicyRestrictions) -> None:
        """Set policy restrictions (e.g., from API response)."""
        with self._lock:
            self._restrictions = restrictions


# ============================================================================
# Global singleton
# ============================================================================

_service: PolicyLimitsService | None = None


def get_policy_limits_service() -> PolicyLimitsService:
    """Get the global policy limits service instance."""
    global _service
    if _service is None:
        _service = PolicyLimitsService()
    return _service


def reset_policy_limits_service() -> None:
    """Reset the global policy limits service (for testing)."""
    global _service
    _service = None


# ============================================================================
# Convenience functions
# ============================================================================

def is_policy_allowed(policy: str) -> bool:
    """
    Check if a specific policy is allowed.

    Simplified implementation that returns True for all policies.
    """
    return get_policy_limits_service().is_policy_allowed(policy)
