"""
Policy limits service.

Checks organization-level policy restrictions.

Basic usage:

    from py_claw.services.policy_limits import is_policy_allowed

    if is_policy_allowed('allow_remote_sessions'):
        # Feature is allowed
        pass

    # Or use the service directly
    from py_claw.services.policy_limits import get_policy_limits_service

    svc = get_policy_limits_service()
    svc.initialize()
    if svc.is_policy_allowed('allow_remote_sessions'):
        pass
"""
from __future__ import annotations

from .types import (
    PolicyRestriction,
    PolicyRestrictions,
    PolicyLimitsResponse,
    PolicyLimitsFetchResult,
)
from .service import (
    PolicyLimitsService,
    get_policy_limits_service,
    reset_policy_limits_service,
    is_policy_allowed,
)

__all__ = [
    # Types
    "PolicyRestriction",
    "PolicyRestrictions",
    "PolicyLimitsResponse",
    "PolicyLimitsFetchResult",
    # Service
    "PolicyLimitsService",
    "get_policy_limits_service",
    "reset_policy_limits_service",
    # Functions
    "is_policy_allowed",
]
