"""Bridge entitlement and feature gate checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from py_claw.services.bridge.config import get_bridge_feature_config

if TYPE_CHECKING:
    from py_claw.services.bridge.types import BridgeEntitlement


def is_bridge_enabled() -> bool:
    """Runtime check for bridge mode entitlement.

    Returns true when:
    1. Bridge mode is enabled at build/runtime (via BRIDGE_MODE env var)
    2. The GrowthBook gate 'tengu_ccr_bridge' is enabled
    3. The OAuth account has a claude.ai subscription

    Remote Control requires a claude.ai subscription. This excludes:
    - Bedrock/Vertex/Foundry deployments
    - apiKeyHelper/gateway deployments
    - Env-var API keys
    - Console API logins

    Returns:
        True if bridge is enabled and entitled, False otherwise.
    """
    feature_config = get_bridge_feature_config()

    if not feature_config.bridge_mode_enabled:
        return False

    # In a full implementation, this would also check:
    # - isClaudeAISubscriber() via OAuth tokens
    # - GrowthBook gate: tengu_ccr_bridge
    return feature_config.ccr_bridge_enabled


def is_env_less_bridge_enabled() -> bool:
    """Runtime check for the env-less (v2) REPL bridge path.

    Returns true when the GrowthBook flag 'tengu_bridge_repl_v2' is enabled.
    This gates which implementation initReplBridge uses - NOT whether bridge
    is available at all (see is_bridge_enabled above).
    """
    feature_config = get_bridge_feature_config()

    if not feature_config.bridge_mode_enabled:
        return False

    # In a full implementation, this would check:
    # - GrowthBook gate: tengu_bridge_repl_v2
    return feature_config.env_less_bridge_enabled


def is_bridge_enabled_blocking() -> bool:
    """Blocking entitlement check for Remote Control.

    Returns cached true immediately (fast path). If the disk cache says
    false or is missing, awaits GrowthBook init and fetches the fresh
    server value (slow path, max ~5s), then writes it to disk.

    Use at entitlement gates where a stale false would unfairly block access.
    For user-facing error paths, prefer get_bridge_disabled_reason() which gives
    a specific diagnostic.
    """
    # In a full implementation with GrowthBook:
    # - Check disk cache first
    # - If cache miss or false, await GrowthBook init
    # - Fetch fresh value and update cache
    return is_bridge_enabled()


def get_bridge_disabled_reason() -> str | None:
    """Diagnostic message for why Remote Control is unavailable, or None if enabled.

    Returns an actionable error message instead of a bare boolean.
    This gives users a specific diagnostic when Remote Control is not available.

    Returns:
        Error message string if disabled, None if enabled.
    """
    feature_config = get_bridge_feature_config()

    if not feature_config.bridge_mode_enabled:
        return "Remote Control is not available in this build."

    # In a full implementation, this would also check:
    # - isClaudeAISubscriber() - requires claude.ai subscription
    # - hasProfileScope() - requires full-scope login token
    # - organizationUuid from OAuth account info
    # - GrowthBook gate: tengu_ccr_bridge

    if not feature_config.ccr_bridge_enabled:
        return "Remote Control is not yet enabled for your account."

    return None


def is_cse_shim_enabled() -> bool:
    """Kill-switch for the cse_* -> session_* client-side retag shim.

    The shim exists because compat/convert.go validates TagSession and the
    claude.ai frontend routes on session_*, while v2 worker endpoints hand out
    cse_*. Once the server tags by environment_kind and the frontend accepts
    cse_* directly, flip this to False to make toCompatSessionId a no-op.
    Defaults to True — the shim stays active until explicitly disabled.
    """
    feature_config = get_bridge_feature_config()

    if not feature_config.bridge_mode_enabled:
        return True  # Default active when bridge disabled

    # In a full implementation, this would check GrowthBook:
    # getFeatureValue_CACHED_MAY_BE_STALE('tengu_bridge_repl_v2_cse_shim_enabled', True)
    return True


def get_bridge_entitlement() -> "BridgeEntitlement":
    """Get full bridge entitlement result including capabilities.

    Returns:
        BridgeEntitlement with allowed status and capability details.
    """
    from py_claw.services.bridge.types import BridgeCapability, BridgeEntitlement

    if not is_bridge_enabled():
        return BridgeEntitlement(
            allowed=False,
            reason=get_bridge_disabled_reason(),
            capabilities=[],
        )

    capabilities = [
        BridgeCapability(
            name="env_less_bridge",
            enabled=is_env_less_bridge_enabled(),
            reason=None,
        ),
        BridgeCapability(
            name="cse_shim",
            enabled=True,  # Always enabled in Python implementation
            reason=None,
        ),
    ]

    return BridgeEntitlement(
        allowed=True,
        reason=None,
        capabilities=capabilities,
    )
