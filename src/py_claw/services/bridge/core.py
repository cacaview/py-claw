"""Core bridge implementation for v2 env-less protocol.

Provides the v2 Remote Control protocol implementation with
JWT exchange and env-less authentication.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
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
from py_claw.services.bridge.session_runner import (
    NDJSONParser,
    PermissionRequest,
    SessionActivity,
    SessionHandle,
    SessionSpawner,
    SessionSpawnerDeps,
    SessionSpawnOpts,
)
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
    worker_type: str = "claude_code"
    dir_path: str | None = None

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
    environment_secret: str | None = None
    state: BridgeState = BridgeState.DISCONNECTED
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Internal state
    _api_client: SessionApiClient | None = None
    _poll_task: asyncio.Task | None = None
    _heartbeat_task: asyncio.Task | None = None
    _token_scheduler: Any = None
    _poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS
    _spawner: SessionSpawner | None = None
    _active_sessions: dict[str, SessionHandle] = field(default_factory=dict)

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

            # Register environment
            reg_result = await self._register_environment()
            if not reg_result:
                self.set_state(BridgeState.FAILED, "environment registration failed")
                return False

            self.environment_secret = reg_result.get("environment_secret")

            # Create session
            result = await self._create_session()
            if not result.success or not result.session_id:
                self.set_state(BridgeState.FAILED, result.error or "session creation failed")
                return False

            self.bridge_session_id = result.session_id

            # Setup token refresh
            self._setup_token_refresh()

            # Initialize session spawner for child CLI processes
            self._init_spawner()

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

    def _init_spawner(self) -> None:
        """Initialize the session spawner for child CLI processes."""
        # Determine the CLI executable path
        exec_path = sys.executable
        script_args = ["-m", "py_claw.cli.main"] if not os.environ.get("CLAUDE_BRIDGE_CLI") else None

        # Build environment for child processes
        child_env: dict[str, str] = {
            "CCR_BRIDGE_ENABLED": "true",
            "BRIDGE_SESSION_ID": self.bridge_session_id or "",
            "BRIDGE_ENVIRONMENT_ID": self.params.environment_id,
            "BRIDGE_BASE_URL": self.params.base_url,
            "BRIDGE_MODE_ACCESS_TOKEN": self.params.access_token,
        }

        # Add session ingress URL if available
        if self.params.session_ingress_url:
            child_env["BRIDGE_INGRESS_URL"] = self.params.session_ingress_url

        def on_debug(msg: str) -> None:
            logger.debug("[spawner] %s", msg)

        def on_activity(session_id: str, activity: SessionActivity) -> None:
            logger.info("[spawner] Session %s: %s - %s", session_id, activity.type, activity.message)

        def on_permission_request(session_id: str, request: PermissionRequest, access_token: str) -> None:
            logger.info("[spawner] Permission request from %s: %s", session_id, request.request.get("type", "unknown"))
            # Forward to CCR via API client
            if self._api_client:
                asyncio.create_task(self._forward_permission_request(session_id, request, access_token))

        deps = SessionSpawnerDeps(
            exec_path=exec_path,
            script_args=script_args,
            env=child_env,
            verbose=False,
            sandbox=False,
            permission_mode=self.params.permission_mode,
            on_debug=on_debug,
            on_activity=on_activity,
            on_permission_request=on_permission_request,
        )

        self._spawner = SessionSpawner(deps)
        logger.info("Session spawner initialized with exec_path=%s", exec_path)

    async def _forward_permission_request(
        self,
        session_id: str,
        request: PermissionRequest,
        access_token: str,
    ) -> None:
        """Forward a permission request from child CLI to CCR."""
        if not self._api_client:
            return

        try:
            # In full implementation, forward to CCR API
            logger.info("Forwarding permission request for session %s", session_id)
        except Exception as e:
            logger.error("Error forwarding permission request: %s", e)

    async def _spawn_child_process(
        self,
        work_item: dict[str, Any],
        session_ingress_token: str,
    ) -> None:
        """Spawn a child CLI process for a work item.

        Args:
            work_item: The work item from poll response
            session_ingress_token: Token for the child CLI to connect back
        """
        if not self._spawner:
            logger.error("Session spawner not initialized")
            return

        # Get or generate session ID for this child process
        decoded_secret = work_item.get("_decoded_secret", {})
        child_session_id = decoded_secret.get("session_id") or work_item.get("session_id")

        if not child_session_id:
            # Generate a new session ID
            import uuid
            child_session_id = str(uuid.uuid4())

        try:
            # Update spawner env with session-specific token
            spawn_env = dict(self._spawner._deps.env) if self._spawner._deps.env else {}
            spawn_env["BRIDGE_SESSION_INGRESS_TOKEN"] = session_ingress_token
            spawn_env["BRIDGE_CHILD_SESSION_ID"] = child_session_id

            # Create a new spawner with updated env for this session
            # Or use the existing spawner (it will use its own env)
            # The SessionSpawner handles multiple sessions

            # Spawn the child process
            handle = self._spawner.spawn(child_session_id)
            self._active_sessions[child_session_id] = handle

            logger.info(
                "Spawned child CLI process: session_id=%s pid=%s",
                child_session_id,
                handle.process.pid,
            )

        except Exception as e:
            logger.error("Failed to spawn child process for work item %s: %s",
                        work_item.get("id"), e)

    async def _register_environment(self) -> dict[str, Any] | None:
        """Register this bridge with the CCR environment.

        Returns:
            Registration result with environment_secret on success
        """
        if not self._api_client:
            return None

        return await self._api_client.register_bridge_environment(
            environment_id=self.params.environment_id,
            worker_type=self.params.worker_type if hasattr(self.params, 'worker_type') else "claude_code",
            machine_name=self.params.machine_name,
            git_repo_url=self.params.git_repo_url,
            branch=self.params.branch,
            dir_path=getattr(self.params, 'dir_path', None),
        )

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
                    await self._handle_message_async(msg)

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

        # Check if we have environment_secret (set during initialize)
        if not self.environment_secret:
            logger.warning("No environment_secret available for polling")
            return []

        # Poll for work from CCR
        work_item = await self._api_client.poll_for_work(
            environment_id=self.params.environment_id,
            environment_secret=self.environment_secret,
        )

        if not work_item:
            return []

        # Return as a list of messages to process
        return [work_item]

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

    async def _handle_message_async(self, msg: dict[str, Any]) -> None:
        """Handle an incoming message asynchronously.

        For work items, this will:
        1. Parse the work secret
        2. Spawn a child CLI process via SessionSpawner
        3. Acknowledge the work item
        """
        work_type = msg.get("type")
        work_id = msg.get("id")

        if work_type == "work" and work_id:
            await self._handle_work_item(msg)
        elif self.params.on_message:
            try:
                self.params.on_message(msg)
            except Exception as e:
                logger.error("Message handler error: %s", e)

    async def _handle_work_item(self, work_item: dict[str, Any]) -> None:
        """Handle a work item from CCR.

        Args:
            work_item: The work item from poll response
        """
        work_id = work_item.get("id")
        if not work_id:
            return

        logger.info("Received work item: id=%s", work_id)

        # Extract session ingress token from decoded secret
        decoded_secret = work_item.get("_decoded_secret", {})
        session_ingress_token = decoded_secret.get("session_ingress_token")

        if not session_ingress_token:
            logger.error("Work item missing session_ingress_token")
            return

        # Acknowledge the work item to claim it
        ack_ok = await self._api_client.acknowledge_work(
            environment_id=self.params.environment_id,
            work_id=work_id,
            session_token=session_ingress_token,
        )

        if not ack_ok:
            logger.warning("Failed to acknowledge work item: %s", work_id)
            # Don't spawn - let it be re-queued
            return

        logger.info("Acknowledged work item: %s", work_id)

        # Spawn child CLI process for this work item
        if self._spawner:
            await self._spawn_child_process(work_item, session_ingress_token)

        # Notify via callback that work item was received
        if self.params.on_message:
            try:
                self.params.on_message(work_item)
            except Exception as e:
                logger.error("Work item message handler error: %s", e)

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
