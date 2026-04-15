"""Remote service type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class WebSocketState(Enum):
    """WebSocket connection state."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSED = "closed"


class RemoteMessageType(Enum):
    """Types of messages from remote CCR sessions."""

    AUTH = "auth"
    CONTROL_REQUEST = "control_request"
    CONTROL_RESPONSE = "control_response"
    CONTROL_CANCEL_REQUEST = "control_cancel_request"
    SDK_MESSAGE = "sdk_message"


@dataclass
class RemoteCredential:
    """OAuth credential for remote session authentication."""

    type: str = "oauth"
    token: str | None = None


@dataclass
class RemoteAuthMessage:
    """Authentication message sent after WebSocket connection."""

    type: str = "auth"
    credential: RemoteCredential = field(default_factory=RemoteCredential)


@dataclass
class RemoteMessage:
    """Base class for messages from remote CCR sessions."""

    type: str
    data: dict[str, Any] | None = None


@dataclass
class RemoteControlRequest:
    """Control request from CCR session."""

    type: str = "control_request"
    request_id: str | None = None
    action: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RemoteControlResponse:
    """Control response to CCR session."""

    type: str = "control_response"
    request_id: str | None = None
    success: bool = True
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class RemoteControlCancelRequest:
    """Cancel request for a pending control request."""

    type: str = "control_cancel_request"
    request_id: str | None = None


@dataclass
class RemotePermissionRequest:
    """Permission request from CCR session."""

    type: str = "control_request"
    request_id: str | None = None
    action: str = "permission"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RemotePermissionResponse:
    """Permission response for remote session."""

    behavior: str  # "allow" or "deny"
    updated_input: dict[str, Any] | None = None
    message: str | None = None


@dataclass
class SDKMessage:
    """SDK message from CCR session."""

    type: str
    uuid: str | None = None
    message: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RemoteSessionInfo:
    """Information about a remote CCR session."""

    session_id: str
    org_uuid: str
    has_initial_prompt: bool = False
    viewer_only: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


# WebSocket callbacks type
RemoteWebSocketCallbacks = {
    "on_message": "Callable[[dict[str, Any]], None]",
    "on_close": "Callable[[], None] | None",
    "on_error": "Callable[[Exception], None] | None",
    "on_connected": "Callable[[], None] | None",
    "on_reconnecting": "Callable[[], None] | None",
}
