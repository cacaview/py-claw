"""File state cache with LRU eviction and size limits for fork isolation."""

from __future__ import annotations

from .cache import (
    FileStateCache,
    FileState,
    READ_FILE_STATE_CACHE_SIZE,
    clone_file_state_cache,
    merge_file_state_caches,
    create_file_state_cache_with_size_limit,
)

__all__ = [
    "FileStateCache",
    "FileState",
    "READ_FILE_STATE_CACHE_SIZE",
    "clone_file_state_cache",
    "merge_file_state_caches",
    "create_file_state_cache_with_size_limit",
]
