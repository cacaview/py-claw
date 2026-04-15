"""
ExtractMemories types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ExtractionStatus(str, Enum):
    """Status of an extraction operation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Result of a memory extraction operation."""

    status: ExtractionStatus
    message: str
    memory_path: str | None = None
    memory_content: str | None = None
    messages_processed: int = 0
    tokens_processed: int = 0
    duration_seconds: float = 0.0
    error: str | None = None


@dataclass
class ExtractionState:
    """State tracking for memory extraction."""

    last_extraction_at: datetime | None = None
    last_extraction_duration: float = 0.0
    total_extractions: int = 0
    failed_extractions: int = 0
    consecutive_failures: int = 0
    messages_since_last_extraction: int = 0
    tokens_since_last_extraction: int = 0
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def record_extraction(self, duration: float, messages: int, tokens: int) -> None:
        """Record a successful extraction."""
        with self._lock:
            self.last_extraction_at = datetime.now(timezone.utc)
            self.last_extraction_duration = duration
            self.total_extractions += 1
            self.consecutive_failures = 0
            self.messages_since_last_extraction = 0
            self.tokens_since_last_extraction = 0

    def record_failure(self) -> None:
        """Record a failed extraction."""
        with self._lock:
            self.failed_extractions += 1
            self.consecutive_failures += 1

    def record_progress(self, messages: int, tokens: int) -> None:
        """Record progress since last extraction."""
        with self._lock:
            self.messages_since_last_extraction += messages
            self.tokens_since_last_extraction += tokens


# Global state
_state: ExtractionState | None = None


def get_extraction_state() -> ExtractionState:
    """Get the global extraction state."""
    global _state
    if _state is None:
        _state = ExtractionState()
    return _state
