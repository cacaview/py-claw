"""
Context Collapse types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CollapseStrategy(str, Enum):
    """Context collapse strategy."""

    BOUNDARY = "boundary"  # Collapse at message boundaries
    IMPORTANCE = "importance"  # Collapse by importance scoring
    HYBRID = "hybrid"  # Combination of both


class CollapseStatus(str, Enum):
    """Status of a collapse operation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CollapsedChunk:
    """A collapsed chunk of messages."""

    id: str
    original_message_ids: list[str]
    summary: str
    importance_score: float
    token_count: int
    preserved: bool = False


@dataclass(frozen=True, slots=True)
class CollapseResult:
    """Result of a context collapse operation."""

    status: CollapseStatus
    original_token_count: int
    collapsed_token_count: int
    chunks: list[CollapsedChunk]
    preserved_message_count: int
    collapsed_message_count: int
    strategy_used: CollapseStrategy
    message: str


@dataclass
class CollapseState:
    """State tracking for context collapse."""

    last_collapse_at: datetime | None = None
    total_collapses: int = 0
    total_tokens_saved: int = 0
    consecutive_failures: int = 0
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def record_collapse(self, tokens_saved: int) -> None:
        """Record a successful collapse."""
        with self._lock:
            self.last_collapse_at = datetime.now(timezone.utc)
            self.total_collapses += 1
            self.total_tokens_saved += tokens_saved
            self.consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed collapse."""
        with self._lock:
            self.consecutive_failures += 1


# Global state
_state: CollapseState | None = None


def get_collapse_state() -> CollapseState:
    """Get the global collapse state."""
    global _state
    if _state is None:
        _state = CollapseState()
    return _state
