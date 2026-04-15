"""WebSocket transport using wsproto.

Provides a reconnecting WebSocket transport with ping/keep-alive
and graceful close. This is the base class for HybridTransport.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import wsproto
from wsproto import ConnectionType, WSConnection
from wsproto.connection import ConnectionState
from wsproto.events import (
    AcceptConnection,
    CloseConnection,
    Ping,
    Pong,
    Request,
    TextMessage,
)
from wsproto.extensions import PerMessageDeflate

from py_claw.services.transports.base import Transport

# Keep-alive frame
KEEP_ALIVE_FRAME = '{"type":"keep_alive"}\n'

# Close codes that indicate permanent server-side rejection
PERMANENT_CLOSE_CODES = {1002, 4001, 4003}

DEFAULT_PING_INTERVAL_MS = 10_000
DEFAULT_KEEPALIVE_INTERVAL_MS = 300_000


@dataclass
class WebSocketTransportOptions:
    """Options for WebSocketTransport."""

    # When false, no automatic reconnection on disconnect
    auto_reconnect: bool = True
    # For REPL bridge — enables bridge-specific telemetry
    is_bridge: bool = False


class WebSocketTransport(Transport):
    """WebSocket transport with auto-reconnect and ping/keep-alive.

    Subclasses extend this for specific protocol behaviours (e.g. HybridTransport
    which adds HTTP POST for writes).
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        options: WebSocketTransportOptions | None = None,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._opts = options or WebSocketTransportOptions()
        self._state: str = "idle"  # idle | connected | reconnecting | closing | closed
        self._ws: wsproto.WSConnection | None = None
        self._conn: asyncio.Protocol | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._ping_task: asyncio.Task | None = None
        self._recv_task: asyncio.Task | None = None
        self._data_handler: callable | None = None
        self._close_handler: callable | None = None
        self._close_code: int | None = None
        self._reconnect_delay_ms: int = 1000
        self._max_reconnect_delay_ms: int = 30_000

    @property
    def state(self) -> str:
        return self._state

    async def connect(self) -> None:
        if self._state in ("connected", "reconnecting"):
            return
        self._state = "reconnecting"
        await self._do_connect()
        if self._opts.auto_reconnect:
            self._start_ping_loop()

    async def _do_connect(self) -> None:
        """Establish the WebSocket connection."""
        try:
            url = self._url
            if not url.startswith("ws://") and not url.startswith("wss://"):
                url = f"wss://{url}"
            parsed = url.partition("://")[2] if "://" in url else url
            host_port = parsed.split("/", 1)
            host: str
            port_str: str
            if ":" in host_port[0]:
                host, port_str = host_port[0].split(":", 1)
                port = int(port_str)
            else:
                host = host_port[0]
                port = 443 if url.startswith("wss") else 80
            path = f"/{host_port[1]}" if len(host_port) > 1 else "/"

            use_ssl = url.startswith("wss")

            self._reader, self._writer = await asyncio.open_connection(
                host, port, ssl=use_ssl
            )

            # Build the HTTP upgrade request using wsproto
            request = Request(
                host=host,
                path=path,
                extensions=[PerMessageDeflate()],
            )
            for k, v in self._headers.items():
                request.extra_headers.append((k, v))

            self._ws = WSConnection(ConnectionType.CLIENT)
            self._ws.send(request)

            # Send the upgrade request
            data = self._ws.bytes_to_send()
            self._writer.write(data)
            await self._writer.drain()

            # Receive until connected
            while True:
                data = await self._reader.read(4096)
                if not data:
                    break
                self._ws.receive_data(data)
                for event in self._ws.events():
                    if isinstance(event, AcceptConnection):
                        self._state = "connected"
                        self._reconnect_delay_ms = 1000
                        return
                    elif isinstance(event, CloseConnection):
                        self._handle_close(event.code or 0)
                        return

        except Exception as exc:
            self._state = "idle"
            raise exc

    def _start_ping_loop(self) -> None:
        """Start the ping keep-alive loop."""
        if self._ping_task:
            self._ping_task.cancel()
        self._ping_task = asyncio.create_task(self._ping_loop())

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep the connection alive."""
        interval_s = DEFAULT_PING_INTERVAL_MS / 1000
        while self._state == "connected":
            await asyncio.sleep(interval_s)
            if self._state != "connected":
                break
            await self._send_ping()

    async def _send_ping(self) -> None:
        """Send a ping frame."""
        if self._ws is None:
            return
        try:
            ping = Ping()
            self._ws.send(ping)
            data = self._ws.bytes_to_send()
            if self._writer:
                self._writer.write(data)
                await self._writer.drain()
        except Exception:
            pass

    async def send(self, data: str) -> None:
        """Send a text message over WebSocket."""
        if self._state != "connected" or self._ws is None:
            return
        msg = TextMessage(data=data)
        self._ws.send(msg)
        bytes_data = self._ws.bytes_to_send()
        if self._writer:
            self._writer.write(bytes_data)
            await self._writer.drain()

    def on_data(self, handler: callable) -> None:
        """Register a handler for incoming text messages."""
        self._data_handler = handler
        if self._state == "connected":
            asyncio.create_task(self._recv_loop())

    def on_close(self, handler: callable) -> None:
        """Register a handler for connection close events."""
        self._close_handler = handler

    async def _recv_loop(self) -> None:
        """Receive and dispatch messages."""
        try:
            while self._state == "connected" and self._reader:
                try:
                    data = await asyncio.wait_for(self._reader.read(4096), timeout=30)
                except asyncio.TimeoutError:
                    continue
                if not data:
                    self._handle_close(1000)
                    break
                if self._ws:
                    self._ws.receive_data(data)
                    for event in self._ws.events():
                        if isinstance(event, TextMessage):
                            if self._data_handler:
                                self._data_handler(event.data)
                        elif isinstance(event, Pong):
                            pass
                        elif isinstance(event, CloseConnection):
                            self._handle_close(event.code or 0)
                        elif isinstance(event, AcceptConnection):
                            pass
        except Exception:
            if self._state == "connected":
                self._handle_close(1006)

    def _handle_close(self, code: int) -> None:
        """Handle connection close, optionally reconnecting."""
        if self._state in ("closing", "closed"):
            return
        self._close_code = code
        if code in PERMANENT_CLOSE_CODES:
            self._state = "closed"
        else:
            self._state = "idle"
        self._cleanup()
        if self._close_handler:
            self._close_handler(code)
        if self._opts.auto_reconnect and self._state == "idle":
            asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        self._state = "reconnecting"
        while self._state == "reconnecting":
            try:
                await asyncio.sleep(self._reconnect_delay_ms / 1000)
                await self._do_connect()
                self._start_ping_loop()
            except Exception:
                self._reconnect_delay_ms = min(
                    self._reconnect_delay_ms * 2, self._max_reconnect_delay_ms
                )

    def _cleanup(self) -> None:
        """Clean up connection resources."""
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None
        if self._recv_task:
            self._recv_task.cancel()
            self._recv_task = None
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
            self._writer = None
        self._reader = None
        self._ws = None

    def close(self) -> None:
        """Close the WebSocket connection gracefully."""
        if self._state == "closed":
            return
        self._state = "closing"
        if self._ws and self._writer:
            close = CloseConnection(code=1000, reason="normal closure")
            self._ws.send(close)
            try:
                self._writer.write(self._ws.bytes_to_send())
            except Exception:
                pass
        self._cleanup()
        self._state = "closed"
        if self._close_handler:
            self._close_handler(1000)
