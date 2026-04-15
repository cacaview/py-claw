"""LRU file state cache with size limits for fork isolation.

This module provides a file state cache that:
1. Normalizes all path keys for consistent cache hits
2. Enforces both entry count and byte-size limits
3. Supports cloning for fork children
4. Supports merging caches with timestamp-based resolution
"""

from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path
from typing import Iterator

from .types import FileState


# Default max entries for read file state caches
READ_FILE_STATE_CACHE_SIZE = 100

# Default size limit for file state caches (25MB)
# Prevents unbounded memory growth from large file contents
DEFAULT_MAX_CACHE_SIZE_BYTES = 25 * 1024 * 1024


def _normalize_path(key: str) -> str:
    """Normalize a path for consistent cache lookups.

    Handles:
    - Mixed path separators on Windows (both / and \\)
    - Redundant segments (e.g., /foo/../bar)
    - Relative paths (./foo)
    """
    # Convert to Path and resolve to handle redundancy
    # On Windows, Path.resolve() uses os.path.abspath()
    try:
        return str(Path(key).resolve())
    except OSError:
        # Fallback: normalize separators and remove redundant parts
        normalized = key.replace("\\", "/")
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        normalized = normalized.strip("/")
        if normalized.startswith("."):
            normalized = normalized[1:] if normalized.startswith("./") else normalized
        return normalized


class FileStateCache:
    """LRU cache for file states with size limits.

    Ensures consistent cache hits regardless of whether callers pass:
    - Relative vs absolute paths
    - Mixed path separators (/ vs \\ on Windows)
    - Redundant path segments (foo/../bar)
    """

    def __init__(
        self,
        max_entries: int = READ_FILE_STATE_CACHE_SIZE,
        max_size_bytes: int = DEFAULT_MAX_CACHE_SIZE_BYTES,
    ) -> None:
        self._max_entries = max_entries
        self._max_size_bytes = max_size_bytes
        self._cache: OrderedDict[str, FileState] = OrderedDict()
        self._current_size: int = 0

    def get(self, key: str) -> FileState | None:
        """Get a file state, moving it to end (most recently used)."""
        normalized = _normalize_path(key)
        if normalized not in self._cache:
            return None
        # Move to end for LRU
        self._cache.move_to_end(normalized)
        return self._cache[normalized]

    def set(self, key: str, value: FileState) -> None:
        """Set a file state, evicting entries if necessary."""
        normalized = _normalize_path(key)

        # Remove existing entry if present
        if normalized in self._cache:
            old_size = self._estimate_size(self._cache[normalized])
            del self._cache[normalized]
            self._current_size -= old_size

        # Calculate size of new entry
        new_size = self._estimate_size(value)

        # Evict entries until we have room
        while self._cache and (len(self._cache) >= self._max_entries or self._current_size + new_size > self._max_size_bytes):
            if not self._cache:
                break
            oldest_key, oldest_value = self._cache.popitem(last=False)
            self._current_size -= self._estimate_size(oldest_value)

        # Add new entry
        self._cache[normalized] = value
        self._current_size += new_size

    def has(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        return _normalize_path(key) in self._cache

    def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        normalized = _normalize_path(key)
        if normalized in self._cache:
            value = self._cache.pop(normalized)
            self._current_size -= self._estimate_size(value)
            return True
        return False

    def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()
        self._current_size = 0

    @property
    def size(self) -> int:
        """Number of entries in the cache."""
        return len(self._cache)

    @property
    def max_entries(self) -> int:
        """Maximum number of entries."""
        return self._max_entries

    @property
    def max_size_bytes(self) -> int:
        """Maximum size in bytes."""
        return self._max_size_bytes

    @property
    def current_size(self) -> int:
        """Current total size in bytes."""
        return self._current_size

    def keys(self) -> Iterator[str]:
        """Iterate over cache keys."""
        return iter(self._cache.keys())

    def items(self) -> Iterator[tuple[str, FileState]]:
        """Iterate over cache items."""
        return iter(self._cache.items())

    def values(self) -> Iterator[FileState]:
        """Iterate over cache values."""
        return iter(self._cache.values())

    def _estimate_size(self, state: FileState) -> int:
        """Estimate memory size of a file state entry."""
        # Base overhead + content size + other fields
        return (
            100  # object overhead
            + len(state.content.encode("utf-8"))
            + (len(str(state.offset)) if state.offset else 0)
            + (len(str(state.limit)) if state.limit else 0)
        )


def create_file_state_cache_with_size_limit(
    max_entries: int = READ_FILE_STATE_CACHE_SIZE,
    max_size_bytes: int = DEFAULT_MAX_CACHE_SIZE_BYTES,
) -> FileStateCache:
    """Factory function to create a size-limited FileStateCache."""
    return FileStateCache(max_entries, max_size_bytes)


def clone_file_state_cache(cache: FileStateCache) -> FileStateCache:
    """Clone a FileStateCache preserving size limit configuration.

    Creates a new cache with the same max entries and max size,
    then copies all entries.
    """
    cloned = FileStateCache(cache.max_entries, cache.max_size_bytes)
    for key, state in cache.items():
        cloned.set(key, state)
    return cloned


def merge_file_state_caches(
    first: FileStateCache,
    second: FileStateCache,
) -> FileStateCache:
    """Merge two file state caches.

    More recent entries (by timestamp) override older ones.
    The result uses first's size limits.
    """
    merged = clone_file_state_cache(first)
    for key, state in second.items():
        existing = merged.get(key)
        # Only override if the new entry is more recent
        if not existing or state.timestamp > existing.timestamp:
            merged.set(key, state)
    return merged
