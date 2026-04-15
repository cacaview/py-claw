"""
Hybrid transport: WebSocket for reads, HTTP POST for writes.

Reference: ClaudeCode-main/src/cli/transports/HybridTransport.ts

Write flow:

  write(stream_event) ─┐
                       │ (100ms timer)
                       │
                       ▼
  write(other) ────► uploader.enqueue()  (SerialBatchEventUploader)
                       ▲    │
  writeBatch() ────────┘    │ serial, batched, retries indefinitely,
                            │ backpressure at maxQueueSize
                            ▼
                       postOnce()  (single HTTP POST, throws on retryable)

stream_event messages accumulate in streamEventBuffer for up to 100ms
before enqueue (reduces POST count for high-volume content deltas). A
non-stream write flushes any buffered stream_events first to preserve order.

Serialization + retry + backpressure are delegated to SerialBatchEventUploader.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .base import Transport
from .serial_batch import SerialBatchEventUploader, RetryableError
from .websocket import WebSocketTransport

logger = logging.getLogger(__name__)

# Per-attempt POST timeout (ms)
POST_TIMEOUT_MS = 15_000
# Grace period for queued writes on close() (ms)
CLOSE_GRACE_MS = 3000
# Batch flush interval for stream events (ms)
BATCH_FLUSH_INTERVAL_MS = 100


def _convert_ws_url_to_post_url(ws_url: str) -> str:
    """
    Convert a WebSocket URL to the HTTP POST endpoint URL.

    From: wss://api.example.com/v2/session_ingress/ws/<session_id>
    To: https://api.example.com/v2/session_ingress/session/<session_id>/events
    """
    # Replace ws(s):// with http(s)://
    if ws_url.startswith("wss://"):
        post_url = "https://" + ws_url[6:]
    elif ws_url.startswith("ws://"):
        post_url = "http://" + ws_url[5:]
    else:
        post_url = ws_url

    # Replace /ws/ with /session/
    post_url = post_url.replace("/ws/", "/session/")

    # Append /events if not already present
    if not post_url.endswith("/events"):
        if post_url.endswith("/"):
            post_url = post_url + "events"
        else:
            post_url = post_url + "/events"

    return post_url


class HybridTransport(WebSocketTransport):
    """
    Hybrid transport: WebSocket for reads, HTTP POST for writes.

    Combines WebSocketTransport for reading with SerialBatchEventUploader
    for serialized batched HTTP POST writes.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        session_id: str | None = None,
        refresh_headers: Callable[[], dict[str, str]] | None = None,
        get_auth_token: Callable[[], str | None] | None = None,
        max_consecutive_failures: int | None = None,
        on_batch_dropped: Callable[[int, int], None] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize HybridTransport.

        Args:
            url: WebSocket server URL
            headers: Optional headers to include in handshake
            session_id: Optional session ID for logging
            refresh_headers: Optional callback to refresh auth headers
            get_auth_token: Callback to get session ingress auth token
            max_consecutive_failures: Optional cap on consecutive failures
            on_batch_dropped: Called when a batch is dropped
        """
        super().__init__(url, headers, session_id=session_id, **kwargs)
        self._post_url = _convert_ws_url_to_post_url(url)
        self._get_auth_token = get_auth_token or (lambda: None)
        self._on_batch_dropped = on_batch_dropped

        async def post_once(events: list[Any]) -> None:
            await self._post_once(events)

        self._uploader = SerialBatchEventUploader(
            max_batch_size=500,
            max_queue_size=100_000,
            send=post_once,
            base_delay_ms=500,
            max_delay_ms=8000,
            jitter_ms=1000,
            max_consecutive_failures=max_consecutive_failures,
            on_batch_dropped=on_batch_dropped,
        )

        # Stream event buffer — accumulates content deltas before enqueueing
        self._stream_event_buffer: list[Any] = []
        self._stream_event_timer: asyncio.Task | None = None

        logger.debug(f"HybridTransport: POST URL = {self._post_url}")

    @property
    def dropped_batch_count(self) -> int:
        """Snapshot of dropped batch count for diagnostics."""
        return self._uploader.dropped_batch_count

    async def write(self, message: dict[str, Any]) -> None:
        """
        Write a message.

        For stream_event messages, buffers them briefly before enqueueing.
        For other messages, flushes buffered stream events first.
        """
        if message.get("type") == "stream_event":
            # Delay: accumulate stream_events briefly before enqueueing
            self._stream_event_buffer.append(message)
            if not self._stream_event_timer:
                self._stream_event_timer = asyncio.create_task(
                    self._flush_stream_events_delayed()
                )
            return

        # Immediate: flush buffered stream_events first, then this event
        buffered = self._take_stream_events()
        await self._uploader.enqueue([*buffered, message])
        await self._uploader.flush()

    async def write_batch(self, messages: list[dict[str, Any]]) -> None:
        """Write multiple messages at once."""
        buffered = self._take_stream_events()
        await self._uploader.enqueue([*buffered, *messages])
        await self._uploader.flush()

    async def flush(self) -> None:
        """Block until all pending events are POSTed."""
        buffered = self._take_stream_events()
        if buffered:
            await self._uploader.enqueue(buffered)
        await self._uploader.flush()

    def _take_stream_events(self) -> list[Any]:
        """Take ownership of buffered stream_events and clear the delay timer."""
        if self._stream_event_timer:
            self._stream_event_timer.cancel()
            self._stream_event_timer = None

        buffered = self._stream_event_buffer
        self._stream_event_buffer = []
        return buffered

    async def _flush_stream_events_delayed(self) -> None:
        """Delay timer fired — enqueue accumulated stream_events."""
        await asyncio.sleep(BATCH_FLUSH_INTERVAL_MS / 1000.0)
        self._stream_event_timer = None
        buffered = self._take_stream_events()
        if buffered:
            await self._uploader.enqueue(buffered)

    async def _post_once(self, events: list[Any]) -> None:
        """
        Single-attempt POST.

        Throws on retryable failures (429, 5xx, network) so SerialBatchEventUploader
        re-queues and retries. Returns on success and on permanent failures
        (4xx non-429, no token) so the uploader moves on.
        """
        session_token = self._get_auth_token()
        if not session_token:
            logger.debug("HybridTransport: No session token available for POST")
            return

        headers = {
            "Authorization": f"Bearer {session_token}",
            "Content-Type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=POST_TIMEOUT_MS / 1000.0)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self._post_url,
                    json={"events": events},
                    headers=headers,
                ) as response:
                    if 200 <= response.status < 300:
                        logger.debug(
                            f"HybridTransport: POST success count={len(events)}"
                        )
                        return

                    # 4xx (except 429) are permanent — drop, don't retry
                    if (
                        400 <= response.status < 500
                        and response.status != 429
                    ):
                        logger.debug(
                            f"HybridTransport: POST returned {response.status} "
                            "(permanent), dropping"
                        )
                        return

                    # 429 / 5xx — retryable
                    logger.debug(
                        f"HybridTransport: POST returned {response.status} (retryable)"
                    )
                    raise RetryableError(f"POST failed with {response.status}")

        except aiohttp.ClientError as e:
            logger.debug(f"HybridTransport: POST error: {e}")
            raise RetryableError(str(e))

    def close(self) -> None:
        """Close the transport with grace period for pending writes."""
        # Clear stream event timer
        if self._stream_event_timer:
            self._stream_event_timer.cancel()
            self._stream_event_timer = None
        self._stream_event_buffer = []

        # Grace period for queued writes — best-effort drain
        async def graceful_close() -> None:
            try:
                await asyncio.wait_for(
                    self._uploader.flush(),
                    timeout=CLOSE_GRACE_MS / 1000.0,
                )
            except asyncio.TimeoutError:
                pass
            finally:
                self._uploader.close()

        asyncio.create_task(graceful_close())
        super().close()


from typing import Callable
