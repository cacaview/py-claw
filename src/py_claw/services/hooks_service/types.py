"""
Types for hooks_service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HookEvent:
    """A hook event."""
    name: str
    description: str
    available: bool = True


@dataclass
class HookEntry:
    """A configured hook entry."""
    event: str
    command: str
    enabled: bool = True


@dataclass
class HooksServiceConfig:
    """Configuration for hooks service."""
    pass


@dataclass
class HooksServiceResult:
    """Result of hooks operation."""
    success: bool
    message: str
    hooks: list[HookEntry] | None = None
