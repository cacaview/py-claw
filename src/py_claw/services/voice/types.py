"""Voice service types and configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class AudioSource(str, Enum):
    """Audio input source type."""

    MICROPHONE = "microphone"
    FILE = "file"
    STREAM = "stream"


class STTProvider(str, Enum):
    """Speech-to-text provider."""

    DEEPGRAM = "deepgram"
    OPENAI = "openai"
    AZURE = "azure"


@dataclass
class VoiceConfig:
    """Configuration for the voice service.

    Attributes:
        provider: STT provider to use.
        api_key: API key for the STT service.
        model: Model to use for transcription.
        language: Language code (e.g., 'en-US').
        sample_rate: Audio sample rate in Hz.
        channels: Number of audio channels.
        encoding: Audio encoding (linear16, opus, etc.).
        keywords: Optional list of keywords to boost.
        endpointing: Enable endpointing (silence detection).
        endpointing_timeout: Timeout in ms for endpoint detection.
        use_stt: Whether to use speech-to-text.
        use_tts: Whether to use text-to-speech.
    """

    provider: STTProvider = STTProvider.DEEPGRAM
    api_key: str | None = None
    model: str = "nova-3"
    language: str = "en-US"
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "linear16"
    keywords: list[str] = field(default_factory=list)
    endpointing: bool = True
    endpointing_timeout: int = 500
    use_stt: bool = True
    use_tts: bool = False

    @classmethod
    def from_env(cls) -> VoiceConfig:
        """Create config from environment variables."""
        api_key = os.environ.get("DEEPGRAM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

        provider = STTProvider.DEEPGRAM
        provider_str = os.environ.get("STT_PROVIDER", "deepgram").lower()
        if provider_str == "openai":
            provider = STTProvider.OPENAI
        elif provider_str == "azure":
            provider = STTProvider.AZURE

        return cls(
            api_key=api_key,
            provider=provider,
            model=os.environ.get("STT_MODEL", "nova-3"),
            language=os.environ.get("STT_LANGUAGE", "en-US"),
        )


@dataclass
class AudioDevice:
    """Audio input/output device information.

    Attributes:
        index: Device index.
        name: Device name.
        max_input_channels: Maximum input channels.
        max_output_channels: Maximum output channels.
        default_sample_rate: Default sample rate.
        host_api: Host API index.
    """

    index: int
    name: str
    max_input_channels: int = 0
    max_output_channels: int = 0
    default_sample_rate: float = 0.0
    host_api: int = 0

    def is_input(self) -> bool:
        """Check if device has input capability."""
        return self.max_input_channels > 0

    def is_output(self) -> bool:
        """Check if device has output capability."""
        return self.max_output_channels > 0


@dataclass
class TranscriptionResult:
    """Result from a transcription.

    Attributes:
        text: Transcribed text.
        is_final: Whether this is a final result.
        confidence: Confidence score (0-1).
        words: Optional word-level timing information.
        speaker: Optional speaker identification.
        language: Detected language.
    """

    text: str
    is_final: bool = True
    confidence: float | None = None
    words: list[dict] = field(default_factory=list)
    speaker: str | None = None
    language: str | None = None


@dataclass
class AudioChunk:
    """Audio data chunk for streaming.

    Attributes:
        data: Raw audio bytes.
        sample_rate: Sample rate of the audio.
        channels: Number of channels.
        width: Bytes per sample (2 for 16-bit).
        timestamp: Timestamp in milliseconds.
    """

    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    width: int = 2
    timestamp: int = 0


@dataclass
class StreamSTTConfig:
    """Configuration for streaming STT.

    Attributes:
        api_key: STT API key.
        model: Model to use.
        language: Language code.
        encoding: Audio encoding.
        sample_rate: Sample rate.
        channels: Number of channels.
        interim_results: Whether to return interim results.
        punctuate: Whether to punctuate results.
        profanity_filter: Whether to filter profanity.
        endpointing_callback: Callback for endpoint detection.
        result_callback: Callback for transcription results.
    """

    api_key: str
    model: str = "nova-3"
    language: str = "en-US"
    encoding: str = "linear16"
    sample_rate: int = 16000
    channels: int = 1
    interim_results: bool = True
    punctuate: bool = True
    profanity_filter: bool = False
    endpointing_callback: callable | None = None
    result_callback: callable | None = None
