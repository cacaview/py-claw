"""Global REPL bridge handle pointer.

Provides a global pointer to the active REPL bridge handle so callers
outside the React tree (tools, slash commands) can invoke handle methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.services.bridge.types import ReplBridgeHandle


# Global handle pointer
_handle: "ReplBridgeHandle | None" = None


def set_repl_bridge_handle(h: "ReplBridgeHandle | None") -> None:
    """Set the global REPL bridge handle.

    Args:
        h: The handle to set, or None to clear.
    """
    global _handle
    _handle = h


def get_repl_bridge_handle() -> "ReplBridgeHandle | None":
    """Get the current global REPL bridge handle.

    Returns:
        The current handle, or None if not set.
    """
    return _handle


def get_self_bridge_compat_id() -> str | None:
    """Get our own bridge session ID in session_* compat format.

    Returns:
        The compat session ID, or None if bridge isn't connected.
    """
    h = get_repl_bridge_handle()
    if h is None:
        return None

    # Import here to avoid circular dependency
    from py_claw.services.bridge.session_id_compat import to_compat_session_id

    return to_compat_session_id(h.bridge_session_id)
