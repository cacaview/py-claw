"""
Types for the tips service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    pass


@dataclass(slots=True)
class Tip:
    """A tip that can be shown to the user."""

    id: str
    content: str | Callable[[], Awaitable[str]]
    cooldown_sessions: int = 0
    is_relevant: Callable[[TipContext | None], bool | Awaitable[bool]] = lambda _: True


@dataclass(slots=True)
class TipContext:
    """Context information used to determine tip relevance."""

    bash_tools: set[str] | None = None
    read_file_state: dict[str, object] | None = None
    theme: str | None = None
