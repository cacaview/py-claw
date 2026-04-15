"""Tests for the config service."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from py_claw.services.config import (
    GlobalConfig,
    ProjectConfig,
    get_global_config,
    save_global_config,
    get_current_project_config,
    save_current_project_config,
    get_project_path_for_config,
    get_theme,
    set_theme,
    is_auto_compact_enabled,
    increment_startup_count,
    get_or_create_user_id,
)
from py_claw.services.config.service import (
    _get_claude_config_dir,
    _get_global_config_path,
    _get_backup_dir,
    _filter_defaults,
    _merge_config,
    _normalize_path_for_config_key,
    _global_config_cache,
)


class TestGlobalConfig:
    """Tests for GlobalConfig model."""

    def test_default_values(self):
        """Test that GlobalConfig has correct defaults."""
        config = GlobalConfig()
        assert config.theme == "dark"
        assert config.verbose is False
        assert config.auto_compact_enabled is True
        assert config.num_startups == 0
        assert config.env == {}

    def test_extra_fields_allowed(self):
        """Test that extra fields are allowed."""
        config = GlobalConfig(**{"custom_field": "value", "theme": "light"})
        assert config.theme == "light"
        assert config.custom_field == "value"

    def test_nested_dict_defaults(self):
        """Test nested dict defaults are properly initialized."""
        config = GlobalConfig()
        assert config.tips_history == {}
        assert config.cached_statsig_gates == {}
        assert config.github_repo_paths == {}


class TestProjectConfig:
    """Tests for ProjectConfig model."""

    def test_default_values(self):
        """Test that ProjectConfig has correct defaults."""
        config = ProjectConfig()
        assert config.allowed_tools == []
        assert config.mcp_context_uris == []
        assert config.mcp_servers == {}
        assert config.has_trust_dialog_accepted is False

    def test_with_values(self):
        """Test ProjectConfig with values."""
        config = ProjectConfig(
            allowed_tools=["Read", "Edit"],
            mcp_context_uris=["http://localhost:3000"],
            has_trust_dialog_accepted=True,
        )
        assert config.allowed_tools == ["Read", "Edit"]
        assert config.mcp_context_uris == ["http://localhost:3000"]
        assert config.has_trust_dialog_accepted is True


class TestMergeConfig:
    """Tests for config merging."""

    def test_simple_merge(self):
        """Test simple value override."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _merge_config(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """Test nested dict merge."""
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 3, "z": 4}}
        result = _merge_config(base, override)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_list_override(self):
        """Test that lists are overridden, not merged."""
        base = {"a": [1, 2, 3]}
        override = {"a": [4, 5]}
        result = _merge_config(base, override)
        assert result == {"a": [4, 5]}


class TestFilterDefaults:
    """Tests for default filtering."""

    def test_filters_matching_defaults(self):
        """Test that values matching defaults are filtered out."""
        defaults = {"a": 1, "b": 2, "c": {"d": 3}}
        config = {"a": 1, "b": 20, "c": {"d": 3, "e": 4}}
        result = _filter_defaults(config, defaults)
        assert result == {"b": 20, "c": {"e": 4}}

    def test_preserves_non_defaults(self):
        """Test that non-default values are preserved."""
        defaults = {"a": 1}
        config = {"a": 2}
        result = _filter_defaults(config, defaults)
        assert result == {"a": 2}

    def test_empty_result(self):
        """Test that empty dict is returned when all values match defaults."""
        defaults = {"a": 1, "b": 2}
        config = {"a": 1, "b": 2}
        result = _filter_defaults(config, defaults)
        assert result == {}


class TestNormalizePath:
    """Tests for path normalization."""

    def test_forward_slashes(self):
        """Test that backslashes are converted to forward slashes."""
        path = "C:\\Users\\test\\project"
        result = _normalize_path_for_config_key(path)
        assert "\\" not in result
        assert "/" in result

    def test_resolves_relative(self):
        """Test that relative paths are resolved."""
        path = "src/../config"
        result = _normalize_path_for_config_key(path)
        # Path should be absolute after resolution
        assert Path(result).is_absolute()


class TestGetProjectPath:
    """Tests for project path detection."""

    def test_uses_git_root(self, tmp_path):
        """Test that git root is used when available."""
        git_root = tmp_path / "project"
        git_root.mkdir()
        (git_root / ".git").mkdir()

        # Create a subdirectory
        subdir = git_root / "src" / "module"
        subdir.mkdir(parents=True)

        result = get_project_path_for_config(str(subdir))
        assert result == _normalize_path_for_config_key(str(git_root))

    def test_uses_cwd_without_git(self, tmp_path):
        """Test that cwd is used when no git repo."""
        result = get_project_path_for_config(str(tmp_path))
        assert result == _normalize_path_for_config_key(str(tmp_path))


class TestTheme:
    """Tests for theme getter/setter."""

    def test_get_theme_default(self):
        """Test get_theme returns default."""
        # Theme is stored in config file, so just test the function exists
        theme = get_theme()
        assert isinstance(theme, str)
        assert theme in ("dark", "light", "system")

    def test_set_theme(self):
        """Test set_theme updates config."""
        original = get_theme()
        try:
            set_theme("light")
            assert get_theme() == "light"
        finally:
            set_theme(original)


class TestAutoCompact:
    """Tests for auto compact check."""

    def test_is_auto_compact_enabled(self):
        """Test auto compact check returns bool."""
        result = is_auto_compact_enabled()
        assert isinstance(result, bool)


class TestStartupCount:
    """Tests for startup counting."""

    def test_increment_startup_count(self):
        """Test incrementing startup count."""
        before = get_global_config().num_startups
        increment_startup_count()
        after = get_global_config().num_startups
        assert after == before + 1


class TestUserId:
    """Tests for user ID generation."""

    def test_get_or_create_user_id(self):
        """Test user ID is created if not exists."""
        config = get_global_config()
        original_id = config.user_id

        user_id = get_or_create_user_id()
        assert user_id is not None
        assert len(user_id) == 64  # 32 bytes hex = 64 chars

        # Should be same on subsequent calls
        assert get_or_create_user_id() == user_id


class TestConfigCacheInvalidation:
    """Tests for cache behavior."""

    def test_cache_returns_same_object(self):
        """Test that get_global_config returns cached object."""
        global _global_config_cache
        _global_config_cache = None  # Reset cache

        config1 = get_global_config()
        config2 = get_global_config()
        assert config1 is config2

        # Verify it's the same Python object
        assert config1 is config2


class TestBackupFunctions:
    """Tests for backup-related functions."""

    def test_get_backup_dir(self):
        """Test backup dir path."""
        backup_dir = _get_backup_dir()
        assert backup_dir.name == "backups"
        assert backup_dir.parent.name == ".claude"

    def test_get_global_config_path(self):
        """Test global config path."""
        config_path = _get_global_config_path()
        assert config_path.name == "settings.json"
        assert config_path.parent.name == ".claude"
