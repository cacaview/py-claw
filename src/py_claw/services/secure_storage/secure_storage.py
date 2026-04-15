"""Secure storage abstract interface and implementations."""

from __future__ import annotations

import os
import platform
from abc import ABC, abstractmethod
from typing import Any


class SecureStorage(ABC):
    """Abstract interface for secure storage."""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Get a value from secure storage."""
        pass

    @abstractmethod
    async def set(self, key: str, value: str) -> None:
        """Set a value in secure storage."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a value from secure storage."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in secure storage."""
        pass


class PlainTextStorage(SecureStorage):
    """
    Plain text storage implementation.

    Used as fallback on platforms without secure storage.
    WARNING: Stores values in plaintext - not secure!
    """

    def __init__(self) -> None:
        self._storage: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._storage.get(key)

    async def set(self, key: str, value: str) -> None:
        self._storage[key] = value

    async def delete(self, key: str) -> None:
        self._storage.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._storage


def get_secure_storage() -> SecureStorage:
    """
    Get the appropriate secure storage implementation for the current platform.

    macOS: Uses Keychain
    Linux: Falls back to plaintext (TODO: add libsecret support)
    Windows: Falls back to plaintext
    """
    system = platform.system()

    if system == "Darwin":
        # Would use macOS Keychain in full implementation
        return create_fallback_storage(macos_keychain_storage(), PlainTextStorage())

    # TODO: Add libsecret support for Linux

    return PlainTextStorage()


def create_fallback_storage(primary: SecureStorage, fallback: SecureStorage) -> SecureStorage:
    """
    Create a storage that tries primary and falls back to fallback on error.

    Useful for platforms where secure storage might fail (e.g., no keychain access).
    """

    class FallbackStorage(SecureStorage):
        async def get(self, key: str) -> str | None:
            try:
                return await primary.get(key)
            except Exception:
                return await fallback.get(key)

        async def set(self, key: str, value: str) -> None:
            try:
                await primary.set(key, value)
            except Exception:
                await fallback.set(key, value)

        async def delete(self, key: str) -> None:
            try:
                await primary.delete(key)
            except Exception:
                await fallback.delete(key)

        async def exists(self, key: str) -> bool:
            try:
                return await primary.exists(key)
            except Exception:
                return await fallback.exists(key)

    return FallbackStorage()
