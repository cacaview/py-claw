"""Peer sessions management for multi-session bridge.

Manages peer sessions in a bridge environment, allowing sessions to
discover and communicate with other active sessions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from py_claw.services.bridge.state import get_bridge_state

if TYPE_CHECKING:
    from py_claw.services.bridge.types import BridgeSession

logger = logging.getLogger(__name__)


# Maximum number of peer sessions to track
MAX_PEER_SESSIONS = 32


@dataclass
class PeerSessionInfo:
    """Information about a peer session."""

    session_id: str
    environment_id: str
    title: str | None = None
    machine_name: str | None = None
    state: str = "unknown"
    created_at: datetime | None = None
    last_activity: datetime | None = None
    is_local: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PeerSessionsManager:
    """Manager for peer sessions in a bridge context.

    Tracks all active peer sessions and provides methods to query
    and manage them.
    """

    # Maximum number of peers to track
    _max_peers: int = MAX_PEER_SESSIONS
    # Cache of peer sessions
    _peer_cache: dict[str, PeerSessionInfo] = field(default_factory=dict)
    # Last update time
    _last_update: datetime | None = None

    def add_peer(self, session: BridgeSession | PeerSessionInfo) -> None:
        """Add or update a peer session.

        Args:
            session: The session to add
        """
        from py_claw.services.bridge.types import BridgeSession as BridgeSessionType

        if isinstance(session, BridgeSessionType):
            peer = PeerSessionInfo(
                session_id=session.session_id,
                environment_id=session.environment_id,
                title=session.title,
                machine_name=session.machine_name,
                state=session.state.value if hasattr(session.state, 'value') else str(session.state),
                created_at=session.created_at,
                last_activity=session.updated_at or session.created_at,
                is_local=True,
            )
        else:
            peer = session

        self._peer_cache[peer.session_id] = peer
        self._last_update = datetime.utcnow()

    def remove_peer(self, session_id: str) -> bool:
        """Remove a peer session.

        Args:
            session_id: The session ID to remove

        Returns:
            True if removed, False if not found
        """
        if session_id in self._peer_cache:
            del self._peer_cache[session_id]
            self._last_update = datetime.utcnow()
            return True
        return False

    def get_peer(self, session_id: str) -> PeerSessionInfo | None:
        """Get a peer session by ID.

        Args:
            session_id: The session ID to look up

        Returns:
            Peer session info or None if not found
        """
        return self._peer_cache.get(session_id)

    def list_peers(
        self,
        include_local: bool = True,
        state_filter: str | None = None,
    ) -> list[PeerSessionInfo]:
        """List all peer sessions.

        Args:
            include_local: Whether to include local sessions
            state_filter: Optional state to filter by

        Returns:
            List of peer session info objects
        """
        peers = list(self._peer_cache.values())

        if not include_local:
            peers = [p for p in peers if not p.is_local]

        if state_filter:
            peers = [p for p in peers if p.state == state_filter]

        return peers

    def get_peer_count(self) -> int:
        """Get the number of tracked peer sessions."""
        return len(self._peer_cache)

    def clear_peers(self) -> None:
        """Clear all peer sessions."""
        self._peer_cache.clear()
        self._last_update = datetime.utcnow()


# Global manager instance
_peer_manager: PeerSessionsManager | None = None


def get_peer_sessions_manager() -> PeerSessionsManager:
    """Get the global peer sessions manager singleton."""
    global _peer_manager
    if _peer_manager is None:
        _peer_manager = PeerSessionsManager()
    return _peer_manager


def reset_peer_sessions_manager() -> None:
    """Reset the global manager (for testing)."""
    global _peer_manager
    _peer_manager = None


def list_peer_sessions() -> list[dict[str, Any]]:
    """List all peer sessions as dictionaries.

    This is the main entry point for listing peer sessions,
    compatible with the TypeScript listPeerSessions() function.

    Returns:
        List of peer session dictionaries
    """
    manager = get_peer_sessions_manager()

    # Refresh from bridge state
    bridge_state = get_bridge_state()
    sessions = bridge_state.list_sessions()

    for session in sessions:
        manager.add_peer(session)

    peers = manager.list_peers()
    return [
        {
            "session_id": p.session_id,
            "environment_id": p.environment_id,
            "title": p.title,
            "machine_name": p.machine_name,
            "state": p.state,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "last_activity": p.last_activity.isoformat() if p.last_activity else None,
            "is_local": p.is_local,
        }
        for p in peers
    ]


def get_peer_session(session_id: str) -> dict[str, Any] | None:
    """Get a specific peer session by ID.

    Args:
        session_id: The session ID to look up

    Returns:
        Peer session dictionary or None if not found
    """
    manager = get_peer_sessions_manager()
    peer = manager.get_peer(session_id)

    if not peer:
        # Try refreshing from bridge state
        bridge_state = get_bridge_state()
        session = bridge_state.get_session(session_id)
        if session:
            manager.add_peer(session)
            peer = manager.get_peer(session_id)

    if not peer:
        return None

    return {
        "session_id": peer.session_id,
        "environment_id": peer.environment_id,
        "title": peer.title,
        "machine_name": peer.machine_name,
        "state": peer.state,
        "created_at": peer.created_at.isoformat() if peer.created_at else None,
        "last_activity": peer.last_activity.isoformat() if peer.last_activity else None,
        "is_local": peer.is_local,
    }
