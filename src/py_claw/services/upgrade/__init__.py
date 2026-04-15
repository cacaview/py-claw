"""
Upgrade service for upgrading Claude Code.

Based on ClaudeCode-main/src/services/upgrade/
"""
from py_claw.services.upgrade.service import (
    check_for_upgrades,
    get_current_version,
    get_upgrade_info,
    perform_upgrade,
)
from py_claw.services.upgrade.types import UpgradeInfo, UpgradeResult, UpgradeStatus


__all__ = [
    "get_current_version",
    "check_for_upgrades",
    "get_upgrade_info",
    "perform_upgrade",
    "UpgradeInfo",
    "UpgradeResult",
    "UpgradeStatus",
]
