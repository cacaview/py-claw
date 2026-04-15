"""
Remote Managed Settings Service.

Fetches, caches, and validates remote-managed settings for enterprise customers.
Uses checksum-based validation to minimize network traffic and provides
graceful degradation on failures.

Eligibility:
- Console users (API key): All eligible
- OAuth users: Only Enterprise/C4E and Team subscribers are eligible
- API fails open (non-blocking) - if fetch fails, continues without remote settings
- API returns empty settings for users without managed settings
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any

from .state import (
    RemoteSettingsState,
    get_remote_settings_state,
    reset_remote_settings_state,
    load_settings_from_disk,
    save_settings_to_disk,
    clear_disk_cache,
)
from .types import (
    RemoteSettingsConfig,
    RemoteSettingsFetchResult,
)


# Default API endpoint for remote settings
DEFAULT_API_URL = "https://settings.claude.ai/api/v1/managed-settings"


class RemoteSettingsService:
    """
    Service for fetching and managing remote managed settings.

    Enterprise customers can have settings managed by their organization.
    This service fetches those settings, caches them with checksum validation,
    and applies them to the local settings layer.
    """

    def __init__(self) -> None:
        self._state = get_remote_settings_state()
        self._config = RemoteSettingsConfig()
        self._initialized = False
        self._polling_interval_id: threading.Timer | None = None
        self._loading_promise: threading.Event | None = None
        self._lock = threading.RLock()

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(
        self,
        config: RemoteSettingsConfig | None = None,
        load_cached: bool = True,
    ) -> None:
        """
        Initialize the remote settings service.

        Args:
            config: Service configuration
            load_cached: Whether to load cached settings from disk
        """
        with self._lock:
            if self._initialized:
                return

            if config is not None:
                self._config = config

            # Check eligibility
            if self._config.enabled:
                self._check_eligibility()

            # Load from disk cache if available
            if load_cached and self._state.get_eligibility():
                self._load_from_disk()

            self._initialized = True

    def _check_eligibility(self) -> None:
        """
        Check if the current user is eligible for remote managed settings.

        Eligibility:
        - Must be using first-party Anthropic API
        - Must not be using custom base URL
        - Must not be in local-agent mode
        """
        # Check for API provider
        api_url = os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("CLAUDE_API_URL")
        if api_url and not api_url.startswith("https://api.anthropic.com"):
            self._state.set_eligibility(False)
            return

        # Check for local-agent mode
        entrypoint = os.environ.get("CLAUDE_CODE_ENTRYPOINT")
        if entrypoint == "local-agent":
            self._state.set_eligibility(False)
            return

        # Check for API key or OAuth token
        has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        has_oauth = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))

        if not has_api_key and not has_oauth:
            self._state.set_eligibility(False)
            return

        # Eligible
        self._state.set_eligibility(True)

    def _load_from_disk(self) -> None:
        """Load settings from disk cache."""
        settings, checksum = load_settings_from_disk()
        if settings is not None:
            self._state.set_cached_settings(settings, checksum)

    def is_eligible(self) -> bool:
        """Check if the user is eligible for remote managed settings."""
        return self._state.get_eligibility() is True

    def get_settings(self) -> dict[str, Any] | None:
        """
        Get cached remote settings.

        Returns:
            Cached settings dict or None if not loaded
        """
        return self._state.get_cached_settings()

    def get_checksum(self) -> str | None:
        """Get the cached settings checksum."""
        return self._state.get_cached_checksum()

    async def fetch_remote_settings(
        self,
        current_checksum: str | None = None,
    ) -> RemoteSettingsFetchResult:
        """
        Fetch remote settings from the API.

        Args:
            current_checksum: Current checksum to send for 304 Not Modified detection

        Returns:
            RemoteSettingsFetchResult with settings or error
        """
        if not self.is_eligible():
            return RemoteSettingsFetchResult(
                success=False,
                error="Not eligible for remote managed settings",
                skip_retry=True,
            )

        api_url = self._config.api_url or DEFAULT_API_URL
        timeout = self._config.timeout_ms / 1000

        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        # Add auth header
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key

        oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if oauth_token:
            headers["Authorization"] = f"Bearer {oauth_token}"

        # Add current checksum for 304 detection
        if current_checksum:
            headers["If-None-Match"] = current_checksum

        try:
            import urllib.request

            req = urllib.request.Request(
                api_url,
                method="GET",
                headers=headers,
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 304:
                    # Not modified, cache is still valid
                    return RemoteSettingsFetchResult(
                        success=True,
                        settings=None,  # None means 304
                        skip_retry=True,
                    )

                data = json.loads(response.read().decode("utf-8"))

                # Validate response
                if not isinstance(data, dict):
                    return RemoteSettingsFetchResult(
                        success=False,
                        error="Invalid response format",
                    )

                settings = data.get("settings", {})
                checksum = data.get("checksum", "")

                if not checksum:
                    return RemoteSettingsFetchResult(
                        success=False,
                        error="Missing checksum in response",
                    )

                # Validate checksum
                computed = self._compute_checksum(settings)
                if computed != checksum:
                    return RemoteSettingsFetchResult(
                        success=False,
                        error="Checksum mismatch",
                        skip_retry=True,
                    )

                # Cache the settings
                self._state.set_cached_settings(settings, checksum)
                save_settings_to_disk(settings, checksum)

                return RemoteSettingsFetchResult(
                    success=True,
                    settings=settings,
                    checksum=checksum,
                )

        except urllib.error.HTTPError as e:
            if e.code == 304:
                return RemoteSettingsFetchResult(
                    success=True,
                    settings=None,
                    skip_retry=True,
                )
            if e.code in (401, 403):
                return RemoteSettingsFetchResult(
                    success=False,
                    error=f"Authentication error: {e.code}",
                    skip_retry=True,
                )
            return RemoteSettingsFetchResult(
                success=False,
                error=f"HTTP error: {e.code}",
            )
        except Exception as e:
            return RemoteSettingsFetchResult(
                success=False,
                error=str(e),
            )

    def _compute_checksum(self, settings: dict[str, Any]) -> str:
        """Compute SHA-256 checksum of settings."""
        settings_json = json.dumps(settings, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(settings_json.encode()).hexdigest()

    def start_polling(self) -> None:
        """Start background polling for settings updates."""
        if self._polling_interval_id is not None:
            return

        def poll() -> None:
            current_checksum = self.get_checksum()
            # Run sync fetch in background
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.fetch_remote_settings(current_checksum))
                loop.close()
            except Exception:
                pass

            # Schedule next poll
            interval = self._config.polling_interval_ms / 1000
            self._polling_interval_id = threading.Timer(interval, poll)
            self._polling_interval_id.daemon = True
            self._polling_interval_id.start()

        # Start first poll after initial interval
        interval = self._config.polling_interval_ms / 1000
        self._polling_interval_id = threading.Timer(interval, poll)
        self._polling_interval_id.daemon = True
        self._polling_interval_id.start()

    def stop_polling(self) -> None:
        """Stop background polling."""
        if self._polling_interval_id is not None:
            self._polling_interval_id.cancel()
            self._polling_interval_id = None

    def clear_cache(self) -> None:
        """Clear cached settings."""
        self._state.set_cached_settings(None, None)
        clear_disk_cache()

    def get_config(self) -> RemoteSettingsConfig:
        """Get current configuration."""
        return self._config

    def update_config(self, config: RemoteSettingsConfig) -> None:
        """Update configuration."""
        self._config = config


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_service: RemoteSettingsService | None = None


def get_remote_settings_service() -> RemoteSettingsService:
    """Get the global remote settings service."""
    global _service
    if _service is None:
        _service = RemoteSettingsService()
    return _service


def reset_remote_settings_service() -> None:
    """Reset the global remote settings service (for testing)."""
    global _service
    if _service is not None:
        _service.stop_polling()
    _service = None
    reset_remote_settings_state()
