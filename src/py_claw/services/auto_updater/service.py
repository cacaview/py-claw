"""
AutoUpdater service for automatic Claude Code updates.

Checks for updates from Google Cloud Storage and manages
the update lifecycle.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.request import urlopen
from urllib.error import URLError

from .config import (
    AutoUpdaterConfig,
    UpdateChannel,
    get_auto_updater_config,
    load_auto_updater_config,
)

logger = logging.getLogger(__name__)


class UpdateStatus(str, Enum):
    """Update status."""
    NONE = "none"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    INSTALLED = "installed"
    FAILED = "failed"


@dataclass
class UpdateAvailable:
    """Information about an available update."""
    version: str
    release_date: str
    download_url: str
    checksum: str | None
    size_bytes: int | None
    release_notes: str | None
    channel: UpdateChannel


@dataclass
class CheckResult:
    """Result of checking for updates."""
    status: UpdateStatus
    current_version: str
    update: UpdateAvailable | None = None
    error: str | None = None


# Global singleton
_service: "AutoUpdaterService | None" = None


def get_auto_updater_service() -> "AutoUpdaterService":
    """Get the global auto updater service instance."""
    global _service
    if _service is None:
        _service = AutoUpdaterService()
    return _service


class AutoUpdaterService:
    """
    AutoUpdater service for automatic Claude Code updates.

    Checks Google Cloud Storage for new versions and manages
    the update process.
    """

    def __init__(self) -> None:
        self._config = load_auto_updater_config()
        self._status = UpdateStatus.NONE
        self._current_version = self._get_current_version()
        self._last_check: datetime | None = None
        self._update: UpdateAvailable | None = None
        self._download_progress: float = 0.0

    def _get_current_version(self) -> str:
        """Get the current Claude Code version."""
        # Try to read from package
        try:
            from py_claw import __version__
            return __version__
        except ImportError:
            pass

        # Fallback to environment variable
        return os.environ.get("CLAUDE_CODE_VERSION", "unknown")

    @property
    def config(self) -> AutoUpdaterConfig:
        """Get current configuration."""
        return self._config

    @property
    def status(self) -> UpdateStatus:
        """Get current update status."""
        return self._status

    @property
    def current_version(self) -> str:
        """Get current version."""
        return self._current_version

    @property
    def update(self) -> UpdateAvailable | None:
        """Get available update if any."""
        return self._update

    def reload_config(self) -> None:
        """Reload configuration from disk."""
        self._config = load_auto_updater_config()

    async def check_for_updates(self, force: bool = False) -> CheckResult:
        """
        Check for available updates.

        Args:
            force: Force check even if recently checked

        Returns:
            CheckResult with update information
        """
        if not self._config.enabled and not force:
            return CheckResult(
                status=UpdateStatus.NONE,
                current_version=self._current_version,
                error="Auto updater is disabled",
            )

        # Rate limit checks
        if not force and self._last_check is not None:
            elapsed = time.time() - self._last_check.timestamp()
            if elapsed < self._config.check_interval_seconds:
                return CheckResult(
                    status=self._status,
                    current_version=self._current_version,
                    update=self._update,
                )

        try:
            update = await self._fetch_latest_version()
            self._update = update
            self._last_check = datetime.now()

            if update is not None:
                self._status = UpdateStatus.AVAILABLE
                return CheckResult(
                    status=UpdateStatus.AVAILABLE,
                    current_version=self._current_version,
                    update=update,
                )
            else:
                self._status = UpdateStatus.NONE
                return CheckResult(
                    status=UpdateStatus.NONE,
                    current_version=self._current_version,
                )

        except Exception as e:
            logger.warning(f"Failed to check for updates: {e}")
            return CheckResult(
                status=self._status,
                current_version=self._current_version,
                error=str(e),
            )

    async def _fetch_latest_version(self) -> UpdateAvailable | None:
        """Fetch the latest version info from GCS."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        # Map platform to release file suffix
        if system == "darwin":
            suffix = f"darwin-{machine}" if machine == "arm64" else "darwin-amd64"
        elif system == "linux":
            suffix = f"linux-{machine}"
        elif system == "windows":
            suffix = f"windows-{machine}"
        else:
            return None

        # Build GCS URL for version manifest
        channel_path = self._config.channel.value
        manifest_url = f"{self._config.base_url}/{channel_path}/latest/{suffix}/version.json"

        try:
            async with asyncio.timeout(10):
                loop = asyncio.get_event_loop()
                with urlopen(manifest_url, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))

                latest_version = data.get("version")
                if latest_version is None:
                    return None

                # Check if newer than current
                if not self._is_newer_version(latest_version, self._current_version):
                    return None

                # Check if we should skip this version
                if latest_version == self._config.skip_version:
                    return None

                return UpdateAvailable(
                    version=latest_version,
                    release_date=data.get("releaseDate", ""),
                    download_url=data.get("downloadUrl", ""),
                    checksum=data.get("checksum"),
                    size_bytes=data.get("sizeBytes"),
                    release_notes=data.get("releaseNotes"),
                    channel=self._config.channel,
                )

        except URLError as e:
            logger.debug(f"GCS URL not available: {manifest_url} - {e}")
            return None
        except Exception as e:
            logger.debug(f"Failed to fetch version: {e}")
            return None

    def _is_newer_version(self, new: str, current: str) -> bool:
        """Check if new version is newer than current."""
        if current == "unknown":
            return True

        try:
            # Simple version comparison (major.minor.patch)
            new_parts = [int(x) for x in new.split(".")[:3]]
            current_parts = [int(x) for x in current.split(".")[:3]]

            for n, c in zip(new_parts, current_parts):
                if n > c:
                    return True
                elif n < c:
                    return False
            return False  # Equal versions
        except (ValueError, AttributeError):
            return new != current

    async def download_update(self) -> bool:
        """
        Download the available update.

        Returns:
            True if download succeeded, False otherwise
        """
        if self._update is None:
            return False

        self._status = UpdateStatus.DOWNLOADING
        self._download_progress = 0.0

        try:
            download_url = self._update.download_url
            if not download_url:
                raise ValueError("No download URL available")

            # Get download path
            download_dir = self._get_download_dir()
            download_path = download_dir / f"claude-code-{self._update.version}"

            # Download file
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._download_file,
                download_url,
                download_path,
            )

            # Verify checksum
            if self._update.checksum:
                actual_checksum = self._compute_checksum(download_path)
                if actual_checksum != self._update.checksum:
                    raise ValueError(f"Checksum mismatch: expected {self._update.checksum}, got {actual_checksum}")

            self._status = UpdateStatus.DOWNLOADED
            self._download_progress = 1.0
            return True

        except Exception as e:
            logger.error(f"Failed to download update: {e}")
            self._status = UpdateStatus.FAILED
            return False

    def _download_file(self, url: str, dest: "os.PathLike") -> None:
        """Download a file from URL to destination."""
        import shutil

        with urlopen(url, timeout=60) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            with open(dest, "wb") as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        self._download_progress = downloaded / total_size

    def _compute_checksum(self, path: "os.PathLike") -> str:
        """Compute SHA256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def _get_download_dir(self) -> "os.PathLike":
        """Get the directory for downloaded updates."""
        download_dir = Path.home() / ".claude" / "updates"
        download_dir.mkdir(parents=True, exist_ok=True)
        return download_dir

    def get_status_info(self) -> dict[str, Any]:
        """Get detailed status information."""
        return {
            "enabled": self._config.enabled,
            "channel": self._config.channel.value,
            "status": self._status.value,
            "currentVersion": self._current_version,
            "update": {
                "version": self._update.version,
                "releaseDate": self._update.release_date,
                "downloadUrl": self._update.download_url,
                "sizeBytes": self._update.size_bytes,
            } if self._update else None,
            "lastCheck": self._last_check.isoformat() if self._last_check else None,
            "downloadProgress": self._download_progress,
        }
