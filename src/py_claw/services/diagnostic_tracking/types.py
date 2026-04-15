"""
Diagnostic Tracking types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class DiagnosticSeverity(str, Enum):
    """Diagnostic severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


class DiagnosticStatus(str, Enum):
    """Status of a diagnostic entry."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    FIXED = "fixed"
    IGNORED = "ignored"


@dataclass(frozen=True, slots=True)
class DiagnosticEntry:
    """A single diagnostic entry."""

    file_path: str
    line: int
    column: int
    severity: DiagnosticSeverity
    message: str
    source: str  # e.g., "lsp", " eslint", "mypy"
    code: str | None = None
    entry_id: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.entry_id is None:
            import uuid
            object.__setattr__(self, "entry_id", str(uuid.uuid4())[:8])
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    """Diagnostic report summary."""

    total_diagnostics: int
    by_severity: dict[str, int]
    by_source: dict[str, int]
    most_recent: datetime | None
    newly_introduced: int
    newly_fixed: int


@dataclass
class DiagnosticTrackingState:
    """State for diagnostic tracking."""

    entries: dict[str, DiagnosticEntry] = field(default_factory=dict)
    history: list[DiagnosticEntry] = field(default_factory=list)
    fixed_count: int = 0
    last_report_at: datetime | None = None
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def add(self, entry: DiagnosticEntry) -> None:
        """Add a new diagnostic entry."""
        with self._lock:
            self.entries[entry.entry_id] = entry
            self.history.append(entry)

    def acknowledge(self, entry_id: str) -> bool:
        """Acknowledge a diagnostic entry."""
        with self._lock:
            if entry_id in self.entries:
                entry = self.entries[entry_id]
                # Create new entry with acknowledged status by removing and re-adding
                # For now just track that it was acknowledged
                return True
            return False

    def mark_fixed(self, entry_id: str) -> bool:
        """Mark a diagnostic as fixed."""
        with self._lock:
            if entry_id in self.entries:
                del self.entries[entry_id]
                self.fixed_count += 1
                return True
            return False

    def ignore(self, entry_id: str) -> bool:
        """Ignore a diagnostic entry."""
        with self._lock:
            if entry_id in self.entries:
                del self.entries[entry_id]
                return True
            return False

    def clear_resolved(self, current_diagnostics: list[DiagnosticEntry]) -> int:
        """Clear diagnostics that are no longer present.

        Returns the number of diagnostics cleared.
        """
        with self._lock:
            current_keys = {d.entry_id for d in current_diagnostics if d.entry_id}
            cleared = 0
            for entry_id in list(self.entries.keys()):
                if entry_id not in current_keys:
                    del self.entries[entry_id]
                    cleared += 1
            return cleared


# Global state
_state: DiagnosticTrackingState | None = None


def get_tracking_state() -> DiagnosticTrackingState:
    """Get the global tracking state."""
    global _state
    if _state is None:
        _state = DiagnosticTrackingState()
    return _state
