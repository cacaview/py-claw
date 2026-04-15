"""
Remote Managed Settings types.

Enterprise remote policy configuration with checksum-based validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RemoteSettingsResponse:
    """
    Response from remote settings API.
    """
    uuid: str
    checksum: str
    settings: dict[str, Any]


@dataclass
class RemoteSettingsFetchResult:
    """
    Result of fetching remote managed settings.
    """
    success: bool
    settings: dict[str, Any] | None = None  # None means 304 Not Modified
    checksum: str | None = None
    error: str | None = None
    skip_retry: bool = False  # If True, don't retry (e.g., auth errors)


@dataclass
class RemoteSettingsEligibility:
    """
    Eligibility state for remote managed settings.
    """
    is_eligible: bool = False
    reason: str | None = None


@dataclass
class RemoteSettingsConfig:
    """
    Configuration for remote managed settings.
    """
    enabled: bool = True
    api_url: str | None = None
    timeout_ms: int = 10000
    max_retries: int = 5
    polling_interval_ms: int = 60 * 60 * 1000  # 1 hour
    cache_file: str = "~/.claude/remote-settings.json"
