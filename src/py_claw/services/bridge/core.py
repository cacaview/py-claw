"""Core bridge implementation for v2 env-less protocol.

Provides the v2 Remote Control protocol implementation with
JWT exchange and env-less authentication.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from py_claw.services.bridge.config import get_bridge_config
from py_claw.services.bridge.enabled import (
    is_cse_shim_enabled,
    is_env_less_bridge_enabled,
)
from py_claw.services.bridge.jwt import (
    create_token_refresh_scheduler,
    decode_jwt_expiry,
    decode_jwt_payload,
    sign_jwt_payload,
    verify_jwt_signature,
)
from py_claw.services.bridge.session_api import SessionApiClient
from py_claw.services.bridge.state import get_bridge_state
from py_claw.services.bridge.trusted_device import (
    get_token_expiry_seconds,
    is_trusted_device_token_valid,
)
from py_claw.services.bridge.types import (
    BridgeConfig,
    BridgeState,
    CreateSessionResult,
    ReplBridgeHandle,
)

logger = logging.getLogger(__name__)


# Protocol constants
PROTOCOL_VERSION = "v2"
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
MAX_POLL_INTERVAL_SECONDS = 30.0
HEARTBEAT_INTERVAL_SECONDS = 30.0


@dataclass
class BridgeCoreParams:
    """Parameters for initializing bridge core.

    Everything needed to establish and maintain a bridge connection.
    """

    # Connection parameters
    base_url: str
    session_ingress_url: str
    environment_id: str
    access_token: str

    # Session metadata
    title: str | None = None
    git_repo_url: str | None = None
    branch: str | None = None
    permission_mode: str | None = None
    machine_name: str | None = None

    # Callbacks
    on_message: Callable[[dict[str, Any]], None] | None = None
    on_state_change: Callable[[BridgeState, str | None], None] | None = None
    on_error: Callable[[str], None] | None = None

    # Options
    perpetual: bool = False
    outbound_only: bool = False


@dataclass
class BridgeCore:
    """Core bridge implementation for v2 env-less protocol.

    Manages the bridge lifecycle including:
    - JWT-based authentication
    - Session polling/heartbeat
    - Message routing
    - Token refresh
    """

    params: BridgeCoreParams
    config: BridgeConfig
    bridge_session_id: str | None = None
    state: BridgeState = BridgeState.DISCONNECTED
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Internal state
    _api_client: SessionApiClient | None = None
    _poll_task: asyncio.Task | None = None
    _heartbeat_task: asyncio.Task | None = None
    _token_scheduler: Any = None
    _poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS

    def is_env_less(self) -> bool:
        """Check if using env-less (v2) protocol."""
        return is_env_less_bridge_enabled()

    def set_state(self, new_state: BridgeState, detail: str | None = None) -> None:
        """Transition to a new state."""
        old_state = self.state
        self.state = new_state
        logger.debug(
            "Bridge core state: %s -> %s (%s)",
            old_state.value,
            new_state.value,
            detail,
        )
        if self.params.on_state_change:
            self.params.on_state_change(new_state, detail)

    async def initialize(self) -> bool:
        """Initialize the bridge connection.

        Returns:
            True if initialization successful
        """
        try:
            self.set_state(BridgeState.READY, "initializing")

            # Create API client
            self._api_client = SessionApiClient(
                base_url=self.params.base_url,
                access_token=self.params.access_token,
            )

            # Create session
            result = await self._create_session()
            if not result.success or not result.session_id:
                self.set_state(BridgeState.FAILED, result.error or "session creation failed")
                return False

            self.bridge_session_id = result.session_id

            # Setup token refresh
            self._setup_token_refresh()

            # Start polling
            self._poll_task = asyncio.create_task(self._poll_loop())

            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            self.set_state(BridgeState.CONNECTED, "initialized")
            return True

        except Exception as e:
            logger.error("Bridge initialization failed: %s", e)
            self.set_state(BridgeState.FAILED, str(e))
            return False

    async def _create_session(self) -> CreateSessionResult:
        """Create the bridge session via API."""
        if not self._api_client:
            return CreateSessionResult(success=False, error="No API client")

        return await self._api_client.create_session(
            environment_id=self.params.environment_id,
            title=self.params.title,
            git_repo_url=self.params.git_repo_url,
            branch=self.params.branch,
            permission_mode=self.params.permission_mode,
        )

    def _setup_token_refresh(self) -> None:
        """Setup token refresh scheduler."""
        if not self._api_client or not self.bridge_session_id:
            return

        def get_access_token() -> str | None:
            return self.params.access_token

        def on_refresh(session_id: str, token: str) -> None:
            logger.info("Token refreshed for session: %s", session_id)

        self._token_scheduler = create_token_refresh_scheduler(
            get_access_token=get_access_token,
            on_refresh=on_refresh,
            label="bridge",
        )

    async def _poll_loop(self) -> None:
        """Main polling loop for fetching messages."""
        import asyncio

        while self.state in (BridgeState.CONNECTED, BridgeState.RECONNECTING):
            try:
                # Fetch messages
                messages = await self._poll_messages()

                # Process messages
                for msg in messages:
                    self._handle_message(msg)

                # Adaptive poll interval
                self._poll_interval = min(
                    self._poll_interval * 1.5,
                    MAX_POLL_INTERVAL_SECONDS,
                )

            except Exception as e:
                logger.error("Poll error: %s", e)
                self.set_state(BridgeState.RECONNECTING, str(e))
                self._poll_interval = DEFAULT_POLL_INTERVAL_SECONDS

            await asyncio.sleep(self._poll_interval)

    async def _poll_messages(self) -> list[dict[str, Any]]:
        """Poll for new messages from the server.

        Returns:
            List of message objects
        """
        if not self._api_client or not self.bridge_session_id:
            return []

        # In full implementation:
        # GET /v1/sessions/{id}/poll?since={sequence}
        # Returns messages since last poll

        # For now, return empty
        return []

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat to keep connection alive."""
        while self.state == BridgeState.CONNECTED:
            try:
                await self._send_heartbeat()
            except Exception as e:
                logger.error("Heartbeat error: %s", e)

            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

    async def _send_heartbeat(self) -> bool:
        """Send a heartbeat ping.

        Returns:
            True if heartbeat successful
        """
        if not self._api_client or not self.bridge_session_id:
            return False

        # In full implementation:
        # POST /v1/sessions/{id}/ping

        return True

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle an incoming message."""
        if self.params.on_message:
            try:
                self.params.on_message(msg)
            except Exception as e:
                logger.error("Message handler error: %s", e)

    async def send_message(self, message: dict[str, Any]) -> bool:
        """Send a message to the bridge.

        Args:
            message: Message object to send

        Returns:
            True if sent successfully
        """
        if not self._api_client or not self.bridge_session_id:
            return False

        try:
            # In full implementation:
            # POST /v1/sessions/{id}/messages
            logger.debug("Sent message: %s", message.get("type", "unknown"))
            return True

        except Exception as e:
            logger.error("Send error: %s", e)
            return False

    async def teardown(self) -> None:
        """Clean up bridge resources."""
        logger.info("Tearing down bridge core: %s", self.bridge_session_id)

        # Cancel tasks
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        # Cancel token refresh
        if self._token_scheduler:
            self._token_scheduler.cancel_all()

        # Archive session
        if self._api_client and self.bridge_session_id:
            try:
                await self._api_client.archive_session(self.bridge_session_id)
            except Exception as e:
                logger.error("Archive error: %s", e)

        self.set_state(BridgeState.DISCONNECTED, "teardown")


def create_bridge_core(
    params: BridgeCoreParams,
) -> BridgeCore:
    """Create a new bridge core instance.

    Args:
        params: Bridge initialization parameters

    Returns:
        Configured BridgeCore instance
    """
    config = get_bridge_config()

    return BridgeCore(
        params=params,
        config=config,
    )


@dataclass
class JwtExchangeConfig:
    """Configuration for JWT exchange."""

    # JWT secret for signing
    secret: str
    # Issuer claim
    issuer: str = "claude-code"
    # Audience claim
    audience: str = "claude-ai"
    # Default expiry in seconds
    expiry_seconds: int = 3600


async def exchange_token_for_jwt(
    access_token: str,
    config: JwtExchangeConfig,
) -> str | None:
    """Exchange an OAuth access token for a bridge JWT.

    Args:
        access_token: OAuth access token
        config: JWT exchange configuration

    Returns:
        JWT string, or None on failure
    """
    # In full implementation:
    # 1. Validate OAuth token with auth server
    # 2. Extract claims (user_id, org_id, etc.)
    # 3. Create JWT with those claims
    # 4. Return signed JWT

    import uuid

    # Create payload with claims
    payload = {
        "sub": str(uuid.uuid4()),  # User ID
        "org": "default-org",  # Organization
        "scope": "bridge",
        "jti": str(uuid.uuid4()),  # JWT ID
    }

    # Sign JWT
    jwt = sign_jwt_payload(
        payload=payload,
        secret=config.secret,
        algorithm="HS256",
        expires_in_seconds=config.expiry_seconds,
    )

    return jwt


def verify_bridge_jwt(
    token: str,
    secret: str,
) -> dict[str, Any] | None:
    """Verify a bridge JWT.

    Args:
        token: JWT string
        secret: Secret used to sign

    Returns:
        Decoded payload if valid, None otherwise
    """
    if not verify_jwt_signature(token, secret):
        return None

    return decode_jwt_payload(token)
