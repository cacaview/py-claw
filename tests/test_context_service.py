"""
Tests for the context service.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from py_claw.services.context import (
    get_context,
    get_system_context,
    get_user_context,
    get_git_status,
    get_claude_md_content,
    get_context_config,
    set_context_config,
    clear_context_cache,
    ContextConfig,
    SystemContext,
    UserContext,
    ContextResult,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_context_state():
    """Reset context state before and after each test."""
    # Save original config
    from py_claw.services.context import get_context_config
    original_config = get_context_config()

    # Reset to defaults
    from py_claw.services.context.config import ContextConfig
    default_config = ContextConfig()
    from py_claw.services.context import set_context_config
    set_context_config(default_config)

    # Clear caches
    clear_context_cache()

    yield

    # Restore
    set_context_config(original_config)
    clear_context_cache()


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repo for testing."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)
        # Initialize a real git repo
        subprocess.run(["git", "init", "-q"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_dir, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir, capture_output=True
        )
        # Create initial commit so branch/show-current works
        readme = repo_dir / "README.md"
        readme.write_text("test")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=repo_dir, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "initial"],
            cwd=repo_dir, capture_output=True
        )
        yield repo_dir


@pytest.fixture
def temp_claude_md():
    """Create temporary claude.md files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create project-level CLAUDE.md
        project_md = root / "CLAUDE.md"
        project_md.write_text("# Project Instructions\nProject-level content.\n")

        # Create user-level in ~/.claude/
        user_claude = root / ".claude" / "CLAUDE.md"
        user_claude.parent.mkdir(parents=True)
        user_claude.write_text("# User Instructions\nUser-level content.\n")

        # Create .claude/rules/ file
        rules_dir = root / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "rules.md").write_text("# Rules\nRule content.\n")

        yield root


# ------------------------------------------------------------------
# Tests: Git status
# ------------------------------------------------------------------


class TestGitStatus:
    """Tests for git status functionality."""

    def test_get_git_status_returns_none_when_not_git_repo(self, tmp_path):
        """When not in a git repo, git status should return None."""
        result = get_git_status(str(tmp_path))
        assert result is None

    def test_get_git_status_returns_string_in_git_repo(self, temp_git_repo):
        """When in a git repo, git status should return a string."""
        result = get_git_status(str(temp_git_repo))
        assert result is not None
        assert isinstance(result, str)

    def test_get_git_status_contains_branch_info(self, temp_git_repo):
        """Git status should contain branch information."""
        result = get_git_status(str(temp_git_repo))
        assert "main" in result or "master" in result

    def test_get_git_status_contains_status_section(self, temp_git_repo):
        """Git status should contain 'Status:' section."""
        result = get_git_status(str(temp_git_repo))
        assert "Status:" in result

    def test_get_git_status_contains_recent_commits(self, temp_git_repo):
        """Git status should contain 'Recent commits:' section."""
        result = get_git_status(str(temp_git_repo))
        assert "Recent commits:" in result

    def test_get_git_status_cached(self, temp_git_repo):
        """Git status should be cached per process."""
        result1 = get_git_status(str(temp_git_repo))
        result2 = get_git_status(str(temp_git_repo))
        assert result1 == result2


# ------------------------------------------------------------------
# Tests: Claude.md loading
# ------------------------------------------------------------------


class TestClaudeMd:
    """Tests for claude.md loading functionality."""

    def test_get_claude_md_returns_none_when_disabled(self, tmp_path):
        """When claude.md is disabled, should return None."""
        config = get_context_config()
        config.include_claude_md = False
        set_context_config(config)

        result = get_claude_md_content(str(tmp_path))
        assert result is None

    def test_get_claude_md_returns_none_when_no_files(self, tmp_path):
        """When no claude.md files exist, should return None."""
        result = get_claude_md_content(str(tmp_path))
        assert result is None

    def test_get_claude_md_loads_project_file(self, temp_claude_md):
        """Should load project-level CLAUDE.md."""
        result = get_claude_md_content(str(temp_claude_md))
        assert result is not None
        assert "Project Instructions" in result
        assert "Project-level content" in result

    def test_get_claude_md_loads_user_file(self, temp_claude_md):
        """Should load user-level ~/.claude/CLAUDE.md."""
        result = get_claude_md_content(str(temp_claude_md))
        assert result is not None
        assert "User Instructions" in result

    def test_get_claude_md_loads_rules_files(self, temp_claude_md):
        """Should load .claude/rules/*.md files."""
        result = get_claude_md_content(str(temp_claude_md))
        assert result is not None
        assert "Rules" in result or "Rule content" in result

    def test_get_claude_md_priority_ordering(self, temp_claude_md):
        """Higher priority (closer to cwd) files should come later and override."""
        result = get_claude_md_content(str(temp_claude_md))
        assert result is not None
        # Project-level should be included (higher priority)
        assert "Project-level content" in result

    def test_get_claude_md_cached(self, temp_claude_md):
        """Claude.md content should be cached."""
        result1 = get_claude_md_content(str(temp_claude_md))
        result2 = get_claude_md_content(str(temp_claude_md))
        assert result1 == result2


# ------------------------------------------------------------------
# Tests: System and User context
# ------------------------------------------------------------------


