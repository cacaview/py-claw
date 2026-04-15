"""Tests for HybridTransport and SerialBatchEventUploader."""

from __future__ import annotations

import asyncio
import json

import pytest

from py_claw.services.transports.hybrid import (
    _convert_ws_url_to_post_url,
    HybridTransport,
    HybridTransportOptions,
)
from py_claw.services.transports.serial_batcher import (
    RetryableError,
    SerialBatchEventUploader,
    SerialBatcherConfig,
)
from py_claw.services.transports.websocket import WebSocketTransport, WebSocketTransportOptions


# ─── URL Conversion ────────────────────────────────────────────────────────────

class TestConvertWsUrlToPostUrl:
    """Tests for WebSocket URL → HTTP POST URL conversion."""

    def test_wss_session_ingress(self):
        result = _convert_ws_url_to_post_url(
            "wss://api.example.com/v2/session_ingress/ws/sess123"
        )
        assert result == "https://api.example.com/v2/session_ingress/session/sess123/events"

    def test_wss_trailing_slash(self):
        result = _convert_ws_url_to_post_url(
            "wss://api.example.com/v2/session_ingress/ws/"
        )
        assert result == "https://api.example.com/v2/session_ingress/session/events"

    def test_ws_localhost(self):
        result = _convert_ws_url_to_post_url(
            "ws://localhost:8080/ws/session/abc"
        )
        assert "http://localhost:8080" in result
        assert "/session/abc/events" in result

    def test_https_replaces_wss(self):
        result = _convert_ws_url_to_post_url(
            "wss://echo.example.com/ws/test"
        )
        assert result.startswith("https://")

    def test_http_replaces_ws(self):
        result = _convert_ws_url_to_post_url(
            "ws://echo.example.com/ws/test"
        )
        assert result.startswith("http://")


# ─── SerialBatchEventUploader ────────────────────────────────────────────────

class TestSerialBatchEventUploader:
    """Tests for SerialBatchEventUploader."""

    def test_batching(self):
        """Items are batched according to max_batch_size."""
        results: list[list] = []

        async def run():
            async def sender(batch):
                results.append(list(batch))

            uploader = SerialBatchEventUploader(SerialBatcherConfig(
                max_batch_size=3,
                max_queue_size=100,
                send=sender,
                base_delay_ms=10,
                max_delay_ms=100,
                jitter_ms=0,
            ))
            await uploader.enqueue(["a", "b", "c", "d", "e"])
            await uploader.flush()
            uploader.close()

        asyncio.run(run())
        # 5 items with batch_size=3 → two batches: [a,b,c], [d,e]
        assert results == [["a", "b", "c"], ["d", "e"]]

    def test_single_item(self):
        """Single item is sent immediately."""
        results: list[list] = []

        async def run():
            async def sender(batch):
                results.append(list(batch))

            uploader = SerialBatchEventUploader(SerialBatcherConfig(
                max_batch_size=10,
                max_queue_size=100,
                send=sender,
                base_delay_ms=10,
                max_delay_ms=100,
                jitter_ms=0,
            ))
            await uploader.enqueue(["only"])
            await uploader.flush()
            uploader.close()

        asyncio.run(run())
        assert results == [["only"]]

    def test_flush_empty(self):
        """flush() on empty queue returns immediately."""
        async def run():
            async def sender(batch):
                pass

            uploader = SerialBatchEventUploader(SerialBatcherConfig(
                max_batch_size=2,
                max_queue_size=100,
                send=sender,
                base_delay_ms=10,
                max_delay_ms=100,
                jitter_ms=0,
            ))
            # flush without any enqueue should not hang
            await uploader.flush()
            uploader.close()

        asyncio.run(run())

    def test_close_drops_pending(self):
        """close() drops pending items and resolves flush."""
        results: list[list] = []

        async def run():
            async def sender(batch):
                results.append(list(batch))

            uploader = SerialBatchEventUploader(SerialBatcherConfig(
                max_batch_size=2,
                max_queue_size=100,
                send=sender,
                base_delay_ms=500,
                max_delay_ms=1000,
                jitter_ms=0,
            ))
            await uploader.enqueue(["a", "b", "c"])
            await asyncio.sleep(0)
            uploader.close()
            # Items 'a','b' might have been sent before close
            await asyncio.sleep(0)

        asyncio.run(run())
        # At most one batch (2 items) sent; the 3rd was dropped by close()

    def test_pending_count(self):
        """pending_count reflects actual queue depth."""
        uploader: SerialBatchEventUploader

        async def run():
            nonlocal uploader
            async def sender(batch):
                await asyncio.sleep(0)

            uploader = SerialBatchEventUploader(SerialBatcherConfig(
                max_batch_size=1,
                max_queue_size=10,
                send=sender,
                base_delay_ms=500,
                max_delay_ms=1000,
                jitter_ms=0,
            ))
            assert uploader.pending_count == 0
            await uploader.enqueue(["x", "y"])
            # 2 items pending, batch_size=1, so at least 1 still pending
            assert uploader.pending_count >= 1
            uploader.close()

        asyncio.run(run())

    def test_dropped_batch_count(self):
        """dropped_batch_count increments on max_consecutive_failures."""
        drop_count = 0

        async def run():
            nonlocal drop_count

            def on_drop(batch_size, failures):
                nonlocal drop_count
                drop_count += 1

            async def sender(batch):
                raise RetryableError("test failure")

            uploader = SerialBatchEventUploader(SerialBatcherConfig(
                max_batch_size=2,
                max_queue_size=10,
                send=sender,
                base_delay_ms=5,
                max_delay_ms=20,
                jitter_ms=0,
                max_consecutive_failures=2,
                on_batch_dropped=on_drop,
            ))
            await uploader.enqueue(["a", "b"])
            await uploader.flush()
            await asyncio.sleep(0.1)
            uploader.close()

        asyncio.run(run())
        assert drop_count >= 1

    def test_retryable_error_triggers_retry(self):
        """RetryableError causes the batch to be re-queued."""
        results: list[list] = []
        attempt = 0

        async def run():
            nonlocal attempt

            async def sender(batch):
                nonlocal attempt
                attempt += 1
                results.append(list(batch))
                if attempt == 1:
                    raise RetryableError("transient failure")

            uploader = SerialBatchEventUploader(SerialBatcherConfig(
                max_batch_size=2,
                max_queue_size=10,
                send=sender,
                base_delay_ms=5,
                max_delay_ms=50,
                jitter_ms=0,
            ))
            await uploader.enqueue(["only_one"])
            await uploader.flush()
            uploader.close()

        asyncio.run(run())
        # First attempt failed, re-queued and retried → 2 total attempts
        assert attempt == 2
        assert len(results) == 2


