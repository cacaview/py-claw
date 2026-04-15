"""
Tests for the policy limits service.
"""
from __future__ import annotations

import pytest

from py_claw.services.policy_limits import (
    PolicyLimitsService,
    PolicyRestriction,
    get_policy_limits_service,
    reset_policy_limits_service,
    is_policy_allowed,
)


class TestPolicyLimitsService:
    """Tests for PolicyLimitsService."""

    def setup_method(self) -> None:
        reset_policy_limits_service()

    def test_singleton(self) -> None:
        svc1 = get_policy_limits_service()
        svc2 = get_policy_limits_service()
        assert svc1 is svc2

    def test_initialize(self) -> None:
        svc = get_policy_limits_service()
        assert not svc.initialized
        svc.initialize()
        assert svc.initialized

    def test_is_policy_allowed_unknown_policy(self) -> None:
        svc = get_policy_limits_service()
        svc.initialize()
        # Unknown policies should be allowed (fail-open)
        assert svc.is_policy_allowed("some_unknown_policy") is True

    def test_is_policy_allowed_explicitly_allowed(self) -> None:
        svc = get_policy_limits_service()
        svc.initialize()
        svc.set_restrictions({
            "allow_remote_sessions": PolicyRestriction(allowed=True),
        })
        assert svc.is_policy_allowed("allow_remote_sessions") is True

    def test_is_policy_allowed_explicitly_denied(self) -> None:
        svc = get_policy_limits_service()
        svc.initialize()
        svc.set_restrictions({
            "allow_remote_sessions": PolicyRestriction(allowed=False),
        })
        assert svc.is_policy_allowed("allow_remote_sessions") is False

    def test_get_restrictions(self) -> None:
        svc = get_policy_limits_service()
        svc.initialize()
        svc.set_restrictions({
            "policy1": PolicyRestriction(allowed=True),
            "policy2": PolicyRestriction(allowed=False),
        })
        restrictions = svc.get_restrictions()
        assert restrictions is not None
        assert restrictions["policy1"].allowed is True
        assert restrictions["policy2"].allowed is False

    def test_uninitialized_is_allowed(self) -> None:
        svc = get_policy_limits_service()
        # Should return True without initialization
        assert svc.is_policy_allowed("any_policy") is True


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self) -> None:
        reset_policy_limits_service()

    def test_is_policy_allowed_function(self) -> None:
        assert is_policy_allowed("allow_remote_sessions") is True
        assert is_policy_allowed("another_policy") is True


class TestPolicyRestriction:
    """Tests for PolicyRestriction dataclass."""

    def test_allowed_true(self) -> None:
        restriction = PolicyRestriction(allowed=True)
        assert restriction.allowed is True

    def test_allowed_false(self) -> None:
        restriction = PolicyRestriction(allowed=False)
        assert restriction.allowed is False
