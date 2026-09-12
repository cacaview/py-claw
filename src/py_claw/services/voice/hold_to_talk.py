"""Hold-to-talk audio capture using sounddevice.

Provides a context manager that starts audio capture on enter
(key press) and stops on exit (key release), streaming audio
chunks to the registered callback.

This is a pure Python fallback for the native audio-capture-napi
module used in the TypeScript reference implementation.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from .audio import AudioChunk, AudioInputDevice, AudioError

if TYPE_CHECKING:
    from .types import VoiceConfig

logger = logging.getLogger(__name__)


class HoldToTalk:
    """Hold-to-talk audio capture.

    Starts capture on `start()` (key press), stops on `stop()` (key release).
    Audio chunks are sent to the callback as they arrive.

    Usage:
        htt = HoldToTalk(on_audio=lambda chunk: send_to_stt(chunk))
        htt.start()   # User presses key
        # ... audio is captured and sent to callback ...
        htt.stop()    # User releases key
    """

    def __init__(
        self,
        config: "VoiceConfig | None" = None,
        device_index: int | None = None,
        on_audio: Callable[[AudioChunk], None] | None = None,
        on_release: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize hold-to-talk.

        Args:
            config: VoiceConfig with sample_rate/channels settings.
                   If None, uses defaults (16kHz mono).
            device_index: Audio device index (None for default).
            on_audio: Callback for each audio chunk captured.
            on_release: Callback when recording stops.
            on_error: Callback for audio errors.
        """
        self._config = config
        self._device_index = device_index
        self._on_audio = on_audio
        self._on_release = on_release
        self._on_error = on_error
        self._audio_device: AudioInputDevice | None = None
        self._started = False

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._started and self._audio_device is not None and self._audio_device.is_recording

    def start(self) -> bool:
        """Start audio capture.

        Returns:
            True if capture started successfully, False otherwise.
        """
        if self._started:
            logger.debug("HoldToTalk already started")
            return True

        try:
            # Determine audio parameters
            sample_rate = 16000
            channels = 1

            if self._config is not None:
                sample_rate = getattr(self._config, "sample_rate", 16000)
                channels = getattr(self._config, "channels", 1)

            self._audio_device = AudioInputDevice(
                device_index=self._device_index,
                sample_rate=sample_rate,
                channels=channels,
            )
            self._audio_device.set_callback(self._handle_chunk)
            self._audio_device.start()
            self._started = True
            logger.info("HoldToTalk started recording")
            return True

        except AudioError as e:
            logger.error(f"HoldToTalk audio error: {e}")
            if self._on_error:
                self._on_error(str(e))
            self._audio_device = None
            self._started = False
            return False

    def stop(self) -> None:
        """Stop audio capture."""
        if not self._started:
            return

        if self._audio_device:
            try:
                self._audio_device.stop()
            except Exception as e:
                logger.debug(f"Error stopping audio device: {e}")
            self._audio_device = None

        self._started = False
        logger.info("HoldToTalk stopped recording")

        if self._on_release:
            self._on_release()

    def _handle_chunk(self, chunk: AudioChunk) -> None:
        """Handle an audio chunk from the device."""
        if self._on_audio:
            try:
                self._on_audio(chunk)
            except Exception as e:
                logger.debug(f"Error in audio callback: {e}")

    def __enter__(self) -> "HoldToTalk":
        """Enter context manager - starts recording."""
        self.start()
        return self

    def __exit__(self, exc_type: type, exc_val: exc_type, exc_tb: object) -> None:
        """Exit context manager - stops recording."""
        self.stop()
