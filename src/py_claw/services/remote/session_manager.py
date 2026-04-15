"""Remote session manager for CCR (Claude Code Remote) sessions.

Coordinates:
- WebSocket subscription for receiving messages from CCR
- HTTP POST for sending user messages to CCR
- Permission request/response flow
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from py_claw.services.remote.types import (
    RemoteControlCancelRequest,
    RemoteControlRequest,
    RemoteControlResponse,
    RemotePermissionRequest,
    RemotePermissionResponse,
    SDKMessage,
)
from py_claw.services.remote.websocket import (
    SessionsWebSocket,
    SessionsWebSocketCallbacks,
    SessionsWebSocketConfig,
)

logger = logging.getLogger(__name__)

# Maximum retries for 4001 (session not found)
MAX_SESSION_NOT_FOUND_RETRIES = 3


@dataclass
class RemoteSessionConfig:
    """Configuration for a remote session."""

    session_id: str
    get_access_token: Callable[[], str]
    org_uuid: str
    has_initial_prompt: bool = False
    viewer_only: bool = False
    base_url: str = "https://api.anthropic.com"


@dataclass
class RemoteSessionCallbacks:
    """Callbacks for remote session events."""

    on_message: Callable[[dict[str, Any]], None]
    on_permission_request: Callable[[RemotePermissionRequest, str], None] | None = None
    on_permission_cancelled: Callable[[str, str | None], None] | None = None
    on_connected: Callable[[], None] | None = None
    on_disconnected: Callable[[], None] | None = None
    on_reconnecting: Callable[[], None] | None = None
    on_error: Callable[[Exception], None] | None = None


class RemoteSessionManager:
    """Manages a remote CCR session.

    Coordinates WebSocket subscription for incoming messages and HTTP POST
    for outgoing messages, with permission request handling.
    """

    def __init__(self, config: RemoteSessionConfig, callbacks: RemoteSessionCallbacks):
        self.config = config
        self.callbacks = callbacks
        self._websocket: SessionsWebSocket | None = None
        self._pending_permission_requests: dict[str, RemotePermissionRequest] = {}
        self._session_not_found_retries = 0
        self._running = False

    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self.config.session_id

    @property
    def is_connected(self) -> bool:
        """Check if session is connected."""
        return self._websocket is not None and self._websocket.is_connected

    async def connect(self) -> bool:
        """Connect to the remote session via WebSocket.

        Returns:
            True if connection successful
        """
        if self._running:
            logger.warning("Session manager already running")
            return False

        self._running = True
        self._session_not_found_retries = 0

        # Create WebSocket config
        ws_config = SessionsWebSocketConfig(
            session_id=self.config.session_id,
            org_uuid=self.config.org_uuid,
            get_access_token=self.config.get_access_token,
            base_url=self.config.base_url.replace("https://", "wss://").replace("http://", "ws://"),
        )

        # Create callbacks
        ws_callbacks = SessionsWebSocketCallbacks(
            on_message=self._handle_websocket_message,
            on_close=self._handle_close,
            on_error=self._handle_error,
            on_connected=self._handle_connected,
            on_reconnecting=self._handle_reconnecting,
        )

        self._websocket = SessionsWebSocket(ws_config, ws_callbacks)
        return await self._websocket.connect()

    async def disconnect(self) -> None:
        """Disconnect from the remote session."""
        self._running = False

        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        self._pending_permission_requests.clear()

    async def send_message(self, message: dict[str, Any]) -> bool:
        """Send a message to the remote session.

        Args:
            message: Message to send

        Returns:
            True if message was sent successfully
        """
        if not self._websocket or not self._websocket.is_connected:
            logger.error("Cannot send message: not connected")
            return False

        return await self._websocket.send(message)

    async def send_control_response(
        self,
        request_id: str,
        success: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        """Send a control response to the CCR session.

        Args:
            request_id: Request ID to respond to
            success: Whether the request was successful
            result: Result data if successful
            error: Error message if failed

        Returns:
            True if response was sent
        """
        response = RemoteControlResponse(
            type="control_response",
            request_id=request_id,
            success=success,
            result=result,
            error=error,
        )

        return await self.send_message({
            "type": response.type,
            "request_id": response.request_id,
            "success": response.success,
            "result": response.result,
            "error": response.error,
        })

    async def send_permission_response(
        self,
        request_id: str,
        behavior: str,
        updated_input: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> bool:
        """Send a permission response to the CCR session.

        Args:
            request_id: Request ID to respond to
            behavior: 'allow' or 'deny'
            updated_input: Updated input if allowing
            message: Error/denial message if denying

        Returns:
            True if response was sent
        """
        response = RemotePermissionResponse(
            behavior=behavior,
            updated_input=updated_input,
            message=message,
        )

        msg = {
            "type": "control_response",
            "request_id": request_id,
            "success": True,
            "result": {
                "behavior": response.behavior,
            },
        }

        if response.updated_input:
            msg["result"]["updated_input"] = response.updated_input
        if response.message:
            msg["result"]["message"] = response.message

        return await self.send_message(msg)

    def _handle_websocket_message(self, data: dict[str, Any]) -> None:
        """Handle incoming WebSocket message.

        Args:
            data: Message data from WebSocket
        """
        msg_type = data.get("type")

        # Check for session not found (can be transient during compaction)
        if data.get("code") == 4001:
            self._handle_session_not_found()
            return

        # Handle different message types
        if msg_type == "control_request":
            self._handle_control_request(data)
        elif msg_type == "control_cancel_request":
            self._handle_control_cancel_request(data)
        elif msg_type in ("sdk_message", "assistant", "system", "tool_use"):
            # SDK messages go to on_message callback
            self.callbacks.on_message(data)
        else:
            logger.debug("Unknown message type: %s", msg_type)

    def _handle_control_request(self, data: dict[str, Any]) -> None:
        """Handle incoming control request.

        Args:
            data: Control request data
        """
        request_id = data.get("request_id")
        action = data.get("action")

        if action == "permission":
            # Permission request
            request = RemotePermissionRequest(
                type=data.get("type"),
                request_id=request_id,
                action=action,
                params=data.get("params", {}),
            )
            self._pending_permission_requests[request_id] = request

            if self.callbacks.on_permission_request:
                self.callbacks.on_permission_request(request, request_id)
        else:
            # Other control requests - forward to on_message
            self.callbacks.on_message(data)

    def _handle_control_cancel_request(self, data: dict[str, Any]) -> None:
        """Handle control cancel request.

        Args:
            data: Cancel request data
        """
        request_id = data.get("request_id")
        tool_use_id = data.get("tool_use_id")

        # Remove from pending
        self._pending_permission_requests.pop(request_id, None)

        if self.callbacks.on_permission_cancelled:
            self.callbacks.on_permission_cancelled(request_id, tool_use_id)

    def _handle_session_not_found(self) -> None:
        """Handle session not found error with retry logic."""
        if self._session_not_found_retries < MAX_SESSION_NOT_FOUND_RETRIES:
            self._session_not_found_retries += 1
            logger.warning(
                "Session not found (attempt %d/%d), will retry",
                self._session_not_found_retries,
                MAX_SESSION_NOT_FOUND_RETRIES,
            )
        else:
            logger.error("Session not found after %d retries", MAX_SESSION_NOT_FOUND_RETRIES)
            if self.callbacks.on_error:
                self.callbacks.on_error(Exception("Session not found"))

    def _handle_close(self) -> None:
        """Handle WebSocket close."""
        if self.callbacks.on_disconnected:
            self.callbacks.on_disconnected()

    def _handle_error(self, error: Exception) -> None:
        """Handle WebSocket error.

        Args:
            error: Error that occurred
        """
        logger.error("WebSocket error: %s", error)
        if self.callbacks.on_error:
            self.callbacks.on_error(error)

    def _handle_connected(self) -> None:
        """Handle successful connection."""
        self._session_not_found_retries = 0
        if self.callbacks.on_connected:
            self.callbacks.on_connected()

    def _handle_reconnecting(self) -> None:
        """Handle reconnection event."""
        if self.callbacks.on_reconnecting:
            self.callbacks.on_reconnecting()
