"""Voice service - high-level voice input management.

Provides a unified interface for voice input with transcription,
keyword detection, and session lifecycle management.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from .audio import AudioChunk, AudioError, AudioInputDevice
from .stt import STTError, StreamSTT, TranscriptionResult
from .types import AudioDevice, VoiceConfig
from .keyterms import detect_keywords

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class VoiceService:
    """High-level voice service for audio capture and transcription.

    Manages audio input devices, STT connections, and provides
    callbacks for transcription results.
    """

    def __init__(
        self,
        config: VoiceConfig | None = None,
        audio_device: int | None = None,
    ) -> None:
        """Initialize voice service.

        Args:
            config: Voice configuration.
            audio_device: Audio device index (None for default).
        """
        self._config = config or VoiceConfig.from_env()
        self._audio_device_index = audio_device
        self._audio: AudioInputDevice | None = None
        self._stt: StreamSTT | None = None
        self._is_active = False
        self._transcript_callback: Callable[[str], Awaitable[None]] | None = None
        self._keyword_callback: Callable[[list[str]], Awaitable[None]] | None = None

    @property
    def is_active(self) -> bool:
        """Check if voice service is currently active."""
        return self._is_active

    @property
    def config(self) -> VoiceConfig:
        """Get voice configuration."""
        return self._config

    async def start(
        self,
        transcript_callback: Callable[[str], Awaitable[None]] | None = None,
        keyword_callback: Callable[[list[str]], Awaitable[None]] | None = None,
    ) -> None:
        """Start voice capture and transcription.

        Args:
            transcript_callback: Callback for transcribed text.
            keyword_callback: Callback for detected keywords.
        """
        if self._is_active:
            logger.warning("Voice service already active")
            return

        self._transcript_callback = transcript_callback
        self._keyword_callback = keyword_callback

        try:
            # Connect to STT
            await self._connect_stt()

            # Start audio capture
            self._start_audio()

            self._is_active = True
            logger.info("Voice service started")
        except Exception as e:
            await self.stop()
            raise VoiceError(f"Failed to start voice service: {e}") from e

    async def stop(self) -> None:
        """Stop voice capture and transcription."""
        if not self._is_active:
            return

        # Stop audio capture
        if self._audio:
            try:
                self._audio.stop()
            except Exception as e:
                logger.debug(f"Error stopping audio: {e}")
            self._audio = None

        # Disconnect STT
        if self._stt:
            try:
                await self._stt.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting STT: {e}")
            self._stt = None

        self._is_active = False
        logger.info("Voice service stopped")

    async def _connect_stt(self) -> None:
        """Connect to the STT service."""
        if not self._config.use_stt:
            return

        if not self._config.api_key:
            raise VoiceError("No STT API key configured")

        async def on_transcript(result: TranscriptionResult) -> None:
            """Handle transcription result."""
            await self._handle_transcript(result)

        self._stt = StreamSTT(
            config=StreamSTTConfig(
                api_key=self._config.api_key,
                model=self._config.model,
                language=self._config.language,
                encoding=self._config.encoding,
                sample_rate=self._config.sample_rate,
                channels=self._config.channels,
                interim_results=True,
            )
        )

        await self._stt.connect(
            text_callback=on_transcript,
            final_callback=on_transcript,
        )

    def _start_audio(self) -> None:
        """Start audio capture."""
        if not self._config.use_stt:
            return

        self._audio = AudioInputDevice(
            device_index=self._audio_device_index,
            sample_rate=self._config.sample_rate,
            channels=self._config.channels,
        )

        def on_audio(chunk: AudioChunk) -> None:
            """Handle audio chunk."""
            if self._stt and self._stt.is_connected:
                asyncio.create_task(self._stt.send_audio(chunk))

        self._audio.set_callback(on_audio)
        self._audio.start()

    async def _handle_transcript(self, result: TranscriptionResult) -> None:
        """Handle transcription result.

        Args:
            result: Transcription result.
        """
        if not result.text.strip():
            return

        # Check for keywords
        if self._config.keywords and self._keyword_callback:
            detected = detect_keywords(result.text, self._config.keywords)
            if detected:
                await self._keyword_callback(detected)

        # Send transcript callback
        if self._transcript_callback:
            await self._transcript_callback(result.text)

    async def send_audio(self, chunk: AudioChunk) -> None:
        """Send audio data directly to STT.

        Args:
            chunk: Audio chunk to send.
        """
        if self._stt and self._stt.is_connected:
            await self._stt.send_audio(chunk)

    def get_audio_devices(self) -> list[AudioDevice]:
        """Get available audio input devices.

        Returns:
            List of available devices.
        """
        from .audio import list_audio_devices

        return list_audio_devices()

    def set_keywords(self, keywords: list[str]) -> None:
        """Set keywords to detect.

        Args:
            keywords: List of keywords to look for.
        """
        self._config.keywords = keywords

    def __await__(self) -> Any:
        """Allow await on service."""
        return self.start().__await__()


class VoiceError(Exception):
    """Voice service errors."""

    pass


# Global service instance
_service: VoiceService | None = None


def get_voice_service(
    config: VoiceConfig | None = None,
    audio_device: int | None = None,
) -> VoiceService:
    """Get the global VoiceService singleton.

    Args:
        config: Optional voice configuration.
        audio_device: Optional audio device index.

    Returns:
        VoiceService instance.
    """
    global _service
    if _service is None:
        _service = VoiceService(config=config, audio_device=audio_device)
    return _service


async def start_voice(
    transcript_callback: Callable[[str], Awaitable[None]] | None = None,
    keyword_callback: Callable[[list[str]], Awaitable[None]] | None = None,
) -> VoiceService:
    """Start the global voice service.

    Args:
        transcript_callback: Callback for transcribed text.
        keyword_callback: Callback for detected keywords.

    Returns:
        VoiceService instance.
    """
    service = get_voice_service()
    await service.start(transcript_callback, keyword_callback)
    return service


async def stop_voice() -> None:
    """Stop the global voice service."""
    global _service
    if _service:
        await _service.stop()
