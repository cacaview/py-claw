"""Remote service module for CCR (Claude Code Remote) session management.

This module provides:
- SessionsWebSocket: WebSocket client for CCR session subscriptions
- RemoteSessionManager: Manages remote CCR sessions with permission handling
- Message adapter: Converts between SDK and internal message types
- Permission bridge: Handles permission requests for remote sessions
"""

from __future__ import annotations

from py_claw.services.remote.session_manager import (
    RemoteSessionConfig,
    RemoteSessionCallbacks,
    RemoteSessionManager,
)
from py_claw.services.remote.types import (
    RemoteMessage,
    RemotePermissionResponse,
    WebSocketState,
)
from py_claw.services.remote.websocket import SessionsWebSocket

__all__ = [
    "RemoteSessionConfig",
    "RemoteSessionCallbacks",
    "RemoteSessionManager",
    "RemoteMessage",
    "RemotePermissionResponse",
    "WebSocketState",
    "SessionsWebSocket",
]
