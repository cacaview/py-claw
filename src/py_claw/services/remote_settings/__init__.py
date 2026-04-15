"""
Remote Managed Settings Service.

Enterprise remote policy configuration with checksum-based validation.

Provides:
- Eligibility checking (API key vs OAuth, custom base URL detection)
- Remote settings fetching with checksum validation
- Disk cache with SHA-256 checksum verification
- Background polling for settings updates
- Graceful degradation (fails open if API unavailable)

Basic usage:

    from py_claw.services.remote_settings import get_remote_settings_service

    service = get_remote_settings_service()
    service.initialize()

    if service.is_eligible():
        settings = service.get_settings()
        if settings:
            # Apply settings
            ...
"""
from __future__ import annotations

from .types import (
    RemoteSettingsResponse,
    RemoteSettingsFetchResult,
    RemoteSettingsEligibility,
    RemoteSettingsConfig,
)
from .state import (
    RemoteSettingsState,
    get_remote_settings_state,
    reset_remote_settings_state,
    load_settings_from_disk,
    save_settings_to_disk,
    clear_disk_cache,
)
from .service import (
    RemoteSettingsService,
    get_remote_settings_service,
    reset_remote_settings_service,
)

__all__ = [
    # Types
    "RemoteSettingsResponse",
    "RemoteSettingsFetchResult",
    "RemoteSettingsEligibility",
    "RemoteSettingsConfig",
    # State
    "RemoteSettingsState",
    "get_remote_settings_state",
    "reset_remote_settings_state",
    "load_settings_from_disk",
    "save_settings_to_disk",
    "clear_disk_cache",
    # Service
    "RemoteSettingsService",
    "get_remote_settings_service",
    "reset_remote_settings_service",
]
