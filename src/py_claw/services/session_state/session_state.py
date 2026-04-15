"""Session state management.

Based on ClaudeCode-main/src/utils/sessionState.ts

Provides session state tracking for idle/running/requires_action transitions
with support for pending action details and external metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TypedDict

# Session state type
SessionState = str  # 'idle' | 'running' | 'requires_action'


class RequiresActionDetails(TypedDict, total=False):
    """Context carried with requires_action transitions."""

    tool_name: str
    action_description: str
    tool_use_id: str
    request_id: str
    input: dict | None


class SessionExternalMetadata(TypedDict, total=False):
    """External metadata for session state."""

    permission_mode: str | None
    is_ultraplan_mode: bool | None
    model: str | None
    pending_action: RequiresActionDetails | None
    post_turn_summary: object | None
    task_summary: str | None


# Listener types
SessionStateChangedListener = Callable[[SessionState, RequiresActionDetails | None], None]
SessionMetadataChangedListener = Callable[[SessionExternalMetadata], None]
PermissionModeChangedListener = Callable[[str], None]  # PermissionMode


# Module-level state
_state_listener: SessionStateChangedListener | None = None
_metadata_listener: SessionMetadataChangedListener | None = None
_permission_mode_listener: PermissionModeChangedListener | None = None

_has_pending_action = False
_current_state: SessionState = "idle"


def set_session_state_changed_listener(
    cb: SessionStateChangedListener | None,
) -> None:
    """Register a listener for session state changes."""
    global _state_listener
    _state_listener = cb


def set_session_metadata_changed_listener(
    cb: SessionMetadataChangedListener | None,
) -> None:
    """Register a listener for session metadata changes."""
    global _metadata_listener
    _metadata_listener = cb


def set_permission_mode_changed_listener(
    cb: PermissionModeChangedListener | None,
) -> None:
    """Register a listener for permission mode changes.

    Wired by print.ts to emit an SDK system:status message so CCR/IDE clients
    see mode transitions in real time.
    """
    global _permission_mode_listener
    _permission_mode_listener = cb


def get_session_state() -> SessionState:
    """Get the current session state."""
    return _current_state


def notify_session_state_changed(
    state: SessionState,
    details: RequiresActionDetails | None = None,
) -> None:
    """Notify that session state has changed.

    Mirrors details into external_metadata so GetSession carries the
    pending-action context without proto changes.
    """
    global _current_state, _has_pending_action

    _current_state = state

    if _state_listener:
        _state_listener(state, details)

    # Mirror details into external_metadata
    if state == "requires_action" and details:
        _has_pending_action = True
        if _metadata_listener:
            _metadata_listener({"pending_action": details})
    elif _has_pending_action:
        _has_pending_action = False
        if _metadata_listener:
            _metadata_listener({"pending_action": None})

    # Clear task_summary at idle so next turn doesn't briefly show previous turn's progress
    if state == "idle" and _metadata_listener:
        _metadata_listener({"task_summary": None})

    # Mirror to SDK event stream (only when CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS is set)
    # This is handled at the caller level in Python implementation


def notify_session_metadata_changed(
    metadata: SessionExternalMetadata,
) -> None:
    """Notify that session metadata has changed."""
    if _metadata_listener:
        _metadata_listener(metadata)


def notify_permission_mode_changed(mode: str) -> None:
    """Notify that permission mode has changed.

    Fired by onChangeAppState when toolPermissionContext.mode changes.
    Downstream listeners (CCR external_metadata PUT, SDK status stream) are
    both wired through this single choke point.
    """
    if _permission_mode_listener:
        _permission_mode_listener(mode)
