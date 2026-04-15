"""
Types for upgrade service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UpgradeStatus(str, Enum):
    """Upgrade status."""
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class UpgradeInfo:
    """Upgrade information."""
    current_version: str
    latest_version: str | None = None
    release_notes: str | None = None
    download_url: str | None = None


@dataclass
class UpgradeResult:
    """Result of upgrade operation."""
    success: bool
    status: UpgradeStatus
    message: str
    info: UpgradeInfo | None = None
