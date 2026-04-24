"""Voice service - audio capture and speech-to-text."""
from __future__ import annotations

from .audio import (
    AudioChunk,
    AudioDevice,
    AudioError,
    AudioFileReader,
    AudioInputDevice,
    get_default_input_device,
    list_audio_devices,
)
from .keyterms import (
    KeywordDetector,
    build_keyword_pattern,
    detect_keywords,
    detect_phrase_matches,
    extract_keyword_context,
)
from .hold_to_talk import HoldToTalk
from .service import (
    VoiceError,
    VoiceService,
    get_voice_service,
    start_voice,
    stop_voice,
)
from .stt import STTError, StreamSTT, StreamSTTConfig, TranscriptionResult, create_stream_stt
from .types import AudioSource, STTProvider, VoiceConfig

__all__ = [
    # Types
    "VoiceConfig",
    "AudioDevice",
    "AudioChunk",
    "StreamSTTConfig",
    "TranscriptionResult",
    "AudioSource",
    "STTProvider",
    # Audio
    "AudioInputDevice",
    "AudioFileReader",
    "list_audio_devices",
    "get_default_input_device",
    "AudioError",
    # Hold-to-talk
    "HoldToTalk",
    # STT
    "StreamSTT",
    "StreamSTTConfig",
    "TranscriptionResult",
    "create_stream_stt",
    "STTError",
    # Keyterms
    "detect_keywords",
    "detect_phrase_matches",
    "extract_keyword_context",
    "build_keyword_pattern",
    "KeywordDetector",
    # Service
    "VoiceService",
    "get_voice_service",
    "start_voice",
    "stop_voice",
    "VoiceError",
]
