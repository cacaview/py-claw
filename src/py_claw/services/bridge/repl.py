"""REPL bridge core implementation.

Provides v1/v2 path dispatch, UUID dedup, and FlushGate mechanism
for Remote Control session management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from py_claw.services.bridge.config import get_bridge_config
from py_claw.services.bridge.enabled import is_env_less_bridge_enabled
from py_claw.services.bridge.state import get_bridge_state
from py_claw.services.bridge.types import (
    BridgeConfig,
    BridgeState,
    ReplBridgeHandle,
    SessionEvent,
)

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

    # Number of pending flush operations
    _pending: int = 0
    # Event triggered when all flushes complete
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    # Lock for thread-safe access
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
        # Evict oldest if over capacity
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

    # Configuration
    config: BridgeConfig
    # Bridge session ID
    bridge_session_id: str
    # Environment ID
    environment_id: str
    # Session ingress URL
    session_ingress_url: str
    # State
    state: BridgeState = BridgeState.DISCONNECTED
    # Flush gate for coordinating message flow
    _flush_gate: FlushGate = field(default_factory=FlushGate)
    # UUID deduplication set
    _seen_uuids: BoundedUUIDSet = field(default_factory=BoundedUUIDSet)
    # Callbacks
    _on_state_change: Callable[[BridgeState, str | None], None] | None = None
    _on_inbound_message: Callable[[dict[str, Any]], None] | None = None
    # Transport
    _transport: Any = None
    # Created timestamp
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_v2_path(self) -> bool:
        """Check if we should use the v2 (env-less) path."""
        return is_env_less_bridge_enabled()

    def set_state(self, new_state: BridgeState, detail: str | None = None) -> None:
        """Transition to a new bridge state."""
        old_state = self.state
        self.state = new_state
        logger.debug(
            "Bridge state transition: %s -> %s (%s)",
            old_state.value,
            new_state.value,
            detail,
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
        # SDK messages go through same path but with SDK envelope
        self.write_messages(messages)

    def send_result(self) -> None:
        """Send a result acknowledgment."""
        if self._transport:
            asyncio.create_task(self._transport.send_result())

    async def teardown(self) -> None:
        """Clean up bridge resources."""
        logger.info("Tearing down REPL bridge: %s", self.bridge_session_id)
        self.set_state(BridgeState.DISCONNECTED, "teardown")

        if self._transport:
            await self._transport.close()
            self._transport = None

    def to_handle(self) -> ReplBridgeHandle:
        """Convert to a ReplBridgeHandle for external use."""
        return ReplBridgeHandle(
            bridge_session_id=self.bridge_session_id,
            environment_id=self.environment_id,
            session_ingress_url=self.session_ingress_url,
            state=self.state,
            created_at=self.created_at,
        )


@dataclass
class ReplBridgeManager:
    """Manager for REPL bridge instances.

    Handles bridge lifecycle, reconnection, and state coordination.
    """

    # Active bridges: bridge_session_id -> ReplBridgeCore
    _bridges: dict[str, ReplBridgeCore] = field(default_factory=dict)
    # Lock for thread-safe access
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

        # Generate unique bridge session ID
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
            "Created REPL bridge: session_id=%s bridge_id=%s",
            environment_id,
            bridge_session_id,
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
