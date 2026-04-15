"""
Voice stream STT service implementation.

Connects to Anthropic's voice_stream WebSocket endpoint for speech-to-text.
Uses conversation-engine backed models for speech-to-text. Designed for
hold-to-talk: hold the keybinding to record, release to stop and submit.

The wire protocol uses JSON control messages (KeepAlive, CloseStream) and
binary audio frames. The server responds with TranscriptText and
TranscriptEndpoint JSON messages.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

VOICE_STREAM_PATH = "/api/ws/speech_to_text/voice_stream"
KEEPALIVE_INTERVAL_MS = 8_000

# finalize() resolution timers
FINALIZE_TIMEOUTS_MS = {
    "safety": 5_000,
    "noData": 1_500,
}

KEEPALIVE_MSG = '{"type":"KeepAlive"}'
CLOSE_STREAM_MSG = '{"type":"CloseStream"}'

# Default base URL for OAuth - used to derive WebSocket URL
DEFAULT_BASE_API_URL = "https://api.anthropic.com"


# =============================================================================
# Types
# =============================================================================

from dataclasses import dataclass
from enum import Enum


class FinalizeSource(str, Enum):
    """How finalize() resolved."""
    POST_CLOSESTREAM_ENDPOINT = "post_closestream_endpoint"
    NO_DATA_TIMEOUT = "no_data_timeout"
    SAFETY_TIMEOUT = "safety_timeout"
    WS_CLOSE = "ws_close"
    WS_ALREADY_CLOSED = "ws_already_closed"


@dataclass(slots=True)
class VoiceStreamCallbacks:
    """Callbacks for voice stream events."""
    on_transcript: Callable[[str, bool], None]
    on_error: Callable[[str], None]
    on_close: Callable[[], None]
    on_ready: Callable[[VoiceStreamConnection], None]


@dataclass(slots=True)
class VoiceStreamConnection:
    """Connection to the voice stream STT service."""
    _ws: Any = None  # WebSocket connection
    _connected: bool = False
    _finalized: bool = False
    _finalizing: bool = False
    _last_transcript_text: str = ""
    _resolve_finalize: Callable[[FinalizeSource], None] | None = None
    _cancel_no_data_timer: Callable[[], None] | None = None

    def send(self, audio_chunk: bytes) -> None:
        """Send an audio chunk to the service."""
        raise NotImplementedError("Set via connect_voice_stream")

    async def finalize(self) -> FinalizeSource:
        """Finalize the stream and get the final transcript."""
        raise NotImplementedError("Set via connect_voice_stream")

    def close(self) -> None:
        """Close the connection."""
        raise NotImplementedError("Set via connect_voice_stream")

    def is_connected(self) -> bool:
        """Check if the connection is still open."""
        raise NotImplementedError("Set via connect_voice_stream")


# =============================================================================
# Availability Check
# =============================================================================

def is_voice_stream_available() -> bool:
    """
    Check if voice stream STT is available.

    Voice stream uses the same OAuth as Claude Code - available when the
    user is authenticated with Anthropic (Claude.ai subscriber or has
    valid OAuth tokens).

    Returns:
        True if voice stream is available, False otherwise
    """
    from py_claw.services.auth.auth import is_anthropic_auth_enabled, get_claude_ai_oauth_tokens

    if not is_anthropic_auth_enabled():
        return False
    tokens = get_claude_ai_oauth_tokens()
    return tokens is not None and tokens.get("accessToken") is not None


# =============================================================================
# WebSocket Connection
# =============================================================================

async def connect_voice_stream(
    callbacks: VoiceStreamCallbacks,
    options: dict[str, Any] | None = None,
) -> VoiceStreamConnection | None:
    """
    Connect to the voice stream STT service.

    Args:
        callbacks: VoiceStreamCallbacks with handlers for transcript, error, close, ready
        options: Optional dict with 'language' and 'keyterms' settings

    Returns:
        VoiceStreamConnection or None if connection fails
    """
    options = options or {}

    # Check availability first
    if not is_voice_stream_available():
        logger.warning("[voice_stream] No OAuth token available")
        return None

    # Refresh OAuth token if needed
    from py_claw.services.auth.auth import check_and_refresh_oauth_token_if_needed, get_claude_ai_oauth_tokens

    await check_and_refresh_oauth_token_if_needed()

    tokens = get_claude_ai_oauth_tokens()
    if not tokens or not tokens.get("accessToken"):
        logger.warning("[voice_stream] No OAuth token available after refresh check")
        return None

    # Build WebSocket URL
    ws_base_url = _get_ws_base_url()
    params = _build_url_params(options)
    url = f"{ws_base_url}{VOICE_STREAM_PATH}?{params}"

    logger.debug(f"[voice_stream] Connecting to {url}")

    # Create WebSocket connection
    try:
        ws = await _create_websocket(url, tokens["accessToken"])
    except Exception as e:
        logger.error(f"[voice_stream] Failed to create WebSocket: {e}")
        return None

    # Track connection state
    connected = False
    finalized = False
    finalizing = False
    last_transcript_text = ""
    resolve_finalize: Callable[[FinalizeSource], None] | None = None
    cancel_no_data_timer: Callable[[], None] | None = None
    keepalive_timer: asyncio.Task | None = None

    def _log_for_debugging(msg: str) -> None:
        """Debug logging helper."""
        logger.debug(f"[voice_stream] {msg}")

    # Build the connection object
    connection = _build_connection_object(
        ws=ws,
        get_connected=lambda: connected,
        get_finalized=lambda: finalized,
        get_finalizing=lambda: finalizing,
        get_last_transcript=lambda: last_transcript_text,
        set_last_transcript=lambda t: nonlocal last_transcript_text; last_transcript_text = t,
        get_resolve_finalize=lambda: resolve_finalize,
        set_resolve_finalize=lambda f: nonlocal resolve_finalize; resolve_finalize = f,
        get_cancel_no_data=lambda: cancel_no_data_timer,
        set_cancel_no_data=lambda c: nonlocal cancel_no_data_timer; cancel_no_data_timer = c,
        set_connected=lambda v: nonlocal connected; connected = v,
        set_finalized=lambda v: nonlocal finalized; finalized = v,
        set_finalizing=lambda v: nonlocal finalizing; finalizing = v,
        log=_log_for_debugging,
    )

    # Set up keepalive timer
    async def send_keepalive() -> None:
        """Send periodic keepalive to prevent idle timeout."""
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL_MS / 1000)
            if ws.open:
                _log_for_debugging("Sending periodic KeepAlive")
                await ws.send(KEEPALIVE_MSG)

    # Start message handler
    async def handle_messages() -> None:
        """Handle incoming WebSocket messages."""
        nonlocal last_transcript_text, finalized, resolve_finalize, cancel_no_data_timer

        try:
            async for msg in ws:
                await _handle_message(
                    msg=msg,
                    callbacks=callbacks,
                    connection=connection,
                    is_nova3=_is_nova_3_enabled(),
                    finalized=finalized,
                    last_transcript=last_transcript_text,
                    set_last_transcript=lambda t: nonlocal last_transcript_text; last_transcript_text = t,
                    cancel_no_data_timer=cancel_no_data_timer,
                    resolve_finalize=resolve_finalize,
                    log=_log_for_debugging,
                )
        except Exception as e:
            _log_for_debugging(f"Message handler error: {e}")

    # Handle WebSocket events
    async def on_open() -> None:
        nonlocal connected, keepalive_timer
        _log_for_debugging("WebSocket connected")
        connected = True

        # Send initial KeepAlive
        _log_for_debugging("Sending initial KeepAlive")
        await ws.send(KEEPALIVE_MSG)

        # Start keepalive timer
        keepalive_timer = asyncio.create_task(send_keepalive())

        # Notify ready
        callbacks.on_ready(connection)

    async def on_close(code: int, reason: str) -> None:
        nonlocal connected, keepalive_timer, last_transcript_text, finalizing, resolve_finalize
        _log_for_debugging(f"WebSocket closed: code={code} reason={reason}")
        connected = False

        if keepalive_timer:
            keepalive_timer.cancel()
            keepalive_timer = None

        # Promote unreported interim transcript
        if last_transcript_text:
            _log_for_debugging(
                f"Promoting unreported interim transcript to final on close: '{last_transcript_text}'"
            )
            callbacks.on_transcript(last_transcript_text, True)
            last_transcript_text = ""

        # Resolve finalize if pending
        if resolve_finalize:
            resolve_finalize(FinalizeSource.WS_CLOSE)

        # Notify close
        if not finalizing and code != 1000 and code != 1005:
            callbacks.on_error(f"Connection closed: code {code}{f' — {reason}' if reason else ''}")
        callbacks.on_close()

    async def on_error(error: Exception) -> None:
        nonlocal finalizing
        logger.error(f"[voice_stream] WebSocket error: {error}")
        if not finalizing:
            callbacks.on_error(f"Voice stream connection error: {error}")

    # Connect
    try:
        ws = await _connect_websocket(url, tokens["accessToken"])
    except Exception as e:
        logger.error(f"[voice_stream] WebSocket connection failed: {e}")
        return None

    # Run WebSocket
    try:
        await ws.wait_for_close()
    except Exception as e:
        _log_for_debugging(f"WebSocket error: {e}")
        if not finalizing:
            callbacks.on_error(f"Voice stream connection error: {e}")

    return connection


def _get_ws_base_url() -> str:
    """Get WebSocket base URL from OAuth config or environment."""
    # Check for VOICE_STREAM_BASE_URL override
    override = os.environ.get("VOICE_STREAM_BASE_URL")
    if override:
        # Convert http/https to ws/wss
        return override.replace("https://", "wss://").replace("http://", "ws://")

    # Use default API URL
    return DEFAULT_BASE_API_URL.replace("https://", "wss://").replace("http://", "ws://")


def _build_url_params(options: dict[str, Any]) -> str:
    """Build URL query parameters for the voice stream connection."""
    params = {
        "encoding": "linear16",
        "sample_rate": "16000",
        "channels": "1",
        "endpointing_ms": "300",
        "utterance_end_ms": "1000",
        "language": options.get("language", "en"),
    }

    # Check for Nova 3 feature gate
    if _is_nova_3_enabled():
        params["use_conversation_engine"] = "true"
        params["stt_provider"] = "deepgram-nova3"
        logger.debug("[voice_stream] Nova 3 gate enabled (tengu_cobalt_frost)")

    # Add keyterms if provided
    keyterms = options.get("keyterms")
    if keyterms:
        for term in keyterms:
            params.setdefault("keyterms", []).append(term)

    # Build query string
    return "&".join(f"{k}={v if isinstance(v, str) else ','.join(v)}" for k, v in params.items())


def _is_nova_3_enabled() -> bool:
    """Check if Nova 3 feature gate is enabled."""
    # TODO: Integrate with GrowthBook feature flags
    # For now, check environment variable
    return os.environ.get("VOICE_STREAM_NOVA3", "").lower() in ("1", "true", "yes")


async def _create_websocket(url: str, access_token: str) -> Any:
    """
    Create and connect a WebSocket connection.

    Returns the connected WebSocket object.
    """
    try:
        import websockets
    except ImportError:
        logger.error("[voice_stream] websockets package not installed")
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "x-app": "cli",
    }

    # Get proxy URL if configured
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    if proxy_url:
        async with websockets.connect(url, extra_headers=headers, proxy=proxy_url) as ws:
            return ws
    else:
        async with websockets.connect(url, extra_headers=headers) as ws:
            return ws


async def _connect_websocket(url: str, access_token: str) -> Any:
    """Connect to WebSocket and return the connection."""
    try:
        import websockets
    except ImportError:
        raise RuntimeError("websockets package required for voice stream")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "x-app": "cli",
    }

    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    if proxy_url:
        ws = await websockets.connect(url, extra_headers=headers, proxy=proxy_url)
    else:
        ws = await websockets.connect(url, extra_headers=headers)

    return ws


def _build_connection_object(
    ws: Any,
    get_connected: Callable[[], bool],
    get_finalized: Callable[[], bool],
    get_finalizing: Callable[[], bool],
    get_last_transcript: Callable[[], str],
    set_last_transcript: Callable[[str], None],
    get_resolve_finalize: Callable[[], Callable[[FinalizeSource], None] | None],
    set_resolve_finalize: Callable[[Callable[[FinalizeSource], None]], None],
    get_cancel_no_data: Callable[[], Callable[[], None] | None],
    set_cancel_no_data: Callable[[Callable[[], None]], None],
    set_connected: Callable[[bool], None],
    set_finalized: Callable[[bool], None],
    set_finalizing: Callable[[bool], None],
    log: Callable[[str], None],
) -> VoiceStreamConnection:
    """Build the VoiceStreamConnection object with closures."""

    connection = VoiceStreamConnection()

    async def send_chunk(audio_chunk: bytes) -> None:
        if not ws.open:
            return
        if get_finalized():
            log(f"Dropping audio chunk after CloseStream: {len(audio_chunk)} bytes")
            return
        log(f"Sending audio chunk: {len(audio_chunk)} bytes")
        # Copy buffer before sending
        await ws.send(audio_chunk)

    def send_chunk_sync(audio_chunk: bytes) -> None:
        """Sync wrapper for send_chunk."""
        if not ws.open:
            return
        if get_finalized():
            log(f"Dropping audio chunk after CloseStream: {len(audio_chunk)} bytes")
            return
        log(f"Sending audio chunk: {len(audio_chunk)} bytes")
        # Note: This is a simplification; in reality websockets requires await
        asyncio.create_task(ws.send(audio_chunk))

    async def finalize_stream() -> FinalizeSource:
        nonlocal connection
        if get_finalizing() or get_finalized():
            return FinalizeSource.WS_ALREADY_CLOSED

        set_finalizing(True)

        # Set up timers
        safety_timer = asyncio.create_task(_sleep_and_resolve(FINALIZE_TIMEOUTS_MS["safety"], FinalizeSource.SAFETY_TIMEOUT, get_resolve_finalize))
        no_data_timer = asyncio.create_task(_sleep_and_resolve(FINALIZE_TIMEOUTS_MS["noData"], FinalizeSource.NO_DATA_TIMEOUT, get_resolve_finalize))

        def cancel_no_data() -> None:
            if not no_data_timer.done():
                no_data_timer.cancel()

        set_cancel_no_data(cancel_no_data)

        def resolve(source: FinalizeSource) -> None:
            safety_timer.cancel()
            if not no_data_timer.done():
                no_data_timer.cancel()
            # Promote unreported interim
            last = get_last_transcript()
            if last:
                log(f"Promoting unreported interim before {source} resolve")
                set_last_transcript("")
                # Note: callbacks would need to be passed in for this
            log(f"Finalize resolved via {source}")
            if get_resolve_finalize():
                get_resolve_finalize()(source)

        set_resolve_finalize(resolve)

        # Check if already closed
        if not ws.open:
            return FinalizeSource.WS_ALREADY_CLOSED

        # Defer CloseStream to next event loop iteration
        async def send_close_stream() -> None:
            set_finalized(True)
            if ws.open:
                log("Sending CloseStream (finalize)")
                await ws.send(CLOSE_STREAM_MSG)

        asyncio.create_task(send_close_stream())
        return FinalizeSource.WS_ALREADY_CLOSED  # Will be resolved by timer/callback

    def close_connection() -> None:
        set_finalized(True)
        set_connected(False)
        if ws.open:
            asyncio.create_task(ws.close())

    def is_connected() -> bool:
        return get_connected() and ws.open

    # Assign methods to connection
    connection.send = send_chunk_sync
    connection.finalize = finalize_stream
    connection.close = close_connection
    connection.is_connected = is_connected

    return connection


async def _sleep_and_resolve(delay_ms: int, source: FinalizeSource, resolve_fn: Callable[[], Callable[[FinalizeSource], None] | None]) -> None:
    """Sleep for delay_ms then resolve with source."""
    await asyncio.sleep(delay_ms / 1000)
    resolve = resolve_fn()
    if resolve:
        resolve(source)


async def _handle_message(
    msg: Any,
    callbacks: VoiceStreamCallbacks,
    connection: VoiceStreamConnection,
    is_nova3: bool,
    finalized: bool,
    last_transcript: str,
    set_last_transcript: Callable[[str], None],
    cancel_no_data_timer: Callable[[], None] | None,
    resolve_finalize: Callable[[FinalizeSource], None] | None,
    log: Callable[[str], None],
) -> None:
    """Handle an incoming WebSocket message."""
    try:
        text = msg.data if hasattr(msg, 'data') else msg
        if isinstance(text, bytes):
            text = text.decode('utf-8')

        log(f"Message received ({len(text)} chars): {text[:200]}")

        data = json.loads(text)
        msg_type = data.get("type")

        if msg_type == "TranscriptText":
            transcript = data.get("data", "")
            log(f"TranscriptText: '{transcript}'")

            # Disarm no-data timer if finalized
            if finalized and cancel_no_data_timer:
                cancel_no_data_timer()

            if transcript:
                # Auto-finalize previous segment if non-cumulative
                if not is_nova3 and last_transcript:
                    prev = last_transcript.strip()
                    next_t = transcript.strip()
                    if prev and next_t and not next_t.startswith(prev) and not prev.startswith(next_t):
                        log(f"Auto-finalizing previous segment: '{last_transcript}'")
                        callbacks.on_transcript(last_transcript, True)

                set_last_transcript(transcript)
                callbacks.on_transcript(transcript, False)

        elif msg_type == "TranscriptEndpoint":
            log(f"TranscriptEndpoint received, lastTranscript='{last_transcript}'")
            final_text = last_transcript
            set_last_transcript("")
            if final_text:
                callbacks.on_transcript(final_text, True)

            if finalized and resolve_finalize:
                resolve_finalize(FinalizeSource.POST_CLOSESTREAM_ENDPOINT)

        elif msg_type == "TranscriptError":
            desc = data.get("description") or data.get("error_code") or "unknown transcription error"
            log(f"TranscriptError: {desc}")
            callbacks.on_error(desc)

        elif msg_type == "error":
            error_detail = data.get("message", json.dumps(data))
            log(f"Server error: {error_detail}")
            callbacks.on_error(error_detail)

    except json.JSONDecodeError:
        pass
    except Exception as e:
        log(f"Error handling message: {e}")
