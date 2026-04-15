"""Streaming speech-to-text with Deepgram WebSocket integration."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from .types import AudioChunk, StreamSTTConfig, TranscriptionResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Deepgram WebSocket URLs
DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_URL_TELEMETRY = "wss://api.deepgram.com/v1/listen?terminal_phrases=true"


class StreamSTT:
    """Streaming speech-to-text using Deepgram WebSocket.

    Provides real-time audio transcription with support for:
    - Interim results (partial transcriptions)
    - Endpoint detection (silence detection)
    - Word-level timing
    - Speaker detection (with diarization)
    """

    def __init__(self, config: StreamSTTConfig) -> None:
        """Initialize streaming STT.

        Args:
            config: Stream STT configuration.
        """
        self._config = config
        self._websocket = None
        self._receive_task: asyncio.Task | None = None
        self._is_connected = False
        self._audio_queue: asyncio.Queue[AudioChunk | None] = asyncio.Queue()
        self._text_callback: Callable[[TranscriptionResult], Awaitable[None]] | None = None
        self._final_callback: Callable[[TranscriptionResult], Awaitable[None]] | None = None

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._is_connected

    async def connect(
        self,
        text_callback: Callable[[TranscriptionResult], Awaitable[None]] | None = None,
        final_callback: Callable[[TranscriptionResult], Awaitable[None]] | None = None,
    ) -> None:
        """Connect to the STT WebSocket.

        Args:
            text_callback: Callback for interim transcription results.
            final_callback: Callback for final transcription results.
        """
        if self._is_connected:
            logger.warning("Already connected to STT")
            return

        self._text_callback = text_callback
        self._final_callback = final_callback

        # Build URL with parameters
        params = [
            ("model", self._config.model),
            ("language", self._config.language),
            ("encoding", self._config.encoding),
            ("sample_rate", str(self._config.sample_rate)),
            ("channels", str(self._config.channels)),
            ("interim_results", str(self._config.interim_results).lower()),
            ("punctuate", str(self._config.punctuate).lower()),
            ("profanity_filter", str(self._config.profanity_filter).lower()),
            ("endpointing", str(self._config.endpointing).lower()),
            ("utterance_end", "true"),
        ]

        # Add API key to headers
        headers = {"Authorization": f"Token {self._config.api_key}"}

        url = _build_url(DEEPGRAM_URL, params)

        try:
            import websockets

            self._websocket = await websockets.connect(url, extra_headers=headers)
            self._is_connected = True

            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())

            logger.info("Connected to Deepgram STT")
        except Exception as e:
            logger.error(f"Failed to connect to Deepgram: {e}")
            raise STTError(f"Connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from the STT WebSocket."""
        if not self._is_connected:
            return

        # Signal end of audio
        await self._audio_queue.put(None)

        # Wait for receive task to finish
        if self._receive_task:
            try:
                await asyncio.wait_for(self._receive_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._receive_task.cancel()
            except Exception:
                pass

        # Close WebSocket
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass

        self._is_connected = False
        self._websocket = None
        logger.info("Disconnected from Deepgram STT")

    async def send_audio(self, chunk: AudioChunk) -> None:
        """Send audio data to the STT service.

        Args:
            chunk: Audio chunk to send.
        """
        if not self._is_connected or not self._websocket:
            raise STTError("Not connected to STT service")

        try:
            # Encode audio to base64
            audio_b64 = base64.b64encode(chunk.data).decode("utf-8")

            # Send as JSON message
            message = json.dumps({"channel": {"data": audio_b64}})
            await self._websocket.send(message)
        except Exception as e:
            logger.error(f"Failed to send audio: {e}")
            raise STTError(f"Send failed: {e}") from e

    async def _receive_loop(self) -> None:
        """Receive messages from the WebSocket."""
        if not self._websocket:
            return

        try:
            async for message in self._websocket:
                if not message:
                    continue

                try:
                    data = json.loads(message)
                    result = self._parse_message(data)
                    if result:
                        await self._handle_result(result)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from STT: {message[:100]}")
                except Exception as e:
                    logger.error(f"Error processing STT message: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("STT WebSocket connection closed")
        except Exception as e:
            logger.error(f"STT receive loop error: {e}")
        finally:
            self._is_connected = False

    def _parse_message(self, data: dict) -> TranscriptionResult | None:
        """Parse a Deepgram WebSocket message.

        Args:
            data: Parsed JSON message.

        Returns:
            TranscriptionResult or None if not a transcript message.
        """
        try:
            # Check for transcript in channel alternatives
            if "channel" not in data:
                return None

            channel = data.get("channel", {})
            alternatives = channel.get("alternatives", [])
            if not alternatives:
                return None

            alternative = alternatives[0]
            transcript = alternative.get("transcript", "")

            if not transcript:
                return None

            # Check if final
            is_final = data.get("is_final", False)

            # Extract confidence
            confidence = alternative.get("confidence")
            if confidence is not None:
                confidence = float(confidence)

            # Extract word timing
            words = []
            if "words" in alternative:
                words = [
                    {
                        "word": w.get("word", ""),
                        "start": w.get("start"),
                        "end": w.get("end"),
                        "confidence": w.get("confidence"),
                    }
                    for w in alternative["words"]
                ]

            # Extract speaker
            speaker = None
            if "speaker" in alternative:
                speaker = str(alternative["speaker"])

            # Extract detected language
            language = data.get("channel", {}).get("language")

            return TranscriptionResult(
                text=transcript,
                is_final=is_final,
                confidence=confidence,
                words=words,
                speaker=speaker,
                language=language,
            )

        except Exception as e:
            logger.debug(f"Error parsing STT message: {e}")
            return None

    async def _handle_result(self, result: TranscriptionResult) -> None:
        """Handle a transcription result.

        Args:
            result: Transcription result to handle.
        """
        if result.is_final:
            if self._final_callback:
                await self._final_callback(result)
        else:
            if self._text_callback:
                await self._text_callback(result)


class STTError(Exception):
    """STT-related errors."""

    pass


def _build_url(base: str, params: list[tuple[str, str]]) -> str:
    """Build URL with query parameters.

    Args:
        base: Base URL.
        params: List of (key, value) tuples.

    Returns:
        URL with query string.
    """
    if not params:
        return base

    query = "&".join(f"{k}={v}" for k, v in params)
    return f"{base}?{query}"


async def create_stream_stt(
    api_key: str,
    text_callback: Callable[[TranscriptionResult], Awaitable[None]] | None = None,
    final_callback: Callable[[TranscriptionResult], Awaitable[None]] | None = None,
    **kwargs: Any,
) -> StreamSTT:
    """Create and connect a streaming STT instance.

    Args:
        api_key: Deepgram API key.
        text_callback: Callback for interim results.
        final_callback: Callback for final results.
        **kwargs: Additional config options.

    Returns:
        Connected StreamSTT instance.
    """
    config = StreamSTTConfig(api_key=api_key, **kwargs)
    stt = StreamSTT(config)
    await stt.connect(text_callback, final_callback)
    return stt
