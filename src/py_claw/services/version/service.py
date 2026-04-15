"""
Version service for displaying version information.
"""
from __future__ import annotations

import logging
import platform

from .types import VersionInfo, VersionResult

logger = logging.getLogger(__name__)


def get_version_info() -> VersionInfo:
    """Get version information.

    Returns:
        VersionInfo with version details
    """
    try:
        from py_claw import __version__
        version = __version__
    except ImportError:
        version = "unknown"

    return VersionInfo(
        version=version,
        build_date=None,
        commit=None,
    )


def get_version_string() -> str:
    """Get a formatted version string.

    Returns:
        Formatted version string
    """
    info = get_version_info()
    lines = [
        f"py-claw version {info.version}",
        f"Python: {platform.python_version()}",
        f"Platform: {platform.system()} {platform.release()}",
    ]
    if info.build_date:
        lines.append(f"Build date: {info.build_date}")
    if info.commit:
        lines.append(f"Commit: {info.commit}")
    return "\n".join(lines)


def get_full_version_info() -> VersionResult:
    """Get full version information result.

    Returns:
        VersionResult with all version details
    """
    try:
        info = get_version_info()
        return VersionResult(
            success=True,
            message=get_version_string(),
            version_info=info,
        )
    except Exception as e:
        return VersionResult(
            success=False,
            message=f"Error getting version info: {e}",
        )
