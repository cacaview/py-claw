"""Native installer utilities - install, cleanup, and version management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .installer import (
    check_install,
    install_latest,
    cleanup_old_versions,
    cleanup_npm_installations,
    cleanup_shell_aliases,
    lock_current_version,
    remove_installed_symlink,
    SetupMessage,
)

__all__ = [
    "check_install",
    "install_latest",
    "cleanup_old_versions",
    "cleanup_npm_installations",
    "cleanup_shell_aliases",
    "lock_current_version",
    "remove_installed_symlink",
    "SetupMessage",
]