class TestRetryableError:
    """Tests for RetryableError."""

    def test_with_retry_after(self):
        err = RetryableError("rate limited", retry_after_ms=5000)
        assert err.message == "rate limited"
        assert err.retry_after_ms == 5000

    def test_without_retry_after(self):
        err = RetryableError("network error")
        assert err.retry_after_ms is None


# ─── HybridTransport ──────────────────────────────────────────────────────────

class TestHybridTransportInit:
    """Tests for HybridTransport initialization."""

    def test_default_options(self):
        transport = HybridTransport("wss://api.example.com/ws/sess1")
        assert transport.state == "idle"
        assert transport._opts.auto_reconnect is True

    def test_custom_options(self):
        transport = HybridTransport(
            "wss://api.example.com/ws/sess1",
            options=HybridTransportOptions(
                auto_reconnect=False,
                max_consecutive_failures=3,
            ),
        )
        assert transport._opts.auto_reconnect is False
        assert transport._opts.max_consecutive_failures == 3

    def test_post_url_derived(self):
        transport = HybridTransport("wss://api.example.com/v2/session_ingress/ws/sess123")
        assert transport._post_url == "https://api.example.com/v2/session_ingress/session/sess123/events"

    def test_dropped_batch_count_initially_zero(self):
        transport = HybridTransport("wss://api.example.com/ws/test")
        assert transport.dropped_batch_count == 0


class TestHybridTransportWrite:
    """Tests for HybridTransport.write()."""

    def test_stream_event_buffering(self):
        """stream_event messages are buffered, not sent immediately."""
        sent_batches: list[list] = []

        async def run():
            transport = HybridTransport(
                "wss://api.example.com/ws/test",
                options=HybridTransportOptions(auto_reconnect=False),
            )
            # Replace the uploader's send with a collector
            original_send = transport._uploader._config.send

            async def collector(batch):
                sent_batches.append(list(batch))

            transport._uploader._config.send = collector  # type: ignore

            # stream_event goes to buffer
            msg = {"type": "stream_event", "data": "chunk1"}
            await transport.write(msg)
            assert len(transport._stream_event_buffer) == 1
            assert sent_batches == []

            # Non-stream_event flushes the buffer
            msg2 = {"type": "result", "data": "done"}
            await transport.write(msg2)
            # Buffer should be cleared after flush
            assert len(transport._stream_event_buffer) == 0

            transport.close()

        asyncio.run(run())

    def test_write_batch(self):
        """write_batch flushes buffer and enqueues the batch."""
        enqueued: list[list] = []

        async def run():
            transport = HybridTransport(
                "wss://api.example.com/ws/test",
                options=HybridTransportOptions(auto_reconnect=False),
            )

            async def collector(batch):
                enqueued.extend(list(batch))

            transport._uploader._config.send = collector  # type: ignore

            await transport.write_batch([
                {"type": "message", "content": "a"},
                {"type": "message", "content": "b"},
            ])
            # Should have flushed and enqueued
            await asyncio.sleep(0)
            transport.close()

        asyncio.run(run())
        assert len(enqueued) == 2


class TestWebSocketTransportOptions:
    """Tests for WebSocketTransportOptions."""

    def test_defaults(self):
        opts = WebSocketTransportOptions()
        assert opts.auto_reconnect is True
        assert opts.is_bridge is False
