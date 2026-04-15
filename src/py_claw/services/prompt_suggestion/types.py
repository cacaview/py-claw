"""
PromptSuggestion types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SuggestionCategory(str, Enum):
    """Categories for prompt suggestions."""

    CODING = "coding"
    REVIEW = "review"
    DEBUG = "debug"
    REFACTOR = "refactor"
    DOCS = "docs"
    GENERAL = "general"


@dataclass(frozen=True, slots=True)
class PromptSuggestion:
    """A single prompt suggestion."""

    text: str
    category: SuggestionCategory
    relevance_score: float = 0.5
    description: str | None = None


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    """Result of getting prompt suggestions."""

    suggestions: list[PromptSuggestion]
    context_hash: str | None = None
    generated_at: datetime | None = None
    from_cache: bool = False


@dataclass
class SuggestionState:
    """State for prompt suggestion service."""

    last_suggestion_at: datetime | None = None
    total_suggestions: int = 0
    cache: dict[str, tuple[list[PromptSuggestion], datetime]] = field(default_factory=dict)
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def get_cached(self, context_hash: str, ttl: int) -> list[PromptSuggestion] | None:
        """Get cached suggestions if not expired."""
        with self._lock:
            if context_hash in self.cache:
                suggestions, cached_at = self.cache[context_hash]
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age < ttl:
                    return suggestions
                del self.cache[context_hash]
        return None

    def set_cached(self, context_hash: str, suggestions: list[PromptSuggestion]) -> None:
        """Cache suggestions."""
        with self._lock:
            self.cache[context_hash] = (suggestions, datetime.now(timezone.utc))
            self.total_suggestions += 1

    def clear_cache(self) -> None:
        """Clear all cached suggestions."""
        with self._lock:
            self.cache.clear()


# Global state
_state: SuggestionState | None = None


def get_suggestion_state() -> SuggestionState:
    """Get the global suggestion state."""
    global _state
    if _state is None:
        _state = SuggestionState()
    return _state
