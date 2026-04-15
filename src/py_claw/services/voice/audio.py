"""Audio input device management and capture.

Supports multiple audio backends:
- sounddevice (cross-platform, preferred)
- pyaudio (legacy, fallback)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Iterator

from .types import AudioChunk, AudioDevice, AudioSource

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default audio parameters
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_WIDTH = 2  # 16-bit


class AudioInputDevice:
    """Audio input device for capturing microphone audio.

    Supports context manager protocol for automatic cleanup.
    """

    def __init__(
        self,
        device_index: int | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        dtype: str = "int16",
        blocksize: int = 1024,
    ) -> None:
        """Initialize audio input device.

        Args:
            device_index: Device index (None for default).
            sample_rate: Sample rate in Hz.
            channels: Number of channels.
            dtype: Data type (int16, float32, etc.).
            blocksize: Number of frames per block.
        """
        self._device_index = device_index
        self._sample_rate = sample_rate
        self._channels = channels
        self._dtype = dtype
        self._blocksize = blocksize
        self._stream = None
        self._is_recording = False
        self._thread: threading.Thread | None = None
        self._callback: Callable[[AudioChunk], None] | None = None
        self._stop_event = threading.Event()

    @property
    def sample_rate(self) -> int:
        """Get sample rate."""
        return self._sample_rate

    @property
    def channels(self) -> int:
        """Get number of channels."""
        return self._channels

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording

    def set_callback(self, callback: Callable[[AudioChunk], None]) -> None:
        """Set audio data callback.

        Args:
            callback: Function to call with AudioChunk.
        """
        self._callback = callback

    def start(self) -> None:
        """Start audio capture."""
        if self._is_recording:
            logger.warning("Already recording")
            return

        try:
            import sounddevice as sd

            self._stream = sd.InputStream(
                device=self._device_index,
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype=self._dtype,
                blocksize=self._blocksize,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_recording = True
            logger.info(f"Started audio capture on device {self._device_index}")
        except ImportError:
            raise AudioError("sounddevice not installed. Install with: pip install sounddevice")
        except Exception as e:
            raise AudioError(f"Failed to start audio capture: {e}")

    def stop(self) -> None:
        """Stop audio capture."""
        if not self._is_recording:
            return

        self._stop_event.set()

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug(f"Error stopping stream: {e}")
            self._stream = None

        self._is_recording = False
        self._stop_event.clear()
        logger.info("Stopped audio capture")

    def _audio_callback(
        self,
        indata: Any,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        """Callback for sounddevice stream.

        Args:
            indata: Input audio data.
            frames: Number of frames.
            time_info: Time information.
            status: Status flags.
        """
        if status:
            logger.warning(f"Audio callback status: {status}")

        if self._callback and not self._stop_event.is_set():
            # Convert to bytes
            audio_bytes = indata.tobytes()
            chunk = AudioChunk(
                data=audio_bytes,
                sample_rate=self._sample_rate,
                channels=self._channels,
                width=2,  # 16-bit
                timestamp=int(time.time() * 1000),
            )
            self._callback(chunk)

    def __enter__(self) -> AudioInputDevice:
        """Enter context manager."""
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        self.stop()


class AudioFileReader:
    """Read audio from a file.

    Supports WAV and raw audio files.
    """

    def __init__(
        self,
        file_path: str,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        dtype: str = "int16",
    ) -> None:
        """Initialize audio file reader.

        Args:
            file_path: Path to audio file.
            sample_rate: Sample rate (for raw files).
            channels: Number of channels (for raw files).
            dtype: Data type (for raw files).
        """
        self._file_path = file_path
        self._sample_rate = sample_rate
        self._channels = channels
        self._dtype = dtype
        self._file = None
        self._is_open = False

    def open(self) -> None:
        """Open the audio file."""
        if self._is_open:
            return

        try:
            import soundfile as sf

            self._file = sf.SoundFile(self._file_path, "r")
            self._is_open = True
            self._sample_rate = self._file.samplerate
            self._channels = self._file.channels
            logger.info(f"Opened audio file: {self._file_path}")
        except ImportError:
            # Fallback to wave module
            import wave

            self._file = wave.open(self._file_path, "rb")
            self._is_open = True
            self._sample_rate = self._file.getframerate()
            self._channels = self._file.getnchannels()
            logger.info(f"Opened audio file (wave): {self._file_path}")
        except Exception as e:
            raise AudioError(f"Failed to open audio file: {e}")

    def read_chunks(self, chunk_size: int = 4096) -> Iterator[AudioChunk]:
        """Read audio in chunks.

        Args:
            chunk_size: Number of frames per chunk.

        Yields:
            AudioChunk objects.
        """
        if not self._is_open:
            self.open()

        try:
            import soundfile as sf

            if isinstance(self._file, sf.SoundFile):
                # Use soundfile
                data = self._file.read(chunk_size)
                while len(data) > 0:
                    if data.dtype != "int16":
                        # Convert to int16
                        data = (data * 32767).astype("int16")
                    yield AudioChunk(
                        data=data.tobytes(),
                        sample_rate=self._sample_rate,
                        channels=self._channels,
                        width=2,
                    )
                    data = self._file.read(chunk_size)
            else:
                # Use wave module
                import wave

                if isinstance(self._file, wave.Wave_read):
                    while True:
                        frames = self._file.readframes(chunk_size)
                        if not frames:
                            break
                        yield AudioChunk(
                            data=frames,
                            sample_rate=self._sample_rate,
                            channels=self._channels,
                            width=self._file.getsampwidth(),
                        )
        except Exception as e:
            raise AudioError(f"Error reading audio file: {e}") from e

    def close(self) -> None:
        """Close the audio file."""
        if self._file and self._is_open:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
            self._is_open = False

    def __enter__(self) -> AudioFileReader:
        """Enter context manager."""
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        self.close()


def list_audio_devices() -> list[AudioDevice]:
    """List available audio input devices.

    Returns:
        List of AudioDevice objects.
    """
    try:
        import sounddevice as sd

        devices = []
        info_list = sd.query_devices()
        if isinstance(info_list, dict):
            info_list = [info_list]

        for i, info in enumerate(info_list):
            if info.get("max_input_channels", 0) > 0:
                devices.append(
                    AudioDevice(
                        index=i,
                        name=info.get("name", f"Device {i}"),
                        max_input_channels=info.get("max_input_channels", 0),
                        max_output_channels=info.get("max_output_channels", 0),
                        default_sample_rate=info.get("default_samplerate", 0),
                        host_api=info.get("hostapi", 0),
                    )
                )
        return devices

    except ImportError:
        logger.warning("sounddevice not installed, cannot list devices")
        return []
    except Exception as e:
        logger.error(f"Error listing audio devices: {e}")
        return []


def get_default_input_device() -> AudioDevice | None:
    """Get the default audio input device.

    Returns:
        AudioDevice or None if no default.
    """
    devices = list_audio_devices()
    for d in devices:
        if d.index == -1 or d.name.lower().startswith("default"):
            return d
    return devices[0] if devices else None


class AudioError(Exception):
    """Audio-related errors."""

    pass
