"""
Voice stream STT service - Anthropic voice_stream speech-to-text client for push-to-talk.

This service connects to Anthropic's voice_stream WebSocket endpoint using OAuth credentials.
Designed for hold-to-talk: hold the keybinding to record, release to stop and submit.

Note: This is a stub implementation. Full implementation requires:
- WebSocket client integration
- OAuth token management
- Audio chunk handling
- Protocol message handling (KeepAlive, CloseStream, TranscriptText, TranscriptEndpoint)
"""
from __future__ import annotations

from .service import VoiceStreamConnection, VoiceStreamCallbacks, is_voice_stream_available

__all__ = ["VoiceStreamConnection", "VoiceStreamCallbacks", "is_voice_stream_available"]
