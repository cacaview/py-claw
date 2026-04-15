"""
Fast mode state management.

Handles fast mode availability, runtime state (active/cooldown),
org-level status, and fast mode rejection handling.

Mirrors TS fastMode.ts behavior.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .debug import log_for_debugging
from .env import is_env_truthy


# Default timeout for exec operations (10 minutes)
DEFAULT_TIMEOUT_MS = 10 * 60 * 1000

# Cooldown reason types
COOLDOWN_REASON_RATE_LIMIT = "rate_limit"
COOLDOWN_REASON_OVERLOADED = "overloaded"


def is_fast_mode_enabled() -> bool:
    """Check if fast mode feature is enabled via environment."""
    return not is_env_truthy(os.environ.get("CLAUDE_CODE_DISABLE_FAST_MODE", ""))


# -----------------------------------------------------------------------------
# Availability checking
# -----------------------------------------------------------------------------

def is_fast_mode_available() -> bool:
    """Check if fast mode is available for the current session."""
    if not is_fast_mode_enabled():
        return False
    reason = get_fast_mode_unavailable_reason()
    return reason is None


def get_fast_mode_unavailable_reason() -> str | None:
    """
    Get the reason why fast mode is unavailable.

    Returns None if available, or a reason string if not.
    """
    if not is_fast_mode_enabled():
        return "Fast mode is not available"

    # Check for org-level disable via feature flag
    # In Python, we check environment for simplicity
    if is_env_truthy(os.environ.get("CLAUDE_CODE_FAST_MODE_DISABLED", "")):
        return "Fast mode has been disabled by your organization"

    # Check for network-related unavailability
    if is_env_truthy(os.environ.get("CLAUDE_CODE_SKIP_FAST_MODE_NETWORK_ERRORS", "")):
        return None

    # Default: available
    return None


# -----------------------------------------------------------------------------
# Runtime state
# -----------------------------------------------------------------------------

@dataclass
class FastModeRuntimeState:
    """Runtime state of fast mode."""
    status: str  # 'active' or 'cooldown'
    reset_at: float | None = None
    reason: str | None = None


# Alias for compatibility
FastModeState = FastModeRuntimeState


# Global runtime state
_runtime_state: FastModeRuntimeState = FastModeRuntimeState(status="active")
_has_logged_cooldown_expiry = False
_runtime_lock = threading.RLock()


def get_fast_mode_runtime_state() -> FastModeRuntimeState:
    """Get the current fast mode runtime state."""
    global _runtime_state, _has_logged_cooldown_expiry

    with _runtime_lock:
        if _runtime_state.status == "cooldown" and time.time() >= _runtime_state.reset_at:
            if is_fast_mode_enabled() and not _has_logged_cooldown_expiry:
                log_for_debugging("Fast mode cooldown expired, re-enabling fast mode")
                _has_logged_cooldown_expiry = True
                _on_cooldown_expired()
            _runtime_state = FastModeRuntimeState(status="active")

    return _runtime_state


def trigger_fast_mode_cooldown(reset_timestamp: float, reason: str) -> None:
    """
    Trigger fast mode cooldown after a rate limit or overload.

    Args:
        reset_timestamp: Unix timestamp when cooldown ends
        reason: Cooldown reason ('rate_limit' or 'overloaded')
    """
    global _runtime_state, _has_logged_cooldown_expiry

    if not is_fast_mode_enabled():
        return

    with _runtime_lock:
        _runtime_state = FastModeRuntimeState(
            status="cooldown",
            reset_at=reset_timestamp,
            reason=reason,
        )
        _has_logged_cooldown_expiry = False

        duration_ms = reset_timestamp - time.time() * 1000
        log_for_debugging(
            f"Fast mode cooldown triggered ({reason}), duration {duration_ms / 1000:.0f}s"
        )


def clear_fast_mode_cooldown() -> None:
    """Clear fast mode cooldown, returning to active state."""
    global _runtime_state
    with _runtime_lock:
        _runtime_state = FastModeRuntimeState(status="active")


def is_fast_mode_cooldown() -> bool:
    """Check if fast mode is currently in cooldown."""
    return get_fast_mode_runtime_state().status == "cooldown"


def get_fast_mode_state(
    model: str | None,
    fast_mode_user_enabled: bool | None,
) -> str:
    """
    Get the effective fast mode state.

    Args:
        model: Current model name
        fast_mode_user_enabled: User's fast mode setting

    Returns:
        'off', 'cooldown', or 'on'
    """
    if not is_fast_mode_enabled():
        return "off"
    if not is_fast_mode_available():
        return "off"
    if not fast_mode_user_enabled:
        return "off"
    if not _is_fast_mode_supported_by_model(model):
        return "off"
    if is_fast_mode_cooldown():
        return "cooldown"
    return "on"


def _is_fast_mode_supported_by_model(model: str | None) -> bool:
    """Check if a model supports fast mode (Opus 4.6 only)."""
    if not is_fast_mode_enabled():
        return False
    if model is None:
        return False
    return "opus-4-6" in model.lower()


# -----------------------------------------------------------------------------
# Callbacks
# -----------------------------------------------------------------------------

_cooldown_triggered_callbacks: list[Callable[[float, str], None]] = []
_cooldown_expired_callbacks: list[Callable[[], None]] = []
_overage_rejection_callbacks: list[Callable[[str], None]] = []
_org_fast_mode_change_callbacks: list[Callable[[bool], None]] = []


def on_cooldown_triggered(callback: Callable[[float, str], None]) -> None:
    """Register a callback for cooldown triggered events."""
    _cooldown_triggered_callbacks.append(callback)


def on_cooldown_expired(callback: Callable[[], None]) -> None:
    """Register a callback for cooldown expired events."""
    _cooldown_expired_callbacks.append(callback)


def _on_cooldown_triggered(reset_at: float, reason: str) -> None:
    for cb in _cooldown_triggered_callbacks:
        try:
            cb(reset_at, reason)
        except Exception:
            pass


def _on_cooldown_expired() -> None:
    for cb in _cooldown_expired_callbacks:
        try:
            cb()
        except Exception:
            pass


def on_fast_mode_overage_rejection(callback: Callable[[str], None]) -> None:
    """Register a callback for fast mode overage rejection events."""
    _overage_rejection_callbacks.append(callback)


def _on_fast_mode_overage_rejection(message: str) -> None:
    for cb in _overage_rejection_callbacks:
        try:
            cb(message)
        except Exception:
            pass


def handle_fast_mode_rejected_by_api() -> None:
    """
    Handle API rejection of fast mode (e.g., org has it disabled).

    Permanently disables fast mode for this org.
    """
    # In Python, this would update settings and global config
    log_for_debugging("Fast mode rejected by API - org has it disabled")
    clear_fast_mode_cooldown()


def handle_fast_mode_overage_rejection(reason: str | None) -> None:
    """
    Handle fast mode rejection due to overage/billing issues.

    Args:
        reason: The specific overage rejection reason
    """
    message = _get_overage_disabled_message(reason)
    log_for_debugging(
        f"Fast mode overage rejection: {reason or 'unknown'} — {message}"
    )
    _on_fast_mode_overage_rejection(message)


def _get_overage_disabled_message(reason: str | None) -> str:
    """Get the disabled message for a given overage reason."""
    if reason is None:
        return "Fast mode disabled · extra usage not available"

    messages = {
        "out_of_credits": "Fast mode disabled · extra usage credits exhausted",
        "org_level_disabled": "Fast mode disabled · extra usage disabled by your organization",
        "org_service_level_disabled": "Fast mode disabled · extra usage disabled by your organization",
        "org_level_disabled_until": "Fast mode disabled · extra usage spending cap reached",
        "member_level_disabled": "Fast mode disabled · extra usage disabled for your account",
        "seat_tier_level_disabled": "Fast mode disabled · extra usage not available for your plan",
        "seat_tier_zero_credit_limit": "Fast mode disabled · extra usage not available for your plan",
        "member_zero_credit_limit": "Fast mode disabled · extra usage not available for your plan",
        "overage_not_provisioned": "Fast mode requires extra usage billing · /extra-usage to enable",
        "no_limits_configured": "Fast mode requires extra usage billing · /extra-usage to enable",
    }

    return messages.get(reason, "Fast mode disabled · extra usage not available")


# Aliases for compatibility with __init__.py exports
def set_fast_mode_state(status: str, reset_at: float | None = None, reason: str | None = None) -> None:
    """Set the fast mode runtime state.

    Args:
        status: 'active' or 'cooldown'
        reset_at: Timestamp when cooldown ends
        reason: Cooldown reason
    """
    global _runtime_state
    with _runtime_lock:
        _runtime_state = FastModeRuntimeState(
            status=status,
            reset_at=reset_at,
            reason=reason,
        )


def is_in_fast_mode_cooldown() -> bool:
    """Check if fast mode is currently in cooldown."""
    return is_fast_mode_cooldown()


def get_fast_mode_cooldown_remaining_seconds() -> float:
    """Get remaining seconds in fast mode cooldown.

    Returns:
        Seconds remaining, or 0 if not in cooldown
    """
    state = get_fast_mode_runtime_state()
    if state.status != "cooldown" or state.reset_at is None:
        return 0.0
    remaining = state.reset_at - time.time()
    return max(0.0, remaining)


# Callback registration functions
def set_fast_mode_cooldown_callback(callback: Callable[[float, str], None]) -> None:
    """Register a callback for cooldown triggered events.

    Args:
        callback: Function(model, fast_mode_user_enabled) to call
    """
    on_cooldown_triggered(callback)


def set_fast_mode_overage_callback(callback: Callable[[str], None]) -> None:
    """Register a callback for fast mode overage rejection events.

    Args:
        callback: Function(message) to call
    """
    on_fast_mode_overage_rejection(callback)

