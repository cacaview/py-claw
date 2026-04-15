"""
Types for version service.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VersionInfo:
    """Version information."""
    version: str
    build_date: str | None = None
    commit: str | None = None


@dataclass
class VersionResult:
    """Result of version query."""
    success: bool
    message: str
    version_info: VersionInfo | None = None
