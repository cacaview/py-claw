"""
Transport interface for CLI remote communication.

Provides a unified interface for different transport mechanisms
used to connect to remote Claude Code sessions.

Reference: ClaudeCode-main/src/cli/transports/Transport.ts
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class Transport(ABC):
    """
    Abstract base class for transport implementations.

    All transport types (WebSocket, SSE, Hybrid) must implement
    this interface.
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish the transport connection.

        Raises:
            Exception: If connection fails
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """
        Close the transport connection.

        This should be called when done with the transport,
        or when the connection needs to be terminated.
        """
        ...

    @abstractmethod
    async def send(self, data: str) -> None:
        """
        Send data over the transport.

        Args:
            data: JSON string data to send

        Raises:
            Exception: If send fails
        """
        ...

    def on_data(self, handler: Callable[[str], None]) -> None:
        """
        Register a handler for incoming data.

        Args:
            handler: Callback function that receives the data string
        """
        self._data_handler = handler

    def on_close(self, handler: Callable[[int | None], None]) -> None:
        """
        Register a handler for connection close events.

        Args:
            handler: Callback function that receives the close code
        """
        self._close_handler = handler

    def on_connect(self, handler: Callable[[], None]) -> None:
        """
        Register a handler for connection success.

        Args:
            handler: Callback function called when connected
        """
        self._connect_handler = handler

    def _notify_data(self, data: str) -> None:
        """Internal method to notify data handlers."""
        handler = getattr(self, "_data_handler", None)
        if handler:
            handler(data)

    def _notify_close(self, close_code: int | None = None) -> None:
        """Internal method to notify close handlers."""
        handler = getattr(self, "_close_handler", None)
        if handler:
            handler(close_code)

    def _notify_connect(self) -> None:
        """Internal method to notify connect handlers."""
        handler = getattr(self, "_connect_handler", None)
        if handler:
            handler()

    _data_handler: Callable[[str], None] | None = None
    _close_handler: Callable[[int | None], None] | None = None
    _connect_handler: Callable[[], None] | None = None
