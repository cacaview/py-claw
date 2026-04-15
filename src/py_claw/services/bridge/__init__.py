"""Bridge service for Remote Control.

This module provides the bridge system for Remote Control connections,
including entitlement checking, session management, and state management.

Phase 1: Core protocol types, config, entitlement checking, JWT, and state ✅
Phase 2: REPL bridge core and session runner ✅
Phase 3: Remote Control - trusted device, session API, webhook, core, main ✅
Phase 4: Bridge supplementary utilities (S7-S23) ✅
"""

from __future__ import annotations

from py_claw.services.bridge.types import (
    BridgeCapability,
    BridgeConfig,
    BridgeEntitlement,
    BridgeSession,
    BridgeState,
    BridgeVersion,
    CreateSessionParams,
    CreateSessionResult,
    GitOutcome,
    GitSource,
    ReplBridgeHandle,
    SessionBridgeId,
    SessionEvent,
    TrustedDeviceToken,
)

# Import Phase 1 modules for direct access
from py_claw.services.bridge import config
from py_claw.services.bridge import enabled
from py_claw.services.bridge import jwt
from py_claw.services.bridge import state
from py_claw.services.bridge.enabled import (
    get_bridge_disabled_reason,
    get_bridge_entitlement,
    is_bridge_enabled,
    is_bridge_enabled_blocking,
    is_env_less_bridge_enabled,
)

# Import Phase 2 modules
from py_claw.services.bridge import init
from py_claw.services.bridge import repl
from py_claw.services.bridge import session_runner

# Import Phase 3 modules
from py_claw.services.bridge import core
from py_claw.services.bridge import main
from py_claw.services.bridge import session_api
from py_claw.services.bridge import trusted_device
from py_claw.services.bridge import webhook

# Import Phase 4 modules (S7-S23)
from py_claw.services.bridge import (
    bridge_pointer,
    bridge_status_util,
    capacity_wake,
    debug_utils,
    env_less_bridge_config,
    flush_gate,
    inbound_attachments,
    inbound_messages,
    peer_sessions,
    poll_config,
    poll_config_defaults,
    repl_bridge_handle,
    repl_bridge_transport,
    session_id_compat,
    work_secret,
)

__all__ = [
    # Types
    "BridgeState",
    "BridgeVersion",
    "BridgeConfig",
    "BridgeCapability",
    "BridgeEntitlement",
    "BridgeSession",
    "CreateSessionParams",
    "CreateSessionResult",
    "GitSource",
    "GitOutcome",
    "SessionEvent",
    "TrustedDeviceToken",
    "SessionBridgeId",
    "ReplBridgeHandle",
    # Phase 1 modules
    "config",
    "enabled",
    "jwt",
    "state",
    # Phase 2 modules
    "init",
    "repl",
    "session_runner",
    # Phase 3 modules
    "core",
    "main",
    "session_api",
    "trusted_device",
    "webhook",
    # Key functions from enabled
    "is_bridge_enabled",
    "is_bridge_enabled_blocking",
    "is_env_less_bridge_enabled",
    "get_bridge_disabled_reason",
    "get_bridge_entitlement",
    # Phase 4 modules (S7-S23)
    "bridge_pointer",
    "bridge_status_util",
    "capacity_wake",
    "debug_utils",
    "env_less_bridge_config",
    "flush_gate",
    "inbound_attachments",
    "inbound_messages",
    "peer_sessions",
    "poll_config",
    "poll_config_defaults",
    "repl_bridge_handle",
    "repl_bridge_transport",
    "session_id_compat",
    "work_secret",
]
