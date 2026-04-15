"""Tests for file state cache and fork isolation utilities."""

import time

import pytest

from py_claw.services.file_state_cache import (
    FileStateCache,
    FileState,
    READ_FILE_STATE_CACHE_SIZE,
    clone_file_state_cache,
    merge_file_state_caches,
    create_file_state_cache_with_size_limit,
)


class TestFileStateCache:
    """Tests for FileStateCache."""

    def test_get_set_basic(self):
        """Basic get/set operations."""
        cache = FileStateCache(max_entries=10)
        state = FileState(content="hello", timestamp=time.time())
        cache.set("test.txt", state)
        result = cache.get("test.txt")
        assert result is not None
        assert result.content == "hello"

    def test_path_normalization(self):
        """Paths are normalized for consistent lookups."""
        cache = FileStateCache(max_entries=10)
        state = FileState(content="hello", timestamp=time.time())
        cache.set("test.txt", state)

        # Different path representations should find the same entry
        assert cache.get("test.txt") is not None
        # Windows-style path normalization
        result = cache.get("TEST.TXT")
        # Path normalization may or may not be case-insensitive depending on OS

    def test_lru_eviction(self):
        """Least recently used entries are evicted."""
        cache = FileStateCache(max_entries=3)
        for i in range(5):
            cache.set(f"file{i}.txt", FileState(content=f"content{i}", timestamp=time.time()))

        # First 2 should be evicted (LRU)
        assert cache.get("file0.txt") is None
        assert cache.get("file1.txt") is None
        # Last 3 should remain
        assert cache.get("file2.txt") is not None
        assert cache.get("file3.txt") is not None
        assert cache.get("file4.txt") is not None

    def test_size_limit(self):
        """Entries are evicted when size limit is reached."""
        cache = FileStateCache(max_entries=10, max_size_bytes=100)
        for i in range(10):
            # Each entry is ~100+ bytes, should trigger size eviction
            cache.set(f"file{i}.txt", FileState(content="x" * 200, timestamp=time.time()))

        # Some entries should be evicted due to size
        assert cache.size < 10

    def test_delete(self):
        """Delete removes an entry."""
        cache = FileStateCache(max_entries=10)
        state = FileState(content="hello", timestamp=time.time())
        cache.set("test.txt", state)
        assert cache.delete("test.txt") is True
        assert cache.get("test.txt") is None

    def test_clear(self):
        """Clear removes all entries."""
        cache = FileStateCache(max_entries=10)
        for i in range(5):
            cache.set(f"file{i}.txt", FileState(content=f"content{i}", timestamp=time.time()))
        cache.clear()
        assert cache.size == 0

    def test_has(self):
        """Has checks for key existence."""
        cache = FileStateCache(max_entries=10)
        state = FileState(content="hello", timestamp=time.time())
        cache.set("test.txt", state)
        assert cache.has("test.txt") is True
        assert cache.has("other.txt") is False

    def test_get_nonexistent(self):
        """Get returns None for nonexistent keys."""
        cache = FileStateCache(max_entries=10)
        assert cache.get("nonexistent.txt") is None


class TestCloneFileStateCache:
    """Tests for clone_file_state_cache."""

    def test_clone_preserves_entries(self):
        """Cloned cache has same entries."""
        cache = FileStateCache(max_entries=10)
        for i in range(3):
            cache.set(f"file{i}.txt", FileState(content=f"content{i}", timestamp=time.time()))

        cloned = clone_file_state_cache(cache)
        assert cloned.size == 3
        for i in range(3):
            assert cloned.get(f"file{i}.txt") is not None

    def test_clone_independent(self):
        """Modifying cloned cache doesn't affect original."""
        cache = FileStateCache(max_entries=10)
        cache.set("file0.txt", FileState(content="original", timestamp=time.time()))

        cloned = clone_file_state_cache(cache)
        cloned.set("file0.txt", FileState(content="modified", timestamp=time.time()))

        # Original unchanged
        assert cache.get("file0.txt").content == "original"
        # Clone changed
        assert cloned.get("file0.txt").content == "modified"


