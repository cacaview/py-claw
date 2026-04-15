"""
WebSocket transport implementation for CLI remote communication.

Provides WebSocket-based transport for connecting to remote
Claude Code sessions with automatic reconnection support.

Reference: ClaudeCode-main/src/cli/transports/WebSocketTransport.ts
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .base import Transport

logger = logging.getLogger(__name__)

# Keep-alive frame content
KEEP_ALIVE_FRAME = '{"type":"keep_alive"}\n'

# Reconnection settings
DEFAULT_MAX_BUFFER_SIZE = 1000
DEFAULT_BASE_RECONNECT_DELAY = 1.0  # seconds
DEFAULT_MAX_RECONNECT_DELAY = 30.0  # seconds
DEFAULT_RECONNECT_GIVE_UP_MS = 600_000  # 10 minutes
DEFAULT_PING_INTERVAL = 10.0  # seconds
DEFAULT_KEEPALIVE_INTERVAL = 300.0  # 5 minutes

# Permanent close codes that should not trigger reconnection
PERMANENT_CLOSE_CODES = {1002, 4001, 4003}


class WebSocketTransportState:
    """WebSocket transport state values."""
    IDLE = "idle"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"
    CLOSED = "closed"


class WebSocketTransport(Transport):
    """
    WebSocket-based transport for remote CLI sessions.

    Features:
    - Automatic reconnection with exponential backoff
    - Keep-alive ping/pong
    - Connection state management
    - Event handlers for data, close, and connect
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        auto_reconnect: bool = True,
        session_id: str | None = None,
    ) -> None:
        """
        Initialize WebSocket transport.

        Args:
            url: WebSocket server URL
            headers: Optional headers to include in handshake
            auto_reconnect: Whether to automatically reconnect on disconnect
            session_id: Optional session ID for logging
        """
        self._url = url
        self._headers = headers or {}
        self._auto_reconnect = auto_reconnect
        self._session_id = session_id

        self._ws: Any = None  # WebSocket connection
        self._state = WebSocketTransportState.IDLE
        self._reconnect_attempts = 0
        self._reconnect_start_time: float | None = None
        self._reconnect_timer: asyncio.Task | None = None
        self._last_activity_time: float = 0.0
        self._ping_interval: asyncio.Task | None = None
        self._pong_received = True
        self._last_sent_id: str | None = None

    @property
    def state(self) -> str:
        """Get current connection state."""
        return self._state

    @property
    def session_id(self) -> str | None:
        """Get session ID."""
        return self._session_id

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if self._state in (WebSocketTransportState.CONNECTED, WebSocketTransportState.RECONNECTING):
            return

        try:
            import websockets

            self._state = WebSocketTransportState.CONNECTED
            self._last_activity_time = asyncio.get_event_loop().time()

            # Build connection headers
            headers = dict(self._headers)

            # Connect with headers
            self._ws = await websockets.connect(
                self._url,
                extra_headers=headers,
                ping_interval=None,  # We handle ping manually
            )

            self._state = WebSocketTransportState.CONNECTED
            self._notify_connect()
            self._start_ping_loop()

            # Start receiving in background
            asyncio.create_task(self._receive_loop())

            logger.debug(f"WebSocket connected to {self._url}")

        except Exception as e:
            self._state = WebSocketTransportState.CLOSED
            self._notify_close()
            raise

    def _start_ping_loop(self) -> None:
        """Start the ping interval loop."""
        if self._ping_interval:
            self._ping_interval.cancel()

        async def ping_loop():
            while self._state == WebSocketTransportState.CONNECTED:
                await asyncio.sleep(DEFAULT_PING_INTERVAL)
                if self._state == WebSocketTransportState.CONNECTED:
                    try:
                        if self._ws:
                            await self._ws.ping()
                            self._pong_received = False
                    except Exception:
                        break

        self._ping_interval = asyncio.create_task(ping_loop())

    async def _receive_loop(self) -> None:
        """Background task to receive messages."""
        try:
            async for message in self._ws:
                self._last_activity_time = asyncio.get_event_loop().time()
                self._notify_data(message)

        except Exception as e:
            logger.debug(f"WebSocket receive error: {e}")

        finally:
            if self._state == WebSocketTransportState.CONNECTED:
                self._handle_disconnect()

    def _handle_disconnect(self) -> None:
        """Handle unexpected disconnection."""
        if self._state == WebSocketTransportState.CLOSING:
            return

        self._state = WebSocketTransportState.CLOSED
        self._notify_close()

        if self._auto_reconnect:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt with exponential backoff."""
        if self._state == WebSocketTransportState.RECONNECTING:
            return

        # Check if we've exceeded the retry window
        now = asyncio.get_event_loop().time()
        if self._reconnect_start_time is None:
            self._reconnect_start_time = now

        elapsed_ms = (now - self._reconnect_start_time) * 1000
        if elapsed_ms > DEFAULT_RECONNECT_GIVE_UP_MS:
            logger.debug("Reconnection give-up period exceeded")
            return

        # Calculate delay with exponential backoff
        delay = min(
            DEFAULT_BASE_RECONNECT_DELAY * (2 ** self._reconnect_attempts),
            DEFAULT_MAX_RECONNECT_DELAY,
        )
        self._reconnect_attempts += 1

        self._state = WebSocketTransportState.RECONNECTING

        async def reconnect_after():
            await asyncio.sleep(delay)
            if self._state == WebSocketTransportState.RECONNECTING:
                try:
                    await self.connect()
                    self._reconnect_attempts = 0
                    self._reconnect_start_time = None
                except Exception:
                    pass

        self._reconnect_timer = asyncio.create_task(reconnect_after())

    async def send(self, data: str) -> None:
        """
        Send data over WebSocket.

        Args:
            data: JSON string data to send

        Raises:
            Exception: If send fails or not connected
        """
        if self._state != WebSocketTransportState.CONNECTED:
            raise RuntimeError(f"Cannot send: not connected (state={self._state})")

        try:
            await self._ws.send(data)
            self._last_activity_time = asyncio.get_event_loop().time()
        except Exception as e:
            self._handle_disconnect()
            raise

    def close(self) -> None:
        """
        Close the WebSocket connection.

        This stops reconnection attempts and closes the connection.
        """
        self._state = WebSocketTransportState.CLOSING

        # Cancel timers
        if self._ping_interval:
            self._ping_interval.cancel()
            self._ping_interval = None

        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None

        # Close websocket
        if self._ws:
            try:
                import websockets
                asyncio.create_task(self._ws.close())
            except Exception:
                pass

        self._state = WebSocketTransportState.CLOSED
        self._notify_close()

    def __repr__(self) -> str:
        return f"WebSocketTransport(url={self._url}, state={self._state})"
