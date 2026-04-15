"""
Tests for the remote settings service.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from py_claw.services.remote_settings import (
    RemoteSettingsService,
    RemoteSettingsState,
    RemoteSettingsConfig,
    RemoteSettingsFetchResult,
    get_remote_settings_service,
    get_remote_settings_state,
    reset_remote_settings_service,
    reset_remote_settings_state,
    load_settings_from_disk,
    save_settings_to_disk,
    clear_disk_cache,
)


class TestRemoteSettingsState:
    """Tests for RemoteSettingsState."""

    def setup_method(self) -> None:
        reset_remote_settings_state()

    def teardown_method(self) -> None:
        reset_remote_settings_state()

    def test_singleton(self) -> None:
        state1 = get_remote_settings_state()
        state2 = get_remote_settings_state()
        assert state1 is state2

    def test_set_and_get_cached_settings(self) -> None:
        state = get_remote_settings_state()
        settings = {"key": "value"}
        state.set_cached_settings(settings, "abc123")
        assert state.get_cached_settings() == settings
        assert state.get_cached_checksum() == "abc123"

    def test_eligibility(self) -> None:
        state = get_remote_settings_state()
        assert state.get_eligibility() is None
        state.set_eligibility(True)
        assert state.get_eligibility() is True
        state.set_eligibility(False)
        assert state.get_eligibility() is False

    def test_clear(self) -> None:
        state = get_remote_settings_state()
        state.set_cached_settings({"key": "value"}, "checksum")
        state.set_eligibility(True)
        state.clear()
        assert state.get_cached_settings() is None
        assert state.get_cached_checksum() is None
        assert state.get_eligibility() is None


class TestRemoteSettingsService:
    """Tests for RemoteSettingsService."""

    def setup_method(self) -> None:
        reset_remote_settings_service()
        reset_remote_settings_state()  # Also reset state singleton

    def teardown_method(self) -> None:
        reset_remote_settings_service()
        reset_remote_settings_state()

    def test_singleton(self) -> None:
        svc1 = get_remote_settings_service()
        svc2 = get_remote_settings_service()
        assert svc1 is svc2

    def test_initialize(self) -> None:
        svc = get_remote_settings_service()
        svc.initialize()
        assert svc.initialized

    def test_initialize_idempotent(self) -> None:
        svc = get_remote_settings_service()
        svc.initialize()
        svc.initialize()
        assert svc.initialized

    def test_not_eligible_without_api_key(self) -> None:
        # Ensure no API key in environment
        reset_remote_settings_service()
        reset_remote_settings_state()

        # Also clear base URL to ensure clean state
        orig_base_url = os.environ.pop("ANTHROPIC_BASE_URL", None)
        orig_api_url = os.environ.pop("CLAUDE_API_URL", None)
        orig_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        orig_oauth = os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        try:
            svc = get_remote_settings_service()
            svc.initialize()
            assert svc.is_eligible() is False
        finally:
            if orig_key:
                os.environ["ANTHROPIC_API_KEY"] = orig_key
            if orig_oauth:
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = orig_oauth
            if orig_base_url:
                os.environ["ANTHROPIC_BASE_URL"] = orig_base_url
            if orig_api_url:
                os.environ["CLAUDE_API_URL"] = orig_api_url

    def test_eligible_with_api_key(self) -> None:
        # Ensure clean state by creating a fresh service
        reset_remote_settings_service()
        reset_remote_settings_state()

        # Must clear custom base URL for eligibility
        orig_base_url = os.environ.pop("ANTHROPIC_BASE_URL", None)
        orig_api_url = os.environ.pop("CLAUDE_API_URL", None)
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        try:
            svc = get_remote_settings_service()
            svc.initialize()
            assert svc.is_eligible() is True
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            if orig_base_url:
                os.environ["ANTHROPIC_BASE_URL"] = orig_base_url
            if orig_api_url:
                os.environ["CLAUDE_API_URL"] = orig_api_url

    def test_not_eligible_with_custom_base_url(self) -> None:
        reset_remote_settings_service()
        reset_remote_settings_state()

        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_BASE_URL"] = "https://custom.example.com"
        try:
            svc = get_remote_settings_service()
            svc.initialize()
            assert svc.is_eligible() is False
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            del os.environ["ANTHROPIC_BASE_URL"]

    def test_not_eligible_in_local_agent_mode(self) -> None:
        reset_remote_settings_service()
        reset_remote_settings_state()

        orig_base_url = os.environ.pop("ANTHROPIC_BASE_URL", None)
        orig_api_url = os.environ.pop("CLAUDE_API_URL", None)
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["CLAUDE_CODE_ENTRYPOINT"] = "local-agent"
        try:
            svc = get_remote_settings_service()
            svc.initialize()
            assert svc.is_eligible() is False
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
            del os.environ["CLAUDE_CODE_ENTRYPOINT"]
            if orig_base_url:
                os.environ["ANTHROPIC_BASE_URL"] = orig_base_url
            if orig_api_url:
                os.environ["CLAUDE_API_URL"] = orig_api_url

    def test_get_settings_returns_none_when_not_loaded(self) -> None:
        svc = get_remote_settings_service()
        svc.initialize()
        assert svc.get_settings() is None

    def test_get_settings_returns_cached(self) -> None:
        svc = get_remote_settings_service()
        svc.initialize()
        svc._state.set_cached_settings({"key": "value"}, "checksum")
        assert svc.get_settings() == {"key": "value"}

    def test_checksum_computation(self) -> None:
        svc = get_remote_settings_service()
        settings = {"b": 2, "a": 1}
        checksum = svc._compute_checksum(settings)
        assert len(checksum) == 64  # SHA-256 hex length
        # Same settings should produce same checksum
        assert svc._compute_checksum(settings) == checksum
        # Different settings should produce different checksum
        assert svc._compute_checksum({"c": 3}) != checksum

    def test_clear_cache(self) -> None:
        svc = get_remote_settings_service()
        svc.initialize()
        svc._state.set_cached_settings({"key": "value"}, "checksum")
        svc.clear_cache()
        assert svc.get_settings() is None
        assert svc.get_checksum() is None

    def test_get_config(self) -> None:
        svc = get_remote_settings_service()
        svc.initialize()
        config = svc.get_config()
        assert isinstance(config, RemoteSettingsConfig)
        assert config.enabled is True


class TestDiskCache:
    """Tests for disk cache functions."""

    def test_save_and_load_settings(self, tmp_path: Path) -> None:
        from py_claw.services.remote_settings.state import get_cache_file_path

        original = str(get_cache_file_path())
        cache_file = tmp_path / "remote-settings.json"

        import py_claw.services.remote_settings.state as state_module
        original_cache = state_module.get_cache_file_path()

        # Monkey-patch temporarily
        state_module.get_cache_file_path = lambda: cache_file

        try:
            settings = {"org": "acme", "policy": {"max_tokens": 10000}}
            checksum = "abc123def456"
            save_settings_to_disk(settings, checksum)
            loaded_settings, loaded_checksum = load_settings_from_disk()
            assert loaded_settings == settings
            assert loaded_checksum == checksum
        finally:
            state_module.get_cache_file_path = lambda: Path(original)

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        import py_claw.services.remote_settings.state as state_module
        original = str(state_module.get_cache_file_path())
        cache_file = tmp_path / "nonexistent.json"
        state_module.get_cache_file_path = lambda: cache_file

        try:
            settings, checksum = load_settings_from_disk()
            assert settings is None
            assert checksum is None
        finally:
            state_module.get_cache_file_path = lambda: Path(original)


class TestRemoteSettingsConfig:
    """Tests for RemoteSettingsConfig."""

    def test_defaults(self) -> None:
        config = RemoteSettingsConfig()
        assert config.enabled is True
        assert config.api_url is None
        assert config.timeout_ms == 10000
        assert config.max_retries == 5
        assert config.polling_interval_ms == 60 * 60 * 1000

    def test_custom_config(self) -> None:
        config = RemoteSettingsConfig(
            enabled=False,
            api_url="https://custom.example.com/settings",
            timeout_ms=5000,
        )
        assert config.enabled is False
        assert config.api_url == "https://custom.example.com/settings"
        assert config.timeout_ms == 5000


class TestRemoteSettingsFetchResult:
    """Tests for RemoteSettingsFetchResult."""

    def test_success_with_settings(self) -> None:
        result = RemoteSettingsFetchResult(
            success=True,
            settings={"key": "value"},
            checksum="abc123",
        )
        assert result.success is True
        assert result.settings == {"key": "value"}
        assert result.checksum == "abc123"
        assert result.error is None
        assert result.skip_retry is False

    def test_not_modified(self) -> None:
        result = RemoteSettingsFetchResult(
            success=True,
            settings=None,
            skip_retry=True,
        )
        assert result.success is True
        assert result.settings is None
        assert result.skip_retry is True

    def test_error(self) -> None:
        result = RemoteSettingsFetchResult(
            success=False,
            error="HTTP 401",
            skip_retry=True,
        )
        assert result.success is False
        assert result.error == "HTTP 401"
        assert result.skip_retry is True
