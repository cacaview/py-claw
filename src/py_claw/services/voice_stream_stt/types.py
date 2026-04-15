"""
Types for the voice stream STT service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class VoiceStreamCallbacks(Protocol):
    """Callbacks for voice stream events."""

    def on_transcript(self, text: str, is_final: bool) -> None:
        """Called when transcript text is received (text, is_final)."""
        ...

    def on_error(self, error: str, *, fatal: bool = False) -> None:
        """Called when an error occurs."""
        ...

    def on_close(self) -> None:
        """Called when the connection closes."""
        ...

    def on_ready(self, connection: VoiceStreamConnection) -> None:
        """Called when the connection is ready."""
        ...


@dataclass(slots=True)
class VoiceStreamCallbacksImpl:
    """Concrete implementation of VoiceStreamCallbacks using callable objects."""

    on_transcript: Callable[[str, bool], None]
    """Called when transcript text is received (text, is_final)"""

    on_error: Callable[[str], None]
    """Called when an error occurs"""

    on_close: Callable[[], None]
    """Called when the connection closes"""

    on_ready: Callable[[VoiceStreamConnection], None]
    """Called when the connection is ready"""

    def on_error_with_opts(self, error: str, *, fatal: bool = False) -> None:
        """Error callback with optional fatal flag."""
        self.on_error(error)


# How finalize() resolved. `no_data_timeout` means zero server messages
# after CloseStream — the silent-drop signature.
FinalizeSource = str
"""One of: 'post_closestream_endpoint', 'no_data_timeout', 'safety_timeout', 'ws_close', 'ws_already_closed'"""


@dataclass(slots=True)
class VoiceStreamConnection:
    """Connection to the voice stream STT service."""

    def send(self, audio_chunk: bytes) -> None:
        """Send an audio chunk to the service."""
        ...

    async def finalize(self) -> str:
        """
        Finalize the stream and get the final transcript.

        Returns:
            How the finalize resolved: 'post_closestream_endpoint', 'no_data_timeout',
            'safety_timeout', 'ws_close', or 'ws_already_closed'
        """
        return "ws_already_closed"

    def close(self) -> None:
        """Close the connection."""
        ...

    def is_connected(self) -> bool:
        """Check if the connection is still open."""
        return False


# Voice stream endpoint message types
@dataclass(slots=True)
class VoiceStreamTranscriptText:
    """Transcript text message from the server."""
    type: str = "TranscriptText"
    data: str = ""


@dataclass(slots=True)
class VoiceStreamTranscriptEndpoint:
    """Transcript endpoint marker from the server."""
    type: str = "TranscriptEndpoint"


@dataclass(slots=True)
class VoiceStreamTranscriptError:
    """Transcript error message from the server."""
    type: str = "TranscriptError"
    error_code: str | None = None
    description: str | None = None


@dataclass(slots=True)
class VoiceStreamError:
    """Generic error message from the server."""
    type: str = "error"
    message: str | None = None


VoiceStreamMessage = VoiceStreamTranscriptText | VoiceStreamTranscriptEndpoint | VoiceStreamTranscriptError | VoiceStreamError
"""Union of possible messages from the voice stream endpoint."""