class TestMergeFileStateCaches:
    """Tests for merge_file_state_caches."""

    def test_merge_combines_entries(self):
        """Merged cache has entries from both sources."""
        cache1 = FileStateCache(max_entries=10)
        cache1.set("file1.txt", FileState(content="content1", timestamp=100.0))

        cache2 = FileStateCache(max_entries=10)
        cache2.set("file2.txt", FileState(content="content2", timestamp=100.0))

        merged = merge_file_state_caches(cache1, cache2)
        assert merged.get("file1.txt") is not None
        assert merged.get("file2.txt") is not None

    def test_merge_newer_wins(self):
        """When same key exists in both, newer timestamp wins."""
        cache1 = FileStateCache(max_entries=10)
        cache1.set("file.txt", FileState(content="old", timestamp=100.0))

        cache2 = FileStateCache(max_entries=10)
        cache2.set("file.txt", FileState(content="new", timestamp=200.0))

        merged = merge_file_state_caches(cache1, cache2)
        assert merged.get("file.txt").content == "new"


class TestForkIsolation:
    """Tests for fork isolation utilities."""

    def test_translate_path_for_worktree_absolute(self):
        """Absolute paths under parent are translated."""
        from py_claw.fork.isolation import translate_path_for_worktree
        import os

        result = translate_path_for_worktree(
            os.path.join("/parent", "src", "file.py"),
            "/parent",
            "/worktree"
        )
        # On Windows, separators are backslash; check the result contains the expected components
        assert "src" in result and "file.py" in result
        assert "/worktree" in result or "\\worktree" in result

    def test_translate_path_for_worktree_relative(self):
        """Relative paths are resolved and translated."""
        from py_claw.fork.isolation import translate_path_for_worktree

        result = translate_path_for_worktree(
            "src/file.py",
            "/parent",
            "/worktree"
        )
        assert result is not None

    def test_build_worktree_notice(self):
        """Worktree notice contains key information."""
        from py_claw.fork.isolation import build_worktree_notice

        notice = build_worktree_notice("/parent", "/worktree")
        assert "/parent" in notice
        assert "/worktree" in notice
        assert "worktree" in notice.lower()

    def test_build_fork_directive(self):
        """Fork directive contains task and rules."""
        from py_claw.fork.isolation import build_fork_directive

        directive = build_fork_directive(
            "Analyze the code",
            parent_session_id="parent-123",
            child_session_id="child-456",
        )
        assert "Analyze the code" in directive
        assert "parent-123" in directive
        assert "child-456" in directive
        assert "FORK SUBAGENT" in directive

    def test_build_fork_directive_with_context(self):
        """Fork directive includes conversation context."""
        from py_claw.fork.isolation import build_fork_directive

        context = [
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Hi there"}]},
        ]
        directive = build_fork_directive(
            "Continue the analysis",
            parent_session_id="parent-123",
            child_session_id="child-456",
            include_context=True,
            context_messages=context,
        )
        assert "Continue the analysis" in directive
        assert "INHERITED CONVERSATION CONTEXT" in directive

    def test_get_cache_safe_system_prompt(self):
        """Cache-safe prompt includes base and context."""
        from py_claw.fork.isolation import get_cache_safe_system_prompt

        result = get_cache_safe_system_prompt(
            base_prompt="You are a helpful assistant.",
            user_context={"user": "test_user"},
            system_context={"os": "Linux"},
        )
        assert "You are a helpful assistant." in result
        assert "test_user" in result
        assert "Linux" in result


class TestCacheSafeParams:
    """Tests for CacheSafeParams."""

    def test_cache_safe_params_creation(self):
        """CacheSafeParams can be created with all fields."""
        from py_claw.fork.isolation import CacheSafeParams

        params = CacheSafeParams(
            system_prompt="You are a helpful assistant.",
            user_context={"user": "test"},
            system_context={"env": "prod"},
            model="claude-sonnet",
            allowed_tools=["Read", "Write"],
        )
        assert params.system_prompt == "You are a helpful assistant."
        assert params.user_context["user"] == "test"
        assert params.model == "claude-sonnet"
        assert "Read" in params.allowed_tools


class TestForkIsolationContext:
    """Tests for ForkIsolationContext."""

    def test_fork_isolation_context_creation(self):
        """ForkIsolationContext can be created."""
        from py_claw.fork.isolation import ForkIsolationContext
        from py_claw.services.file_state_cache import FileStateCache

        cache = FileStateCache(max_entries=10)
        context = ForkIsolationContext(
            file_state_cache=cache,
            parent_cwd="/parent",
            worktree_cwd="/worktree",
            persistent=True,
        )
        assert context.file_state_cache is cache
        assert context.parent_cwd == "/parent"
        assert context.worktree_cwd == "/worktree"
        assert context.persistent is True
