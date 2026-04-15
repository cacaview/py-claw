"""Cleanup utilities for old files and caches.

Based on ClaudeCode-main/src/utils/cleanup.ts

Provides cleanup functions for various cache directories and log files,
respecting the cleanupPeriodDays setting.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Protocol

    class FsOperations(Protocol):
        """Filesystem operations interface."""

        async def readdir(self, path: str) -> list[DirEntry]: ...
        async def unlink(self, path: str) -> None: ...
        async def rmdir(self, path: str) -> None: ...
        async def stat(self, path: str) -> StatResult: ...

    class DirEntry:
        name: str

        def is_file(self) -> bool: ...
        def is_directory(self) -> bool: ...

    class StatResult:
        mtime: datetime


DEFAULT_CLEANUP_PERIOD_DAYS = 30


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    messages: int = 0
    errors: int = 0


def get_cutoff_date(cleanup_period_days: int | None = None) -> datetime:
    """Get the cutoff date for cleanup operations.

    Args:
        cleanup_period_days: Override cleanup period. Defaults to 30 days.

    Returns:
        Datetime before which files should be deleted.
    """
    # In Python implementation, we would read from settings
    # For now, use the default
    period_days = cleanup_period_days or DEFAULT_CLEANUP_PERIOD_DAYS
    period_ms = period_days * 24 * 60 * 60 * 1000
    return datetime.now() - timedelta(milliseconds=period_ms)


def add_cleanup_results(a: CleanupResult, b: CleanupResult) -> CleanupResult:
    """Combine two cleanup results."""
    return CleanupResult(
        messages=a.messages + b.messages,
        errors=a.errors + b.errors,
    )


def convert_filename_to_date(filename: str) -> datetime:
    """Convert filename format to Date.

    Handles the format where all ':' were replaced with '-' and
    T separating date from time.
    """
    # Extract the datetime part from filename like 2024-01-15T10-30-00-000Z
    # Convert back to ISO format
    iso_str = filename.split(".")[0]
    # Replace hyphens in time portion back to colons
    # Pattern: YYYY-MM-DDTHH-MM-SS-fffZ
    iso_str = re.sub(r"T(\d{2})-(\d{2})-(\d{2})-(\d{3})Z", r"T\1:\2:\3.\4Z", iso_str)
    return datetime.fromisoformat(iso_str)


async def cleanup_old_files_in_directory(
    dir_path: str,
    cutoff_date: datetime,
    is_message_path: bool,
    fs_impl: FsOperations | None = None,
) -> CleanupResult:
    """Clean up old files in a single directory.

    Args:
        dir_path: Directory to clean
        cutoff_date: Files older than this are deleted
        is_message_path: If True, deleted files count as messages, else errors
        fs_impl: Filesystem implementation (defaults to os-based)
    """
    result = CleanupResult(messages=0, errors=0)

    if fs_impl is None:
        # Use default filesystem implementation
        fs_impl = _DefaultFsOperations()

    try:
        files = await fs_impl.readdir(dir_path)

        for file in files:
            try:
                timestamp = convert_filename_to_date(file.name)
                if timestamp < cutoff_date:
                    file_path = os.path.join(dir_path, file.name)
                    await fs_impl.unlink(file_path)
                    if is_message_path:
                        result.messages += 1
                    else:
                        result.errors += 1
            except Exception:
                result.errors += 1
    except FileNotFoundError:
        pass
    except Exception:
        pass

    return result


class _DefaultFsOperations:
    """Default filesystem operations using os module."""

    async def readdir(self, path: str) -> list[DirEntry]:
        """Read directory contents."""
        entries = os.listdir(path)
        result = []
        for name in entries:
            full_path = os.path.join(path, name)
            if os.path.isdir(full_path):
                result.append(_DirEntry(name, True, False))
            else:
                result.append(_DirEntry(name, False, True))
        return result

    async def unlink(self, path: str) -> None:
        """Delete a file."""
        os.unlink(path)

    async def rmdir(self, path: str) -> None:
        """Remove a directory."""
        try:
            os.rmdir(path)
        except OSError:
            pass  # not empty or doesn't exist

    async def stat(self, path: str) -> StatResult:
        """Get file stats."""
        stat_info = os.stat(path)
        return _StatResult(datetime.fromtimestamp(stat_info.st_mtime))


class _DirEntry:
    """Directory entry wrapper."""

    def __init__(self, name: str, is_dir: bool, is_file: bool):
        self.name = name
        self._is_dir = is_dir
        self._is_file = is_file

    def is_file(self) -> bool:
        return self._is_file

    def is_directory(self) -> bool:
        return self._is_dir


class _StatResult:
    """Stat result wrapper."""

    def __init__(self, mtime: datetime):
        self.mtime = mtime


async def cleanup_old_message_files() -> CleanupResult:
    """Clean up old message and error log files."""
    # Placeholder - would need cache paths
    return CleanupResult(messages=0, errors=0)


async def cleanup_old_session_files() -> CleanupResult:
    """Clean up old session files including tool-results."""
    # Placeholder - would need projects directory
    return CleanupResult(messages=0, errors=0)


async def cleanup_old_plan_files() -> CleanupResult:
    """Clean up old plan files from ~/.claude/plans."""
    # Placeholder - would need config directory
    return CleanupResult(messages=0, errors=0)


async def cleanup_old_file_history_backups() -> CleanupResult:
    """Clean up old file history backup directories."""
    # Placeholder
    return CleanupResult(messages=0, errors=0)


async def cleanup_old_session_env_dirs() -> CleanupResult:
    """Clean up old session environment directories."""
    # Placeholder
    return CleanupResult(messages=0, errors=0)


async def cleanup_old_debug_logs() -> CleanupResult:
    """Clean up old debug log files from ~/.claude/debug/.

    Preserves the 'latest' symlink which points to the current session's log.
    """
    # Placeholder
    return CleanupResult(messages=0, errors=0)


async def cleanup_old_versions_throttled() -> None:
    """Throttled wrapper around cleanupOldVersions.

    Runs at most once per 24 hours using a marker file.
    """
    # Placeholder - would need config directory
    pass
