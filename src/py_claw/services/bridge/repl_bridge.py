"""REPL Bridge implementation.

Core bridge implementation for Remote Control sessions.
Handles v1/v2 path dispatch, UUID dedup, FlushGate mechanism,
message routing, and transport handling.

Based on ClaudeCode-main/src/bridge/replBridge.ts
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from py_claw.services.bridge.config import get_bridge_config
import logging

logger = logging.getLogger(__name__)
from py_claw.services.bridge.enabled import is_env_less_bridge_enabled
from py_claw.services.bridge.poll_config import get_poll_interval_config
from py_claw.services.bridge.poll_config_defaults import PollIntervalConfig
from py_claw.services.bridge.state import get_bridge_state
from py_claw.services.bridge.types import BridgeConfig, BridgeState

logger = logging.getLogger(__name__)


# Maximum activities to track
MAX_ACTIVITIES = 10

# Poll error recovery constants
POLL_ERROR_INITIAL_DELAY_MS = 2_000
POLL_ERROR_MAX_DELAY_MS = 60_000
POLL_ERROR_GIVE_UP_MS = 15 * 60 * 1000


@dataclass
class FlushGate:
    """Coordinates message flushing across multiple paths.

    The FlushGate ensures that messages are properly flushed before
    the bridge transitions states or closes.
    """

    _pending: int = 0
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def increment(self) -> None:
        """Start a pending flush operation."""
        self._pending += 1
        self._event.clear()

    def decrement(self) -> None:
        """Complete a pending flush operation."""
        if self._pending > 0:
            self._pending -= 1
        if self._pending == 0:
            self._event.set()

    async def wait(self) -> None:
        """Wait for all pending flush operations to complete."""
        await self._event.wait()


class BoundedUUIDSet:
    """Set that bounds memory usage by forgetting oldest entries."""

    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._uuids: list[str] = []
        self._seen: set[str] = set()

    def add(self, uuid: str) -> bool:
        """Add a UUID, returns True if it's new."""
        if uuid in self._seen:
            return False
        self._seen.add(uuid)
        self._uuids.append(uuid)
        while len(self._uuids) > self._max_size:
            old = self._uuids.pop(0)
            self._seen.discard(old)
        return True

    def __contains__(self, uuid: str) -> bool:
        return uuid in self._seen

    def __len__(self) -> int:
        return len(self._uuids)


