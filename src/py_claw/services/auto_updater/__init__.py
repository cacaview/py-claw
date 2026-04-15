"""
AutoUpdater service for automatic Claude Code updates.

Checks Google Cloud Storage for new versions and manages
the update process.
"""
from __future__ import annotations

from .service import (
    AutoUpdaterService,
    CheckResult,
    UpdateAvailable,
    UpdateStatus,
    get_auto_updater_service,
)
from .config import (
    AutoUpdaterConfig,
    UpdateChannel,
    get_auto_updater_config,
    load_auto_updater_config,
)

__all__ = [
    "AutoUpdaterService",
    "AutoUpdaterConfig",
    "UpdateChannel",
    "UpdateStatus",
    "UpdateAvailable",
    "CheckResult",
    "get_auto_updater_service",
    "get_auto_updater_config",
    "load_auto_updater_config",
]
