"""
SkillSearch types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class SkillHit:
    """A single skill search hit."""

    name: str
    description: str
    source: str  # "builtin", "custom", "installed"
    relevance_score: float
    argument_hint: str | None = None
    when_to_use: str | None = None
    version: str | None = None


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Result of a skill search."""

    query: str
    hits: list[SkillHit]
    total_hits: int
    search_time_ms: float
    from_cache: bool = False


@dataclass
class SkillSearchState:
    """State for skill search service."""

    search_cache: dict[str, tuple[list[SkillHit], datetime]] = field(default_factory=dict)
    total_searches: int = 0
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def get_cached(self, query_hash: str, ttl: int) -> list[SkillHit] | None:
        """Get cached search results if not expired."""
        with self._lock:
            if query_hash in self.search_cache:
                hits, cached_at = self.search_cache[query_hash]
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age < ttl:
                    return hits
                del self.search_cache[query_hash]
        return None

    def set_cached(self, query_hash: str, hits: list[SkillHit]) -> None:
        """Cache search results."""
        with self._lock:
            self.search_cache[query_hash] = (hits, datetime.now(timezone.utc))
            self.total_searches += 1

    def clear_cache(self) -> None:
        """Clear the search cache."""
        with self._lock:
            self.search_cache.clear()


# Global state
_state: SkillSearchState | None = None


def get_skill_search_state() -> SkillSearchState:
    """Get the global skill search state."""
    global _state
    if _state is None:
        _state = SkillSearchState()
    return _state
