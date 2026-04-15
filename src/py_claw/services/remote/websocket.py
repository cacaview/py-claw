"""WebSocket client for CCR session subscriptions.

This module provides SessionsWebSocket - a WebSocket client that connects to
CCR (Claude Code Remote) sessions via /v1/sessions/ws/{id}/subscribe.

Protocol:
1. Connect to wss://api.anthropic.com/v1/sessions/ws/{sessionId}/subscribe?organization_uuid=...
2. Send auth message: { type: 'auth', credential: { type: 'oauth', token: '...' } }
3. Receive SDKMessage stream from the session
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from py_claw.services.remote.types import (
    RemoteAuthMessage,
    RemoteCredential,
    WebSocketState,
)

logger = logging.getLogger(__name__)

# Reconnection constants
RECONNECT_DELAY_MS = 2000
MAX_RECONNECT_ATTEMPTS = 5
PING_INTERVAL_MS = 30000

# Permanent close codes - server-side rejection, stop reconnecting
PERMANENT_CLOSE_CODES = {4003}  # unauthorized


@dataclass
class SessionsWebSocketCallbacks:
    """Callbacks for SessionsWebSocket events."""

    on_message: Callable[[dict[str, Any]], None]
    on_close: Callable[[], None] | None = None
    on_error: Callable[[Exception], None] | None = None
    on_connected: Callable[[], None] | None = None
    on_reconnecting: Callable[[], None] | None = None


@dataclass
class SessionsWebSocketConfig:
    """Configuration for SessionsWebSocket."""

    session_id: str
    org_uuid: str
    get_access_token: Callable[[], str]
    base_url: str = "wss://api.anthropic.com"
    reconnect_delay_ms: int = RECONNECT_DELAY_MS
    max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS
    ping_interval_ms: int = PING_INTERVAL_MS


class SessionsWebSocket:
    """WebSocket client for CCR session subscriptions.

    Manages WebSocket lifecycle including:
    - Connection establishment with auth
    - Message sending/receiving
    - Automatic reconnection with backoff
    - Ping/pong heartbeat
    """

    def __init__(self, config: SessionsWebSocketConfig, callbacks: SessionsWebSocketCallbacks):
        self.config = config
        self.callbacks = callbacks
        self.state = WebSocketState.CLOSED
        self._websocket: Any = None  # Will be set when connected
        self._reconnect_attempts = 0
        self._reconnect_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._running = False
        self._send_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self.state == WebSocketState.CONNECTED

    async def connect(self) -> bool:
        """Establish WebSocket connection and authenticate.

        Returns:
            True if connection successful
        """
        if self.state == WebSocketState.CONNECTING:
            return False

        self.state = WebSocketState.CONNECTING
        self._running = True

        try:
            # Build WebSocket URL
            url = (
                f"{self.config.base_url}/v1/sessions/ws/{self.config.session_id}"
                f"/subscribe?organization_uuid={self.config.org_uuid}"
            )

            # Get auth token
            token = self.config.get_access_token()
            if not token:
                logger.error("No access token available for WebSocket auth")
                self.state = WebSocketState.CLOSED
                return False

            # Connect to WebSocket
            async with self._create_websocket(url) as ws:
                self._websocket = ws

                # Send auth message
                auth_msg = RemoteAuthMessage(
                    credential=RemoteCredential(type="oauth", token=token)
                )
                await ws.send(json.dumps(self._auth_to_dict(auth_msg)))

                # Wait for auth confirmation (server sends a message back)
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    msg_data = json.loads(msg)

                    # Check if auth was successful
                    if msg_data.get("type") == "error":
                        logger.error("WebSocket auth failed: %s", msg_data.get("message"))
                        self.state = WebSocketState.CLOSED
                        return False

                except asyncio.TimeoutError:
                    logger.error("WebSocket auth timeout")
                    self.state = WebSocketState.CLOSED
                    return False

                # Connected successfully
                self.state = WebSocketState.CONNECTED
                self._reconnect_attempts = 0

                if self.callbacks.on_connected:
                    self.callbacks.on_connected()

                # Start ping task
                self._ping_task = asyncio.create_task(self._ping_loop())

                # Start message handler
                asyncio.create_task(self._receive_loop())

                # Process queued messages
                asyncio.create_task(self._send_loop())

                return True

        except Exception as e:
            logger.error("WebSocket connection error: %s", e)
            self.state = WebSocketState.CLOSED

            if self.callbacks.on_error:
                self.callbacks.on_error(e)

            return False

    async def _create_websocket(self, url: str) -> Any:
        """Create WebSocket connection.

        Override this method in tests to use a mock.
        """
        import websockets

        return await websockets.connect(url)

    async def _receive_loop(self) -> None:
        """Main loop for receiving messages from WebSocket."""
        while self._running and self.state == WebSocketState.CONNECTED:
            try:
                if self._websocket is None:
                    break

                msg = await self._websocket.recv()
                msg_data = json.loads(msg)

                # Check for close codes
                if isinstance(msg_data, dict) and msg_data.get("type") == "close":
                    code = msg_data.get("code", 0)
                    if code in PERMANENT_CLOSE_CODES:
                        logger.error("Permanent close code received: %d", code)
                        await self._close()
                        return

                # Dispatch message
                self.callbacks.on_message(msg_data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.error("WebSocket receive error: %s", e)
                    await self._handle_disconnect()
                break

    async def _send_loop(self) -> None:
        """Process queued outgoing messages."""
        while self._running and self.state == WebSocketState.CONNECTED:
            try:
                msg = await self._send_queue.get()
                if self._websocket and self.state == WebSocketState.CONNECTED:
                    await self._websocket.send(json.dumps(msg))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("WebSocket send error: %s", e)

    async def _ping_loop(self) -> None:
        """Send periodic ping to keep connection alive."""
        while self._running and self.state == WebSocketState.CONNECTED:
            try:
                await asyncio.sleep(self.config.ping_interval_ms / 1000.0)
                if self._websocket and self.state == WebSocketState.CONNECTED:
                    await self._websocket.ping()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("WebSocket ping error: %s", e)

    async def send(self, message: dict[str, Any]) -> bool:
        """Send a message to the WebSocket.

        Args:
            message: Message object to send

        Returns:
            True if message was queued successfully
        """
        if self.state != WebSocketState.CONNECTED:
            return False

        await self._send_queue.put(message)
        return True

    async def _handle_disconnect(self) -> None:
        """Handle unexpected WebSocket disconnect."""
        if not self._running:
            return

        self.state = WebSocketState.CLOSED

        # Check if we should reconnect
        if self._reconnect_attempts < self.config.max_reconnect_attempts:
            self._reconnect_attempts += 1

            if self.callbacks.on_reconnecting:
                self.callbacks.on_reconnecting()

            # Schedule reconnect
            self._reconnect_task = asyncio.create_task(self._reconnect())
        else:
            logger.error("Max reconnect attempts reached")
            await self._close()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with backoff."""
        delay = self.config.reconnect_delay_ms / 1000.0 * (2 ** (self._reconnect_attempts - 1))
        logger.info("Reconnecting in %.1f seconds (attempt %d)", delay, self._reconnect_attempts)

        await asyncio.sleep(delay)

        if self._running:
            self.state = WebSocketState.CONNECTING
            await self.connect()

    async def _close(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        self.state = WebSocketState.CLOSED

        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
            self._websocket = None

        if self.callbacks.on_close:
            self.callbacks.on_close()

    async def close(self) -> None:
        """Close the WebSocket connection gracefully."""
        self._running = False

        # Cancel pending tasks
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None

        await self._close()

    def _auth_to_dict(self, auth: RemoteAuthMessage) -> dict[str, Any]:
        """Convert auth message to dict."""
        return {
            "type": auth.type,
            "credential": {
                "type": auth.credential.type,
                "token": auth.credential.token,
            },
        }
