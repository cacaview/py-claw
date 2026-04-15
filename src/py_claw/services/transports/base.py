"""Transport interface for structured CLI I/O.

Defines the minimal contract for connect/send/close used by
StructuredIO and RemoteIO.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Transport(ABC):
    """Abstract transport interface.

    Concrete implementations handle WebSocket, SSE, HTTP POST, or hybrid
    read/write strategies.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish the transport connection."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the transport connection."""
        ...

    @abstractmethod
    async def send(self, data: str) -> None:
        """Send data through the transport."""
        ...

    def on_data(self, handler: callable) -> None:
        """Register a handler for incoming data."""
        ...

    def on_close(self, handler: callable) -> None:
        """Register a handler for connection close events."""
        ...
