"""
AutoUpdater configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# GCS bucket for Claude Code releases
DEFAULT_GCS_BUCKET = "claude-code-releases"
DEFAULT_CHECK_INTERVAL = 3600  # 1 hour


class UpdateChannel(str, Enum):
    """Update channel."""
    STABLE = "stable"
    LATEST = "latest"
    BETA = "beta"


@dataclass
class AutoUpdaterConfig:
    """Configuration for auto updater."""

    enabled: bool = False
    channel: UpdateChannel = UpdateChannel.STABLE
    check_interval_seconds: int = DEFAULT_CHECK_INTERVAL
    gcs_bucket: str = DEFAULT_GCS_BUCKET
    auto_download: bool = False
    auto_install: bool = False
    skip_version: str | None = None  # Version to skip (e.g., bad release)
    base_url: str = f"https://storage.googleapis.com/{DEFAULT_GCS_BUCKET}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "channel": self.channel.value,
            "checkIntervalSeconds": self.check_interval_seconds,
            "gcsBucket": self.gcs_bucket,
            "autoDownload": self.auto_download,
            "autoInstall": self.auto_install,
            "skipVersion": self.skip_version,
        }


def get_auto_updater_config_path() -> Path:
    """Get the path to the auto updater config file."""
    config_dir = Path.home() / ".claude"
    return config_dir / "auto_updater.json"


def load_auto_updater_config() -> AutoUpdaterConfig:
    """Load auto updater configuration from disk."""
    config_path = get_auto_updater_config_path()

    if not config_path.exists():
        return AutoUpdaterConfig()

    try:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return AutoUpdaterConfig(
            enabled=data.get("enabled", False),
            channel=UpdateChannel(data.get("channel", "stable")),
            check_interval_seconds=data.get("checkIntervalSeconds", DEFAULT_CHECK_INTERVAL),
            gcs_bucket=data.get("gcsBucket", DEFAULT_GCS_BUCKET),
            auto_download=data.get("autoDownload", False),
            auto_install=data.get("autoInstall", False),
            skip_version=data.get("skipVersion"),
        )
    except Exception:
        return AutoUpdaterConfig()


def save_auto_updater_config(config: AutoUpdaterConfig) -> None:
    """Save auto updater configuration to disk."""
    config_path = get_auto_updater_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    import json
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)


def get_auto_updater_config() -> AutoUpdaterConfig:
    """Get the current auto updater configuration."""
    return load_auto_updater_config()
