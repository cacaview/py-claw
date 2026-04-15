"""
Cleanup utilities for removing old files and caches.

Provides cleanup for:
- Old message and error logs
- Old session files and tool results
- Old MCP logs
- Old plan files
- Old debug logs
- File history backups
- npm cache entries
- Old version directories
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------

@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    messages: int = 0  # Number of files/items removed
    errors: int = 0  # Number of errors encountered


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

DEFAULT_CLEANUP_PERIOD_DAYS = 30


def get_cleanup_period_days() -> int:
    """
    Get the cleanup period in days from settings.
    Returns default if not configured.
    """
    # Would normally load from settings - placeholder for now
    return DEFAULT_CLEANUP_PERIOD_DAYS


def get_cutoff_date() -> datetime:
    """Get the cutoff date for cleanup operations."""
    cleanup_period_days = get_cleanup_period_days()
    cleanup_period_ms = cleanup_period_days * 24 * 60 * 60 * 1000
    return datetime.now() - timedelta(milliseconds=cleanup_period_ms)


def add_cleanup_results(a: CleanupResult, b: CleanupResult) -> CleanupResult:
    """Add two cleanup results together."""
    return CleanupResult(messages=a.messages + b.messages, errors=a.errors + b.errors)


def convert_filename_to_date(filename: str) -> datetime | None:
    """
    Convert a Claude log filename to a datetime.

    Filenames use ISO format with special characters replaced.
    """
    try:
        # Remove extension and replace separators
        base = filename.split(".")[0]
        # Handle format: 2026-04-13T14-30-00-000Z
        iso = base.replace("T", " ").replace("-", ":")
        # Parse partial ISO
        parts = iso.split(":")
        if len(parts) >= 6:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            hour, minute, second = int(parts[3]), int(parts[4]), int(parts[5][:2])
            return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError):
        pass
    return None


# -----------------------------------------------------------------------------
# Directory cleanup helpers
# -----------------------------------------------------------------------------

async def cleanup_old_files_in_directory(
    dir_path: Path,
    cutoff_date: datetime,
    is_message_path: bool = False,
) -> CleanupResult:
    """
    Clean up old files in a single directory.

    Args:
        dir_path: Directory to clean
        cutoff_date: Files older than this are deleted
        is_message_path: If True, count as messages; otherwise as errors
    """
    result = CleanupResult()

    try:
        entries = list(dir_path.iterdir())
    except OSError as e:
        if e.code == "ENOENT":
            return result
        return CleanupResult(errors=1)

    for entry in entries:
        try:
            if entry.is_file():
                timestamp = entry.stat().st_mtime
                file_date = datetime.fromtimestamp(timestamp)
                if file_date < cutoff_date:
                    entry.unlink()
                    result.messages += 1
        except OSError:
            result.errors += 1

    return result


async def unlink_if_old(
    file_path: Path,
    cutoff_date: datetime,
) -> bool:
    """
    Delete a file if it's older than cutoff_date.

    Returns True if file was deleted.
    """
    try:
        stat = file_path.stat()
        if datetime.fromtimestamp(stat.st_mtime) < cutoff_date:
            file_path.unlink()
            return True
    except OSError:
        pass
    return False


async def try_rmdir(dir_path: Path) -> None:
    """Try to remove a directory. Silently ignores errors."""
    try:
        dir_path.rmdir()
    except OSError:
        pass


# -----------------------------------------------------------------------------
# Specific cleanup functions
# -----------------------------------------------------------------------------

async def cleanup_old_message_files() -> CleanupResult:
    """
    Clean up old message and error log files.

    Removes files from:
    - ~/.claude/errors/ (error logs)
    - ~/.claude/logs/mcp-logs-*/ (MCP logs)
    """
    from .path import get_home_dir

    result = CleanupResult()
    cutoff_date = get_cutoff_date()
    claude_dir = get_home_dir() / ".claude"
    errors_path = claude_dir / "errors"

    if errors_path.exists():
        result = add_cleanup_results(
            result, await cleanup_old_files_in_directory(errors_path, cutoff_date, False)
        )

    # Clean MCP log directories
    logs_path = claude_dir / "logs"
    if logs_path.exists():
        try:
            for entry in logs_path.iterdir():
                if entry.is_dir() and entry.name.startswith("mcp-logs-"):
                    sub_result = await cleanup_old_files_in_directory(
                        entry, cutoff_date, True
                    )
                    result = add_cleanup_results(result, sub_result)
                    await try_rmdir(entry)
        except OSError:
            pass

    return result


async def cleanup_old_session_files() -> CleanupResult:
    """
    Clean up old session files and tool results.

    Removes:
    - Old .jsonl and .cast files in project directories
    - Tool results subdirectories
    """
    from .stats import get_projects_dir

    result = CleanupResult()
    cutoff_date = get_cutoff_date()
    projects_dir = get_projects_dir()

    try:
        entries = list(projects_dir.iterdir())
    except OSError:
        return result

    for entry in entries:
        if not entry.is_dir():
            continue
        project_dir = entry
        try:
            sub_entries = list(project_dir.iterdir())
        except OSError:
            result.errors += 1
            continue

        for sub in sub_entries:
            try:
                if sub.is_file():
                    if sub.suffix in (".jsonl", ".cast"):
                        if await unlink_if_old(sub, cutoff_date):
                            result.messages += 1
                elif sub.is_dir():
                    # Clean tool-results subdirectory
                    tool_results = sub / "tool-results"
                    if tool_results.exists():
                        for tool_entry in tool_results.iterdir():
                            if tool_entry.is_file():
                                if await unlink_if_old(tool_entry, cutoff_date):
                                    result.messages += 1
                            elif tool_entry.is_dir():
                                for tf in tool_entry.iterdir():
                                    if tf.is_file() and await unlink_if_old(tf, cutoff_date):
                                        result.messages += 1
                                await try_rmdir(tool_entry)
                        await try_rmdir(tool_results)
                    await try_rmdir(sub)
            except OSError:
                result.errors += 1

        await try_rmdir(project_dir)

    return result


async def cleanup_old_plan_files() -> CleanupResult:
    """Clean up old plan markdown files from ~/.claude/plans/."""
    from .path import get_home_dir

    cutoff_date = get_cutoff_date()
    plans_dir = get_home_dir() / ".claude" / "plans"

    if not plans_dir.exists():
        return CleanupResult()

    result = CleanupResult()
    try:
        for entry in plans_dir.iterdir():
            if entry.is_file() and entry.suffix == ".md":
                if await unlink_if_old(entry, cutoff_date):
                    result.messages += 1
    except OSError:
        pass

    await try_rmdir(plans_dir)
    return result


async def cleanup_old_debug_logs() -> CleanupResult:
    """
    Clean up old debug log files from ~/.claude/debug/.

    Preserves the 'latest' symlink.
    """
    from .path import get_home_dir

    result = CleanupResult()
    cutoff_date = get_cutoff_date()
    debug_dir = get_home_dir() / ".claude" / "debug"

    if not debug_dir.exists():
        return result

    try:
        for entry in debug_dir.iterdir():
            # Preserve 'latest' symlink and non-.txt files
            if entry.name == "latest" or not (entry.is_file() and entry.name.endswith(".txt")):
                continue
            try:
                if await unlink_if_old(entry, cutoff_date):
                    result.messages += 1
            except OSError:
                result.errors += 1
    except OSError:
        pass

    return result


async def cleanup_old_session_env_dirs() -> CleanupResult:
    """Clean up old session-env directories from ~/.claude/session-env/."""
    from .path import get_home_dir

    result = CleanupResult()
    cutoff_date = get_cutoff_date()
    session_env_base = get_home_dir() / ".claude" / "session-env"

    if not session_env_base.exists():
        return result

    try:
        for entry in session_env_base.iterdir():
            if entry.is_dir():
                try:
                    stat = entry.stat()
                    if datetime.fromtimestamp(stat.st_mtime) < cutoff_date:
                        import shutil

                        shutil.rmtree(entry, ignore_errors=True)
                        result.messages += 1
                except OSError:
                    result.errors += 1
    except OSError:
        pass

    await try_rmdir(session_env_base)
    return result


async def cleanup_old_file_history_backups() -> CleanupResult:
    """Clean up old file history backup directories from ~/.claude/file-history/."""
    from .path import get_home_dir

    result = CleanupResult()
    cutoff_date = get_cutoff_date()
    file_history_dir = get_home_dir() / ".claude" / "file-history"

    if not file_history_dir.exists():
        return result

    try:
        for entry in file_history_dir.iterdir():
            if entry.is_dir():
                try:
                    stat = entry.stat()
                    if datetime.fromtimestamp(stat.st_mtime) < cutoff_date:
                        import shutil

                        shutil.rmtree(entry, ignore_errors=True)
                        result.messages += 1
                except OSError:
                    result.errors += 1
    except OSError:
        pass

    await try_rmdir(file_history_dir)
    return result


# -----------------------------------------------------------------------------
# Background cleanup orchestrator
# -----------------------------------------------------------------------------

async def cleanup_old_message_files_in_background() -> None:
    """
    Run all cleanup operations in the background.

    This is called periodically to clean up old files without blocking.
    """
    await cleanup_old_message_files()
    await cleanup_old_session_files()
    await cleanup_old_plan_files()
    await cleanup_old_file_history_backups()
    await cleanup_old_session_env_dirs()
    await cleanup_old_debug_logs()


# -----------------------------------------------------------------------------
# Throttled cleanup helpers
# -----------------------------------------------------------------------------

_ONE_DAY_MS = 24 * 60 * 60 * 1000


async def is_cleanup_marker_fresh(marker_path: Path) -> bool:
    """Check if a cleanup marker file exists and is recent (< 1 day old)."""
    try:
        stat = marker_path.stat()
        return (time.time() - stat.st_mtime) * 1000 < _ONE_DAY_MS
    except OSError:
        return False


async def cleanup_old_versions_throttled() -> None:
    """
    Throttled cleanup of old version directories.

    Uses a marker file to ensure it only runs once per 24 hours.
    """
    from .path import get_home_dir

    marker_path = get_home_dir() / ".claude" / ".version-cleanup"

    if await is_cleanup_marker_fresh(marker_path):
        return

    # Would run cleanupOldVersions() here
    try:
        marker_path.write_text(datetime.now().isoformat())
    except OSError:
        pass


async def cleanup_npm_cache_for_anthropic_packages() -> None:
    """
    Clean up old npm cache entries for Anthropic packages.

    Only runs once per day for ant users.
    """
    from .path import get_home_dir

    marker_path = get_home_dir() / ".claude" / ".npm-cache-cleanup"

    if await is_cleanup_marker_fresh(marker_path):
        return

    # Would clean npm cache here - placeholder
    try:
        marker_path.write_text(datetime.now().isoformat())
    except OSError:
        pass
