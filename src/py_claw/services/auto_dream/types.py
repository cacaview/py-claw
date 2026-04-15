"""
AutoDream types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class DreamStatus(str, Enum):
    """Status of an auto dream operation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class DreamResult:
    """Result of a dream operation."""

    status: DreamStatus
    message: str
    duration_seconds: float = 0.0
    tokens_processed: int = 0
    error: str | None = None


@dataclass
class DreamState:
    """State tracking for auto dream."""

    last_dream_at: datetime | None = None
    last_dream_duration: float = 0.0
    total_dreams: int = 0
    failed_dreams: int = 0
    consecutive_failures: int = 0
    messages_since_last_dream: int = 0
    tokens_since_last_dream: int = 0
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def record_dream(self, duration: float, tokens: int) -> None:
        """Record a successful dream."""
        with self._lock:
            self.last_dream_at = datetime.now(timezone.utc)
            self.last_dream_duration = duration
            self.total_dreams += 1
            self.consecutive_failures = 0
            self.messages_since_last_dream = 0
            self.tokens_since_last_dream = 0

    def record_failure(self) -> None:
        """Record a failed dream."""
        with self._lock:
            self.failed_dreams += 1
            self.consecutive_failures += 1

    def record_progress(self, messages: int, tokens: int) -> None:
        """Record progress since last dream."""
        with self._lock:
            self.messages_since_last_dream += messages
            self.tokens_since_last_dream += tokens


# Global state
_state: DreamState | None = None


def get_dream_state() -> DreamState:
    """Get the global dream state."""
    global _state
    if _state is None:
        _state = DreamState()
    return _state