@dataclass
class ReplBridgeCore:
    """REPL bridge core implementation.

    Manages the bridge lifecycle, message routing, and transport handling.
    """

    config: BridgeConfig
    bridge_session_id: str
    environment_id: str
    session_ingress_url: str
    state: BridgeState = BridgeState.DISCONNECTED
    _flush_gate: FlushGate = field(default_factory=FlushGate)
    _seen_uuids: BoundedUUIDSet = field(default_factory=BoundedUUIDSet)
    _on_state_change: Callable[[BridgeState, str | None], None] | None = None
    _on_inbound_message: Callable[[dict[str, Any]], None] | None = None
    _transport: Any = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_v2_path(self) -> bool:
        """Check if we should use the v2 (env-less) path."""
        return is_env_less_bridge_enabled()

    def set_state(self, new_state: BridgeState, detail: str | None = None) -> None:
        """Transition to a new bridge state."""
        old_state = self.state
        self.state = new_state
        logger.debug(
            f"Bridge state transition: {old_state.value} -> {new_state.value} ({detail})"
        )
        if self._on_state_change:
            self._on_state_change(new_state, detail)

    def write_messages(self, messages: list[dict[str, Any]]) -> None:
        """Write messages to the bridge transport.

        Args:
            messages: List of Message objects to send
        """
        if not self._transport:
            logger.warning("No transport configured for write_messages")
            return

        # Filter out duplicate UUIDs
        filtered = []
        for msg in messages:
            msg_uuid = msg.get("message_id") or msg.get("uuid")
            if msg_uuid and msg_uuid in self._seen_uuids:
                continue
            filtered.append(msg)
            if msg_uuid:
                self._seen_uuids.add(msg_uuid)

        if not filtered:
            return

        # Send via transport
        asyncio.create_task(self._transport.send_messages(filtered))

    def write_sdk_messages(self, messages: list[dict[str, Any]]) -> None:
        """Write SDK messages to the bridge transport.

        Args:
            messages: List of SDKMessage objects to send
        """
        self.write_messages(messages)

    def send_result(self) -> None:
        """Send a result acknowledgment."""
        if self._transport:
            asyncio.create_task(self._transport.send_result())

    async def teardown(self) -> None:
        """Clean up bridge resources."""
        logger.info(f"Tearing down REPL bridge: {self.bridge_session_id}")
        self.set_state(BridgeState.DISCONNECTED, "teardown")

        if self._transport:
            await self._transport.close()
            self._transport = None

    def to_handle(self) -> dict[str, Any]:
        """Convert to a handle dict for external use."""
        return {
            "bridge_session_id": self.bridge_session_id,
            "environment_id": self.environment_id,
            "session_ingress_url": self.session_ingress_url,
            "state": self.state.value if hasattr(self.state, 'value') else str(self.state),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class ReplBridgeManager:
    """Manager for REPL bridge instances.

    Handles bridge lifecycle, reconnection, and state coordination.
    """

    _bridges: dict[str, ReplBridgeCore] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def create_bridge(
        self,
        environment_id: str,
        session_ingress_url: str,
        title: str | None = None,
        git_repo_url: str | None = None,
        branch: str | None = None,
        permission_mode: str | None = None,
    ) -> ReplBridgeCore:
        """Create a new REPL bridge.

        Args:
            environment_id: The environment ID
            session_ingress_url: The session ingress URL
            title: Optional session title
            git_repo_url: Optional git repository URL
            branch: Optional git branch
            permission_mode: Optional permission mode

        Returns:
            The created ReplBridgeCore instance
        """
        config = get_bridge_config()
        bridge_session_id = str(uuid.uuid4())

        bridge = ReplBridgeCore(
            config=config,
            bridge_session_id=bridge_session_id,
            environment_id=environment_id,
            session_ingress_url=session_ingress_url,
        )

        async with self._lock:
            self._bridges[bridge_session_id] = bridge

        # Register in global state
        state = get_bridge_state()
        state.add_handle(bridge.to_handle())

        logger.info(
            f"Created REPL bridge: session_id={environment_id} bridge_id={bridge_session_id}"
        )

        return bridge

    async def get_bridge(
        self, bridge_session_id: str
    ) -> ReplBridgeCore | None:
        """Get a bridge by session ID."""
        async with self._lock:
            return self._bridges.get(bridge_session_id)

    async def remove_bridge(self, bridge_session_id: str) -> bool:
        """Remove a bridge by session ID."""
        async with self._lock:
            if bridge_session_id in self._bridges:
                bridge = self._bridges.pop(bridge_session_id)
                await bridge.teardown()
                return True
            return False

    async def list_bridges(self) -> list[ReplBridgeCore]:
        """List all active bridges."""
        async with self._lock:
            return list(self._bridges.values())

    async def close_all(self) -> None:
        """Close all bridges."""
        async with self._lock:
            for bridge in list(self._bridges.values()):
                await bridge.teardown()
            self._bridges.clear()


# Global manager instance
_manager: ReplBridgeManager | None = None


def get_repl_bridge_manager() -> ReplBridgeManager:
    """Get the global REPL bridge manager singleton."""
    global _manager
    if _manager is None:
        _manager = ReplBridgeManager()
    return _manager


def reset_repl_bridge_manager() -> None:
    """Reset the global manager (for testing)."""
    global _manager
    _manager = None


@dataclass
class BridgeCoreParams:
    """Explicit parameters for init_bridge_core.

    Everything initReplBridge reads from bootstrap state
    (cwd, session ID, git, OAuth) becomes a field here.
    """

    dir: str = ""
    machine_name: str = ""
    branch: str = ""
    title: str = ""
    base_url: str = ""
    session_ingress_url: str = ""
    worker_type: str = ""
    git_repo_url: str | None = None
    get_access_token: Callable[[], str | None] | None = None
    create_session: Callable[..., Any] | None = None
    archive_session: Callable[[str], Any] | None = None
    get_current_title: Callable[[], str] | None = None
    to_sdk_messages: Callable[[list], list] | None = None
    on_auth_401: Callable[[str], Any] | None = None
    get_poll_interval_config: Callable[[], PollIntervalConfig] | None = None
    initial_history_cap: int = 200
    initial_messages: list[dict[str, Any]] | None = None
    previously_flushed_uuids: set[str] | None = None
    on_inbound_message: Callable[[dict[str, Any]], None] | None = None
    on_permission_response: Callable[[dict[str, Any]], None] | None = None
    on_interrupt: Callable[[], None] | None = None
    on_set_model: Callable[[str | None], None] | None = None
    on_set_max_thinking_tokens: Callable[[int | None], None] | None = None
    on_set_permission_mode: Callable[[str], dict] | None = None
    on_state_change: Callable[[BridgeState, str | None], None] | None = None
    on_user_message: Callable[[str], bool] | None = None


async def init_bridge_core(
    params: BridgeCoreParams,
) -> ReplBridgeCore:
    """Initialize a REPL bridge core.

    Args:
        params: Bridge initialization parameters

    Returns:
        Initialized ReplBridgeCore
    """
    config = get_bridge_config()

    # Create bridge core
    bridge = ReplBridgeCore(
        config=config,
        bridge_session_id=str(uuid.uuid4()),
        environment_id="",  # Will be set after session creation
        session_ingress_url=params.session_ingress_url,
        _on_state_change=params.on_state_change,
        _on_inbound_message=params.on_inbound_message,
    )

    # Set up callbacks if provided
    if params.on_state_change:
        bridge._on_state_change = params.on_state_change

    if params.on_inbound_message:
        bridge._on_inbound_message = params.on_inbound_message

    # Transition to ready state
    bridge.set_state(BridgeState.READY, "initializing")

    # Create session if create_session is provided
    if params.create_session:
        try:
            session_id = await params.create_session(
                environment_id=bridge.environment_id,
                title=params.title,
                git_repo_url=params.git_repo_url,
                branch=params.branch,
            )
            if session_id:
                bridge.bridge_session_id = session_id
        except Exception as e:
            logger.error(f"Failed to create bridge session: {e}")
            bridge.set_state(BridgeState.FAILED, str(e))

    # Transition to connected
    bridge.set_state(BridgeState.CONNECTED, "initialized")

    # Register in manager
    manager = get_repl_bridge_manager()
    async with manager._lock:
        manager._bridges[bridge.bridge_session_id] = bridge

    return bridge


__all__ = [
    "FlushGate",
    "BoundedUUIDSet",
    "ReplBridgeCore",
    "ReplBridgeManager",
    "BridgeCoreParams",
    "get_repl_bridge_manager",
    "reset_repl_bridge_manager",
    "init_bridge_core",
]
