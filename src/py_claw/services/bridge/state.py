"""Bridge global state management.

Manages the global bridge state including active sessions, handles,
and connection state.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from py_claw.services.bridge.types import BridgeState

if TYPE_CHECKING:
    from py_claw.services.bridge.types import (
        BridgeSession,
        ReplBridgeHandle,
        SessionBridgeId,
    )


# ---------------------------------------------------------------------------
# State Storage
# ---------------------------------------------------------------------------


@dataclass
class BridgeStateStorage:
    """Thread-safe global bridge state."""

    # Active bridge sessions: session_id -> BridgeSession
    _sessions: dict[str, BridgeSession] = field(default_factory=dict)
    # Active REPL bridge handles: session_id -> ReplBridgeHandle
    _handles: dict[str, ReplBridgeHandle] = field(default_factory=dict)
    # Session to bridge ID mappings
    _session_bridge_ids: dict[str, SessionBridgeId] = field(default_factory=dict)
    # Global bridge connection state
    _global_state: BridgeState = field(default=BridgeState.DISCONNECTED)
    # Lock for thread safety
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def add_session(self, session: BridgeSession) -> None:
        """Add a bridge session."""
        with self._lock:
            self._sessions[session.session_id] = session

    def get_session(self, session_id: str) -> BridgeSession | None:
        """Get a bridge session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def update_session(self, session_id: str, **updates: object) -> bool:
        """Update session fields."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            for key, value in updates.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            return True

    def remove_session(self, session_id: str) -> bool:
        """Remove a bridge session."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions.pop(session_id)
                return True
            return False

    def list_sessions(self) -> list[BridgeSession]:
        """List all bridge sessions."""
        with self._lock:
            return list(self._sessions.values())

    def get_sessions_by_state(
        self, state: BridgeState
    ) -> list[BridgeSession]:
        """Get all sessions in a specific state."""
        with self._lock:
            return [s for s in self._sessions.values() if s.state == state]

    # ------------------------------------------------------------------
    # Handle management
    # ------------------------------------------------------------------

    def add_handle(self, handle: ReplBridgeHandle) -> None:
        """Add a REPL bridge handle."""
        with self._lock:
            self._handles[handle.bridge_session_id] = handle

    def get_handle(self, bridge_session_id: str) -> ReplBridgeHandle | None:
        """Get a REPL bridge handle by bridge session ID."""
        with self._lock:
            return self._handles.get(bridge_session_id)

    def remove_handle(self, bridge_session_id: str) -> bool:
        """Remove a REPL bridge handle."""
        with self._lock:
            if bridge_session_id in self._handles:
                self._handles.pop(bridge_session_id)
                return True
            return False

    def list_handles(self) -> list[ReplBridgeHandle]:
        """List all active REPL bridge handles."""
        with self._lock:
            return list(self._handles.values())

    # ------------------------------------------------------------------
    # Session bridge ID mapping
    # ------------------------------------------------------------------

    def set_session_bridge_id(self, mapping: SessionBridgeId) -> None:
        """Set a session to bridge ID mapping."""
        with self._lock:
            self._session_bridge_ids[mapping.session_id] = mapping

    def get_bridge_id(self, session_id: str) -> str | None:
        """Get bridge ID for a session."""
        with self._lock:
            mapping = self._session_bridge_ids.get(session_id)
            return mapping.bridge_id if mapping else None

    def get_session_bridge_id(
        self, session_id: str
    ) -> SessionBridgeId | None:
        """Get full session to bridge ID mapping."""
        with self._lock:
            return self._session_bridge_ids.get(session_id)

    def remove_session_bridge_id(self, session_id: str) -> bool:
        """Remove a session to bridge ID mapping."""
        with self._lock:
            if session_id in self._session_bridge_ids:
                self._session_bridge_ids.pop(session_id)
                return True
            return False

    # ------------------------------------------------------------------
    # Global state
    # ------------------------------------------------------------------

    def get_global_state(self) -> BridgeState:
        """Get the global bridge state."""
        with self._lock:
            return self._global_state

    def set_global_state(self, state: BridgeState) -> None:
        """Set the global bridge state."""
        with self._lock:
            self._global_state = state

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear_all(self) -> None:
        """Clear all state."""
        with self._lock:
            self._sessions.clear()
            self._handles.clear()
            self._session_bridge_ids.clear()
            self._global_state = BridgeState.DISCONNECTED


# ---------------------------------------------------------------------------
# Global state singleton
# ---------------------------------------------------------------------------

_state: BridgeStateStorage | None = None


def get_bridge_state() -> BridgeStateStorage:
    """Get the global bridge state singleton."""
    global _state
    if _state is None:
        _state = BridgeStateStorage()
    return _state


def reset_bridge_state() -> None:
    """Reset the global bridge state (for testing)."""
    global _state
    _state = None
