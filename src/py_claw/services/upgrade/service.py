"""
Upgrade service for upgrading Claude Code.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .types import UpgradeInfo, UpgradeResult, UpgradeStatus

logger = logging.getLogger(__name__)


def get_current_version() -> str:
    """Get the current Claude Code version.

    Returns:
        Current version string
    """
    try:
        from py_claw import __version__
        return __version__
    except ImportError:
        return "unknown"


def check_for_upgrades() -> UpgradeResult:
    """Check for available upgrades.

    Returns:
        UpgradeResult with upgrade information
    """
    try:
        current = get_current_version()

        # Try to check via pip if installed via pip
        try:
            result = subprocess.run(
                ["pip", "index", "versions", "py-claw"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                # Parse output to find latest version
                output = result.stdout
                # Extract version from output
                if "Available versions:" in output:
                    versions_section = output.split("Available versions:")[1].split("\n")[0]
                    latest = versions_section.strip().split(",")[-1].strip()
                    if latest:
                        return UpgradeResult(
                            success=True,
                            status=UpgradeStatus.AVAILABLE if latest != current else UpgradeStatus.IDLE,
                            message=f"Latest version: {latest}",
                            info=UpgradeInfo(
                                current_version=current,
                                latest_version=latest,
                            ),
                        )
        except FileNotFoundError:
            pass

        # For now, just return current version info
        return UpgradeResult(
            success=True,
            status=UpgradeStatus.IDLE,
            message=f"Current version: {current}",
            info=UpgradeInfo(
                current_version=current,
                latest_version=current,
            ),
        )

    except Exception as e:
        logger.exception("Error checking for upgrades")
        return UpgradeResult(
            success=False,
            status=UpgradeStatus.FAILED,
            message=f"Error checking for upgrades: {e}",
        )


async def perform_upgrade() -> UpgradeResult:
    """Perform the upgrade.

    Returns:
        UpgradeResult with upgrade status
    """
    try:
        current = get_current_version()

        # Try pip install --upgrade
        try:
            result = subprocess.run(
                ["pip", "install", "--upgrade", "py-claw"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                new_version = get_current_version()
                if new_version != current:
                    return UpgradeResult(
                        success=True,
                        status=UpgradeStatus.COMPLETED,
                        message=f"Upgraded from {current} to {new_version}",
                        info=UpgradeInfo(
                            current_version=new_version,
                            latest_version=new_version,
                        ),
                    )
                else:
                    return UpgradeResult(
                        success=True,
                        status=UpgradeStatus.IDLE,
                        message="Already at latest version",
                        info=UpgradeInfo(
                            current_version=current,
                            latest_version=current,
                        ),
                    )
            else:
                return UpgradeResult(
                    success=False,
                    status=UpgradeStatus.FAILED,
                    message=f"Upgrade failed: {result.stderr}",
                    info=UpgradeInfo(current_version=current),
                )

        except FileNotFoundError:
            return UpgradeResult(
                success=False,
                status=UpgradeStatus.FAILED,
                message="pip not found. Please install py-claw manually.",
                info=UpgradeInfo(current_version=current),
            )

    except Exception as e:
        logger.exception("Error performing upgrade")
        return UpgradeResult(
            success=False,
            status=UpgradeStatus.FAILED,
            message=f"Error performing upgrade: {e}",
        )


def get_upgrade_info() -> UpgradeResult:
    """Get upgrade information.

    Returns:
        UpgradeResult with upgrade information
    """
    return check_for_upgrades()
