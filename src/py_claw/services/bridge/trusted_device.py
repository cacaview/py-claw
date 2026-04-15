"""Trusted device enrollment for bridge sessions.

Provides 90-day rolling expiry tokens for elevated security sessions.
Enrollment happens during /login and token is stored securely.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from py_claw.services.bridge.types import TrustedDeviceToken

logger = logging.getLogger(__name__)

# Trusted device gate flag
TRUSTED_DEVICE_GATE = "tengu_sessions_elevated_auth_enforcement"

# Token validity period (90 days)
TOKEN_VALIDITY_DAYS = 90


@dataclass
class TrustedDeviceConfig:
    """Configuration for trusted device enrollment."""

    # Gate flag name
    gate_name: str = TRUSTED_DEVICE_GATE
    # Token validity in days
    validity_days: int = TOKEN_VALIDITY_DAYS


def is_gate_enabled() -> bool:
    """Check if the trusted device gate is enabled.

    In a full implementation, this would check GrowthBook.
    """
    # In full implementation: getFeatureValue_CACHED_MAY_BE_STALE(TRUSTED_DEVICE_GATE, False)
    return os.environ.get("CLAUDE_TRUSTED_DEVICE_ENABLED", "").lower() in (
        "true",
        "1",
        "yes",
    )


def get_trusted_device_token() -> str | None:
    """Get the trusted device token if available and gate is enabled.

    Returns:
        The trusted device token string, or None if not enrolled or gate disabled.
    """
    if not is_gate_enabled():
        return None

    # Check env var override (for testing/canary)
    env_token = os.environ.get("CLAUDE_TRUSTED_DEVICE_TOKEN")
    if env_token:
        return env_token

    # In full implementation: read from secure storage
    # For now, return None
    return None


def clear_trusted_device_token_cache() -> None:
    """Clear the cached trusted device token.

    Called after enrollment and on logout.
    """
    # In full implementation: clear memoized secure storage read
    pass


def clear_trusted_device_token() -> None:
    """Clear the stored trusted device token.

    Called before re-enrollment during /login to avoid stale token
    being sent during enrollment in-flight.
    """
    if not is_gate_enabled():
        return

    # In full implementation:
    # - Read secure storage
    # - Delete trustedDeviceToken field
    # - Write back
    logger.info("Cleared trusted device token")


async def enroll_trusted_device(
    access_token: str,
    base_url: str,
) -> TrustedDeviceToken | None:
    """Enroll this device as trusted for bridge sessions.

    Enrollment must happen during /login (server-side 10min gate).
    Token is valid for 90 days (rolling expiry).

    Args:
        access_token: OAuth access token
        base_url: API base URL

    Returns:
        TrustedDeviceToken if enrollment successful, None otherwise
    """
    if not is_gate_enabled():
        logger.debug("Trusted device gate not enabled, skipping enrollment")
        return None

    # Clear any stale token first
    clear_trusted_device_token()

    # In full implementation:
    # POST /auth/trusted_devices
    # Headers: Authorization: Bearer <access_token>
    # Body: { device_name: hostname() }
    # Response: { token: "...", expires_at: "..." }

    # For now, return a mock token
    expires_at = datetime.utcnow() + timedelta(days=TOKEN_VALIDITY_DAYS)

    token = TrustedDeviceToken(
        token=_generate_mock_token(),
        expires_at=expires_at,
        device_name=_get_device_name(),
    )

    logger.info(
        "Enrolled trusted device: device=%s expires=%s",
        token.device_name,
        token.expires_at.isoformat(),
    )

    return token


def _get_device_name() -> str:
    """Get the device name for enrollment."""
    # In full implementation: hostname()
    return os.environ.get("HOSTNAME", "unknown-device")


def _generate_mock_token() -> str:
    """Generate a mock trusted device token."""
    import uuid

    return f"tdt_{uuid.uuid4().hex}"


def is_trusted_device_token_valid(token: TrustedDeviceToken) -> bool:
    """Check if a trusted device token is still valid.

    Args:
        token: The token to check

    Returns:
        True if token exists and is not expired
    """
    if not token or not token.token:
        return False

    if not token.expires_at:
        return True  # No expiry means valid

    return token.expires_at > datetime.utcnow()


def get_token_expiry_seconds(token: TrustedDeviceToken) -> int | None:
    """Get seconds until token expiry.

    Args:
        token: The token to check

    Returns:
        Seconds until expiry, or None if no expiry
    """
    if not token.expires_at:
        return None

    delta = token.expires_at - datetime.utcnow()
    return int(delta.total_seconds())
