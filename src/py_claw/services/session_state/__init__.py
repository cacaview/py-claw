"""Session state management.

Based on ClaudeCode-main/src/utils/sessionState.ts
"""

from py_claw.services.session_state.session_state import (
    RequiresActionDetails,
    SessionExternalMetadata,
    SessionState,
    get_session_state,
    notify_permission_mode_changed,
    notify_session_metadata_changed,
    notify_session_state_changed,
    set_permission_mode_changed_listener,
    set_session_metadata_changed_listener,
    set_session_state_changed_listener,
)

__all__ = [
    "SessionState",
    "RequiresActionDetails",
    "SessionExternalMetadata",
    "get_session_state",
    "notify_session_state_changed",
    "notify_session_metadata_changed",
    "notify_permission_mode_changed",
    "set_session_state_changed_listener",
    "set_session_metadata_changed_listener",
    "set_permission_mode_changed_listener",
]
