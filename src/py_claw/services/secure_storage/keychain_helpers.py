"""macOS Keychain helpers for secure storage."""

from __future__ import annotations

import subprocess
from typing import Any

from .secure_storage import SecureStorage


class MacOsKeychainStorage(SecureStorage):
    """macOS Keychain-based secure storage."""

    def __init__(self, service: str = "com.claude.code") -> None:
        self._service = service

    async def get(self, key: str) -> str | None:
        """Get a value from macOS Keychain."""
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    self._service,
                    "-a",
                    key,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    async def set(self, key: str, value: str) -> None:
        """Set a value in macOS Keychain."""
        # First try to delete existing item
        await self.delete(key)
        try:
            subprocess.run(
                [
                    "security",
                    "add-generic-password",
                    "-s",
                    self._service,
                    "-a",
                    key,
                    "-w",
                    value,
                ],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        """Delete a value from macOS Keychain."""
        try:
            subprocess.run(
                [
                    "security",
                    "delete-generic-password",
                    "-s",
                    self._service,
                    "-a",
                    key,
                ],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

    async def exists(self, key: str) -> bool:
        """Check if a key exists in macOS Keychain."""
        return await self.get(key) is not None


def macos_keychain_storage(service: str = "com.claude.code") -> MacOsKeychainStorage:
    """Create a macOS Keychain storage instance."""
    return MacOsKeychainStorage(service)