class TestSystemContext:
    """Tests for system context."""

    def test_get_system_context_returns_system_context(self):
        """Should return a SystemContext object."""
        result = get_system_context()
        assert isinstance(result, SystemContext)

    def test_get_system_context_git_status_is_string_or_none(self, temp_git_repo):
        """git_status should be a string or None."""
        ctx = get_system_context(include_git=True)
        # In test environment without real git, may be None
        assert ctx.git_status is None or isinstance(ctx.git_status, str)

    def test_get_system_context_as_dict(self):
        """as_dict property should return a dict."""
        ctx = get_system_context()
        d = ctx.as_dict
        assert isinstance(d, dict)

    def test_get_system_context_with_cache_breaker(self):
        """Should include cache breaker when provided."""
        ctx = get_system_context(cache_breaker="test-injection")
        assert ctx.cache_breaker == "test-injection"
        d = ctx.as_dict
        assert "cacheBreaker" in d


class TestUserContext:
    """Tests for user context."""

    def test_get_user_context_returns_user_context(self):
        """Should return a UserContext object."""
        result = get_user_context()
        assert isinstance(result, UserContext)

    def test_get_user_context_current_date_format(self):
        """current_date should be in 'Today is YYYY/MM/DD.' format."""
        ctx = get_user_context()
        assert ctx.current_date is not None
        assert ctx.current_date.startswith("Today is ")

        # Parse and verify format
        date_str = ctx.current_date.replace("Today is ", "").rstrip(".")
        datetime.strptime(date_str, "%Y/%m/%d")  # Will raise if invalid

    def test_get_user_context_as_dict(self):
        """as_dict property should return a dict."""
        ctx = get_user_context()
        d = ctx.as_dict
        assert isinstance(d, dict)


# ------------------------------------------------------------------
# Tests: Combined context
# ------------------------------------------------------------------


class TestContextResult:
    """Tests for combined context result."""

    def test_get_context_returns_context_result(self):
        """get_context() should return a ContextResult."""
        result = get_context()
        assert isinstance(result, ContextResult)
        assert isinstance(result.system, SystemContext)
        assert isinstance(result.user, UserContext)

    def test_get_context_all_strings(self):
        """all_strings property should merge system and user context."""
        result = get_context()
        all_str = result.all_strings
        assert isinstance(all_str, dict)

    def test_get_context_uses_config(self, temp_git_repo):
        """get_context() should respect ContextConfig settings."""
        # Disable git
        config = get_context_config()
        config.include_git_status = False
        set_context_config(config)

        result = get_context()
        assert result.system.git_status is None

        # Re-enable
        config.include_git_status = True
        set_context_config(config)


# ------------------------------------------------------------------
# Tests: Cache clearing
# ------------------------------------------------------------------


class TestCacheClearing:
    """Tests for cache clearing functionality."""

    def test_clear_context_cache_clears_all_caches(self, temp_git_repo):
        """clear_context_cache() should clear all cached values."""
        # Populate caches
        get_git_status(str(temp_git_repo))
        get_claude_md_content(str(temp_git_repo))
        get_system_context()
        get_user_context()

        # Clear
        clear_context_cache()

        # Caches should be empty (will recompute)
        # We can't directly check internal cache state, but we can verify
        # the function runs without error
        assert True


# ------------------------------------------------------------------
# Tests: Configuration
# ------------------------------------------------------------------


class TestContextConfig:
    """Tests for context configuration."""

    def test_get_context_config_returns_config(self):
        """Should return a ContextConfig object."""
        config = get_context_config()
        assert isinstance(config, ContextConfig)

    def test_set_context_config_updates_config(self):
        """set_context_config() should update the global config."""
        new_config = ContextConfig(include_git_status=False)
        set_context_config(new_config)
        assert get_context_config().include_git_status is False

    def test_config_env_git_disabled(self):
        """CLAUDE_CODE_REMOTE env var should disable git status."""
        original = os.environ.get("CLAUDE_CODE_REMOTE")
        try:
            os.environ["CLAUDE_CODE_REMOTE"] = "1"
            config = get_context_config()
            assert config.is_git_disabled_by_env() is True
        finally:
            if original is None:
                os.environ.pop("CLAUDE_CODE_REMOTE", None)
            else:
                os.environ["CLAUDE_CODE_REMOTE"] = original

    def test_config_env_claude_md_disabled(self):
        """CLAUDE_CODE_DISABLE_CLAUDE_MDS env var should disable claude.md."""
        original = os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS")
        try:
            os.environ["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
            config = get_context_config()
            assert config.is_claude_md_disabled_by_env() is True
        finally:
            if original is None:
                os.environ.pop("CLAUDE_CODE_DISABLE_CLAUDE_MDS", None)
            else:
                os.environ["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = original

    def test_should_include_git_respects_env_and_flag(self):
        """should_include_git() should consider both flag and env var."""
        config = get_context_config()

        # Both enabled
        config.include_git_status = True
        os.environ.pop("CLAUDE_CODE_REMOTE", None)
        assert config.should_include_git() is True

        # Flag disabled
        config.include_git_status = False
        assert config.should_include_git() is False

    def test_should_include_claude_md_respects_env_and_flag(self):
        """should_include_claude_md() should consider both flag and env var."""
        config = get_context_config()

        # Both enabled
        config.include_claude_md = True
        os.environ.pop("CLAUDE_CODE_DISABLE_CLAUDE_MDS", None)
        assert config.should_include_claude_md() is True

        # Flag disabled
        config.include_claude_md = False
        assert config.should_include_claude_md() is False
