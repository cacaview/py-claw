"""
Assistant service module.

Session discovery and assistant mode management.

Based on ClaudeCode-main/src/assistant/
"""
from py_claw.services.assistant.service import (
    create_session_info,
    discover_assistant_sessions,
    get_assistant_mode_config,
    get_assistant_mode_status,
    get_older_session_events,
    get_session_events,
    is_assistant_mode_enabled,
)
from py_claw.services.assistant.session_history import (
    create_history_auth_ctx,
    fetch_latest_events,
    fetch_older_events,
)
from py_claw.services.assistant.types import (
    HISTORY_PAGE_SIZE,
    AssistantModeConfig,
    HistoryAuthCtx,
    HistoryPage,
    SessionInfo,
)


__all__ = [
    # Service functions
    "create_session_info",
    "discover_assistant_sessions",
    "get_assistant_mode_config",
    "get_assistant_mode_status",
    "get_older_session_events",
    "get_session_events",
    "is_assistant_mode_enabled",
    # Session history
    "create_history_auth_ctx",
    "fetch_latest_events",
    "fetch_older_events",
    # Types
    "HISTORY_PAGE_SIZE",
    "AssistantModeConfig",
    "HistoryAuthCtx",
    "HistoryPage",
    "SessionInfo",
]
