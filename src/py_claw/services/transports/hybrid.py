"""Hybrid transport: WebSocket for reads, HTTP POST for writes.

Architecture:
  write(stream_event) ──► stream_event_buffer (100ms timer)
  write(other)         ──► flush buffer + enqueue immediately
                           └──► SerialBatchEventUploader
                                    └──► postOnce() (single HTTP POST)
                                         - 429/5xx → retryable (re-queued)
                                         - 4xx (non-429) → permanent drop
                                         - success → advance

Key behaviours:
- stream_event messages are buffered for up to BATCH_FLUSH_INTERVAL_MS to
  reduce POST count for high-volume content deltas
- Non-stream writes flush buffered stream_events first (ordering guarantee)
- Serialization + retry + backpressure via SerialBatchEventUploader
- close() grants CLOSE_GRACE_MS for queued writes before forcing shutdown
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

try:
    from urllib import request as urllib_request
    from urllib import error as urllib_error
except ImportError:
    import urllib.request as urllib_request  # type: ignore
    import urllib.error as urllib_error  # type: ignore

from py_claw.services.transports.serial_batcher import (
    RetryableError,
    SerialBatchEventUploader,
    SerialBatcherConfig,
)
from py_claw.services.transports.websocket import WebSocketTransport, WebSocketTransportOptions

log = logging.getLogger(__name__)

# Per-attempt POST timeout. Bounds how long a single stuck POST can block
# the serialized queue.
POST_TIMEOUT_MS = 15_000
# Stream event batching interval
BATCH_FLUSH_INTERVAL_MS = 100
# Grace period for queued writes on close(). Best-effort drain window.
CLOSE_GRACE_MS = 3000


def _get_session_ingress_auth_token() -> str | None:
    """Get the session ingress auth token from environment or bridge state."""
    # Check environment variable first
    token = os.environ.get("CLAUDE_SESSION_INGRESS_TOKEN")
    if token:
        return token
    # Try to get from bridge state if available
    try:
        from py_claw.services.bridge.state import BridgeStateStorage

        state = BridgeStateStorage.get_instance()
        if state.sessions:
            for session in state.sessions.values():
                if hasattr(session, "ingress_token"):
                    return session.ingress_token  # type: ignore
    except Exception:
        pass
    return None


def _convert_ws_url_to_post_url(ws_url: str) -> str:
    """Convert a WebSocket URL to an HTTP POST endpoint URL.

    From: wss://api.example.com/v2/session_ingress/ws/<session_id>
      To: https://api.example.com/v2/session_ingress/session/<session_id>/events
    """
    # Determine HTTP protocol
    if ws_url.startswith("wss://"):
        protocol = "https://"
        rest = ws_url[6:]
    elif ws_url.startswith("ws://"):
        protocol = "http://"
        rest = ws_url[5:]
    else:
        protocol = "https://"
        rest = ws_url

    # Split host from path
    if "/" in rest:
        host, path = rest.split("/", 1)
    else:
        host = rest
        path = ""

    # Replace /ws/ with /session/ and append /events
    path = path.replace("/ws/", "/session/")
    if not path.endswith("/events"):
        path = path.rstrip("/") + "/events"

    return f"{protocol}{host}/{path}"


@dataclass
class HybridTransportOptions:
    """Options for HybridTransport."""

    auto_reconnect: bool = True
    is_bridge: bool = False
    max_consecutive_failures: int | None = None
    on_batch_dropped: callable | None = None


class HybridTransport(WebSocketTransport):
    """Hybrid transport: WebSocket for reads, HTTP POST for writes.

    Non-stream writes go through SerialBatchEventUploader for serial ordered
    delivery with retry/backoff. Stream events are buffered for 100ms to batch
    high-frequency content deltas into fewer POSTs.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        options: HybridTransportOptions | None = None,
    ) -> None:
        super().__init__(url, headers, options and WebSocketTransportOptions(
            auto_reconnect=options.auto_reconnect,
            is_bridge=options.is_bridge,
        ))
        self._opts = options or HybridTransportOptions()
        self._post_url = _convert_ws_url_to_post_url(url)

        # SerialBatchEventUploader config
        self._uploader = SerialBatchEventUploader(
            SerialBatcherConfig(
                max_batch_size=500,
                max_queue_size=100_000,
                base_delay_ms=500,
                max_delay_ms=8000,
                jitter_ms=1000,
                max_consecutive_failures=self._opts.max_consecutive_failures,
                on_batch_dropped=self._opts.on_batch_dropped,
                send=lambda batch: asyncio.get_event_loop().run_until_complete(
                    self._post_once(batch)
                ),
            )
        )

        # Stream event batching
        self._stream_event_buffer: list[dict[str, Any]] = []
        self._stream_event_timer: asyncio.Task | None = None

        log.debug(f"HybridTransport: POST URL = {self._post_url}")

    @property
    def dropped_batch_count(self) -> int:
        """Count of batches dropped after maxConsecutiveFailures."""
        return self._uploader.dropped_batch_count

    async def write(self, message: dict[str, Any]) -> None:
        """Enqueue a message, waiting for the queue to drain.

        stream_event messages accumulate in a buffer for up to
        BATCH_FLUSH_INTERVAL_MS before enqueueing. Other messages
        flush the buffer immediately to preserve ordering.
        """
        msg_copy = dict(message)
        if msg_copy.get("type") == "stream_event":
            # Delay: accumulate stream_events briefly before enqueueing
            self._stream_event_buffer.append(msg_copy)
            if not self._stream_event_timer:
                self._stream_event_timer = asyncio.create_task(
                    self._flush_stream_events_after_delay()
                )
            return

        # Immediate: flush any buffered stream_events (ordering), then this event
        buffered = self._take_stream_events()
        await self._uploader.enqueue(buffered + [msg_copy])
        await self.flush()

    async def write_batch(self, messages: list[dict[str, Any]]) -> None:
        """Enqueue a batch of messages and wait for drain."""
        buffered = self._take_stream_events()
        await self._uploader.enqueue(buffered + list(messages))
        await self.flush()

    def flush(self) -> asyncio.Future:
        """Block until all pending events are POSTed."""
        self._uploader.enqueue(self._take_stream_events())
        return self._uploader.flush()

    def _take_stream_events(self) -> list[dict[str, Any]]:
        """Take ownership of buffered stream_events and clear the timer."""
        if self._stream_event_timer:
            self._stream_event_timer.cancel()
            self._stream_event_timer = None
        buffered = self._stream_event_buffer
        self._stream_event_buffer = []
        return buffered

    async def _flush_stream_events_after_delay(self) -> None:
        """Delay timer fired — enqueue accumulated stream_events."""
        await asyncio.sleep(BATCH_FLUSH_INTERVAL_MS / 1000)
        self._stream_event_timer = None
        buffered = self._take_stream_events()
        if buffered:
            await self._uploader.enqueue(buffered)

    async def _post_once(self, events: list[dict[str, Any]]) -> None:
        """Single-attempt POST.

        Throws RetryableError on retryable failures (429, 5xx, network) so
        SerialBatchEventUploader re-queues and retries. Returns on success
        and on permanent failures (4xx non-429) so the uploader moves on.
        """
        token = _get_session_ingress_auth_token()
        if not token:
            log.debug("HybridTransport: No session token available for POST")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        body = json.dumps({"events": events}).encode("utf-8")

        try:
            req = urllib_request.Request(
                self._post_url,
                data=body,
                headers=headers,
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=POST_TIMEOUT_MS / 1000) as response:
                status = response.status
                if 200 <= status < 300:
                    log.debug(f"HybridTransport: POST success count={len(events)}")
                    return
                # 4xx (except 429) — permanent failure, drop
                if 400 <= status < 500 and status != 429:
                    log.debug(f"HybridTransport: POST {status} (permanent), dropping")
                    return
                # 429 / 5xx — retryable
                log.debug(f"HybridTransport: POST {status} (retryable)")
                raise RetryableError(f"POST failed with {status}", retry_after_ms=None)

        except urllib_error.HTTPError as exc:
            status = exc.code
            if 200 <= status < 300:
                return
            if 400 <= status < 500 and status != 429:
                log.debug(f"HybridTransport: POST {status} (permanent), dropping")
                return
            log.debug(f"HybridTransport: POST HTTP error {status} (retryable)")
            raise RetryableError(f"POST failed with {status}") from exc

        except urllib_error.URLError as exc:
            log.debug(f"HybridTransport: POST network error (retryable): {exc.reason}")
            raise RetryableError(f"POST network error: {exc.reason}") from exc

        except Exception as exc:
            log.debug(f"HybridTransport: POST unexpected error (retryable): {exc}")
            raise RetryableError(str(exc)) from exc

    def close(self) -> None:
        """Close the transport with a grace period for queued writes."""
        if self._stream_event_timer:
            self._stream_event_timer.cancel()
            self._stream_event_timer = None
        self._stream_event_buffer = []

        # Grace period for queued writes — last resort after bridge teardown
        uploader = self._uploader

        async def _graceful_close() -> None:
            await asyncio.sleep(CLOSE_GRACE_MS / 1000)
            uploader.close()

        asyncio.create_task(_graceful_close())
        super().close()
