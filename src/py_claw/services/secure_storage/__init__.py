"""Secure storage utilities - platform-specific secure storage (Keychain, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .secure_storage import (
    SecureStorage,
    get_secure_storage,
    PlainTextStorage,
)
from .keychain_helpers import (
    macos_keychain_storage,
    create_fallback_storage,
)

__all__ = [
    "SecureStorage",
    "get_secure_storage",
    "PlainTextStorage",
    "macos_keychain_storage",
    "create_fallback_storage",
]
