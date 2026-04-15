"""
Leader Permission Bridge

Module-level bridge that allows the REPL to register its permission queue
and permission context setter functions for in-process teammates to use.

When an in-process teammate requests permissions, it uses the standard
permission dialog rather than a worker-specific UI. This bridge makes the
REPL's queue setter and permission context setter accessible from non-React code.

Based on ClaudeCode-main/src/utils/swarm/leaderPermissionBridge.ts
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from py_claw.types import ToolPermissionContext


# Module-level setters
_registered_confirm_queue_setter: Optional[Callable[[list], None]] = None
_registered_permission_context_setter: Optional[Callable[..., None]] = None


def register_leader_tool_use_confirm_queue(
    setter: Callable[[list], None],
) -> None:
    """
    Register the leader's ToolUseConfirm queue setter.

    This allows in-process teammates to add permission requests to the
    leader's confirmation queue.
    """
    global _registered_confirm_queue_setter
    _registered_confirm_queue_setter = setter


def get_leader_tool_use_confirm_queue() -> Optional[Callable[[list], None]]:
    """Get the registered leader ToolUseConfirm queue setter."""
    return _registered_confirm_queue_setter


def unregister_leader_tool_use_confirm_queue() -> None:
    """Unregister the leader's ToolUseConfirm queue setter."""
    global _registered_confirm_queue_setter
    _registered_confirm_queue_setter = None


def register_leader_set_tool_permission_context(
    setter: Callable[..., None],
) -> None:
    """
    Register the leader's setToolPermissionContext setter.

    This allows in-process teammates to update the leader's permission context.
    """
    global _registered_permission_context_setter
    _registered_permission_context_setter = setter


def get_leader_set_tool_permission_context() -> Optional[Callable[..., None]]:
    """Get the registered leader setToolPermissionContext setter."""
    return _registered_permission_context_setter


def unregister_leader_set_tool_permission_context() -> None:
    """Unregister the leader's setToolPermissionContext setter."""
    global _registered_permission_context_setter
    _registered_permission_context_setter = None


__all__ = [
    "register_leader_tool_use_confirm_queue",
    "get_leader_tool_use_confirm_queue",
    "unregister_leader_tool_use_confirm_queue",
    "register_leader_set_tool_permission_context",
    "get_leader_set_tool_permission_context",
    "unregister_leader_set_tool_permission_context",
]
