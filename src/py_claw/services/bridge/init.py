"""REPL bridge facade and initialization.

This module provides the high-level initialization for REPL bridge,
including entitlement gates, title derivation, and session creation.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from py_claw.services.bridge.config import get_bridge_config
from py_claw.services.bridge.enabled import (
    get_bridge_disabled_reason,
    is_bridge_enabled,
    is_bridge_enabled_blocking,
)
from py_claw.services.bridge.repl import (
    ReplBridgeCore,
    ReplBridgeManager,
    get_repl_bridge_manager,
)
from py_claw.services.bridge.state import get_bridge_state
from py_claw.services.bridge.types import (
    BridgeConfig,
    BridgeState,
    CreateSessionParams,
    CreateSessionResult,
    ReplBridgeHandle,
)

logger = logging.getLogger(__name__)


@dataclass
class InitBridgeOptions:
    """Options for initializing a REPL bridge."""

    # Callbacks
    on_inbound_message: Callable[[dict[str, Any]], None] | None = None
    on_permission_response: Callable[[dict[str, Any]], None] | None = None
    on_interrupt: Callable[[], None] | None = None
    on_set_model: Callable[[str | None], None] | None = None
    on_set_max_thinking_tokens: Callable[[int | None], None] | None = None
    on_set_permission_mode: Callable[[str], dict[str, Any]] | None = None
    on_state_change: Callable[[BridgeState, str | None], None] | None = None
    on_user_message: Callable[[str, str], bool] | None = None

    # Session options
    initial_messages: list[dict[str, Any]] | None = None
    initial_name: str | None = None
    previously_flushed_uuids: set[str] | None = None
    perpetual: bool = False
    outbound_only: bool = False
    tags: list[str] | None = None

    # Environment/context
    cwd: str | None = None
    machine_name: str | None = None
    branch: str | None = None
    git_repo_url: str | None = None


async def init_repl_bridge(
    options: InitBridgeOptions | None = None,
) -> ReplBridgeHandle | None:
    """Initialize a REPL bridge session.

    This is the main entry point for starting a Remote Control session.
    It checks all entitlement gates, derives session metadata, and
    creates the bridge connection.

    Args:
        options: Initialization options

    Returns:
        ReplBridgeHandle if successful, None if bridge is not enabled or entitled
    """
    opts = options or InitBridgeOptions()

    # Step 1: Runtime gate check (blocking)
    if not await is_bridge_enabled_blocking():
        logger.info("[bridge:repl] Skipping: bridge not enabled")
        return None

    # Step 2: OAuth check - must be logged in with claude.ai
    access_token = _get_bridge_access_token()
    if not access_token:
        logger.info("[bridge:repl] Skipping: no OAuth tokens")
        opts.on_state_change and opts.on_state_change(
            BridgeState.FAILED, "/login"
        )
        return None

    # Step 3: Check organization policy
    if not _is_policy_allowed():
        logger.info(
            "[bridge:repl] Skipping: allow_remote_control policy not allowed"
        )
        opts.on_state_change and opts.on_state_change(
            BridgeState.FAILED, "disabled by your organization's policy"
        )
        return None

    # Step 4: Compute base URL
    base_url = _get_bridge_base_url()

    # Step 5: Derive session title
    title = _derive_session_title(opts)

    # Step 6: Get/create session ingress URL
    session_ingress_url = _get_session_ingress_url(base_url, access_token)

    # Step 7: Create the session via API
    create_result = await _create_bridge_session(
        base_url=base_url,
        access_token=access_token,
        title=title,
        git_repo_url=opts.git_repo_url,
        branch=opts.branch,
        permission_mode=opts.on_set_permission_mode("ask")
        if opts.on_set_permission_mode
        else None,
    )

    if not create_result.success or not create_result.session_id:
        logger.error(
            "[bridge:repl] Failed to create bridge session: %s",
            create_result.error,
        )
        opts.on_state_change and opts.on_state_change(
            BridgeState.FAILED, create_result.error or "session creation failed"
        )
        return None

    # Step 8: Create the bridge
    manager = get_repl_bridge_manager()
    bridge = await manager.create_bridge(
        environment_id=_get_environment_id(),
        session_ingress_url=session_ingress_url,
        title=title,
        git_repo_url=opts.git_repo_url,
        branch=opts.branch,
        permission_mode=opts.on_set_permission_mode("ask")
        if opts.on_set_permission_mode
        else None,
    )

    # Wire up callbacks
    if opts.on_state_change:
        bridge._on_state_change = opts.on_state_change
    if opts.on_inbound_message:
        bridge._on_inbound_message = opts.on_inbound_message

    bridge.set_state(BridgeState.READY, "initialized")

    logger.info(
        "[bridge:repl] Bridge initialized: session_id=%s bridge_id=%s",
        create_result.session_id,
        bridge.bridge_session_id,
    )

    return bridge.to_handle()


async def init_repl_bridge_simple() -> ReplBridgeHandle | None:
    """Simple bridge initialization with minimal options.

    Returns:
        ReplBridgeHandle if successful, None otherwise
    """
    return await init_repl_bridge(None)


def _get_bridge_access_token() -> str | None:
    """Get the bridge access token from OAuth."""
    # In a full implementation, this would:
    # 1. Check for CLAUDE_BRIDGE_OAUTH_TOKEN override (ant-only)
    # 2. Fall back to OAuth tokens from keychain
    token_override = os.environ.get("CLAUDE_BRIDGE_OAUTH_TOKEN")
    if token_override:
        return token_override

    # In full implementation: getClaudeAIOAuthTokens()?.accessToken
    # For now, check env var
    return os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")


def _get_bridge_base_url() -> str:
    """Get the bridge base URL."""
    # Check for override
    override = os.environ.get("CLAUDE_BRIDGE_BASE_URL")
    if override:
        return override

    # In full implementation: getOauthConfig().BASE_API_URL
    return os.environ.get("CLAUDE_BRIDGE_BASE_URL", "https://api.claude.ai")


def _get_session_ingress_url(base_url: str, access_token: str) -> str:
    """Get the session ingress URL for the bridge."""
    # In full implementation, this would call the API to get the ingress URL
    # For now, construct it from base URL
    return f"{base_url}/v1/sessions/ingress"


def _is_policy_allowed() -> bool:
    """Check if remote control is allowed by policy."""
    # In a full implementation, this would check policy limits
    # For now, return True
    return True


def _derive_session_title(opts: InitBridgeOptions) -> str:
    """Derive the session title from options and context."""
    import uuid

    # Explicit name takes precedence
    if opts.initial_name:
        return opts.initial_name

    # Try to get from session storage (custom /rename)
    # In full implementation: getCurrentSessionTitle(sessionId)
    # For now, derive from messages if available
    if opts.initial_messages:
        for msg in reversed(opts.initial_messages):
            if _is_meaningful_user_message(msg):
                content = _extract_message_text(msg)
                if content:
                    derived = _derive_title_from_text(content)
                    if derived:
                        return derived

    # Fallback: generated slug
    return f"remote-control-{uuid.uuid4().hex[:8]}"


def _is_meaningful_user_message(msg: dict[str, Any]) -> bool:
    """Check if a message is a meaningful user message for title derivation."""
    if msg.get("type") != "user":
        return False
    if msg.get("isMeta") or msg.get("toolUseResult") or msg.get("isCompactSummary"):
        return False
    # Skip synthetic messages
    if msg.get("isSynthetic"):
        return False
    return True


def _extract_message_text(msg: dict[str, Any]) -> str | None:
    """Extract text content from a message."""
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        for block in content:
            if block.get("type") == "text":
                return block.get("text", "")
    elif isinstance(content, str):
        return content
    return None


def _derive_title_from_text(text: str) -> str | None:
    """Derive a title from message text."""
    # Simple derivation: first meaningful words
    words = text.split()[:5]
    if not words:
        return None
    return "-".join(words).lower()[:50]


def _get_environment_id() -> str:
    """Get the environment ID for the bridge."""
    # In full implementation: from OAuth/organization info
    return os.environ.get("CLAUDE_BRIDGE_ENV_ID", "default")


async def _create_bridge_session(
    base_url: str,
    access_token: str,
    title: str,
    git_repo_url: str | None = None,
    branch: str | None = None,
    permission_mode: str | None = None,
) -> CreateSessionResult:
    """Create a bridge session via API.

    In a full implementation, this would call POST /v1/sessions
    to create the session and get the session ingress URL.
    """
    # In full implementation, this would:
    # 1. Call POST /v1/sessions with OAuth headers
    # 2. Include git source/outcome context
    # 3. Include permission_mode
    # 4. Return the session ID and ingress URL

    # For now, return a mock successful result
    import uuid

    session_id = str(uuid.uuid4())

    logger.info(
        "[bridge:repl] Created session: id=%s title=%s",
        session_id,
        title,
    )

    return CreateSessionResult(
        success=True,
        session_id=session_id,
    )


async def archive_bridge_session(session_id: str) -> bool:
    """Archive a bridge session.

    Args:
        session_id: The session ID to archive

    Returns:
        True if archived successfully
    """
    # In full implementation: POST /v1/sessions/{id}/archive
    logger.info("[bridge:repl] Archived session: %s", session_id)
    return True


async def update_bridge_session_title(
    session_id: str, title: str
) -> bool:
    """Update a bridge session's title.

    Args:
        session_id: The session ID
        title: New title

    Returns:
        True if updated successfully
    """
    # In full implementation: PATCH /v1/sessions/{id}
    logger.info("[bridge:repl] Updated session title: %s -> %s", session_id, title)
    return True
