"""
Context service implementation.

Provides system context (git status) and user context (claude.md content)
that are prepended to each conversation.

Aligned with TS reference: ClaudeCode-main/src/context.ts
"""
from __future__ import annotations

import subprocess
import shutil
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_context_config, MAX_STATUS_CHARS
from .types import (
    GitStatus,
    SystemContext,
    UserContext,
    ContextResult,
)


# ------------------------------------------------------------------
# Git utilities
# ------------------------------------------------------------------


def _get_git_exe() -> str | None:
    """Get the git executable path."""
    return shutil.which("git")


def _is_git_repo(cwd: Path | None = None) -> bool:
    """Check if the current directory is inside a git repository."""
    git_exe = _get_git_exe()
    if not git_exe:
        return False

    try:
        result = subprocess.run(
            [git_exe, "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, OSError):
        return False


def _get_branch(cwd: Path | None = None) -> str | None:
    """Get the current branch name."""
    git_exe = _get_git_exe()
    if not git_exe:
        return None

    try:
        result = subprocess.run(
            [git_exe, "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _get_default_branch(cwd: Path | None = None) -> str | None:
    """Get the default/main branch name."""
    git_exe = _get_git_exe()
    if not git_exe:
        return None

    try:
        # Try main first, then master
        for branch in ("main", "master"):
            result = subprocess.run(
                [git_exe, "rev-parse", f"origin/{branch}"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return branch
    except (subprocess.TimeoutExpired, OSError):
        pass
    return "main"


def _get_git_user(cwd: Path | None = None) -> str | None:
    """Get the git user name from config."""
    git_exe = _get_git_exe()
    if not git_exe:
        return None

    try:
        result = subprocess.run(
            [git_exe, "config", "user.name"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            name = result.stdout.strip()
            return name if name else None
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _run_git_command(
    args: list[str],
    cwd: Path | None = None,
) -> str | None:
    """Run a git command and return stdout, or None on failure."""
    git_exe = _get_git_exe()
    if not git_exe:
        return None

    try:
        result = subprocess.run(
            [git_exe] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


# ------------------------------------------------------------------
# Git status (cached per process)
# ------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_git_status(cwd: str | None = None) -> str | None:
    """
    Get formatted git status string for context injection.

    Cached for the duration of the process since git status is a
    snapshot that shouldn't change during a conversation.

    Args:
        cwd: Working directory to check. Defaults to current directory.

    Returns:
        Formatted git status string, or None if not in a git repo.
    """
    path = Path(cwd) if cwd else Path.cwd()

    # Check if inside git repo
    if not _is_git_repo(path):
        return None

    # Run git commands in parallel-ish (sequentially here for simplicity)
    branch = _get_branch(path)
    if not branch:
        return None

    main_branch = _get_default_branch(path) or "main"
    git_user = _get_git_user(path)

    # Git status with --short
    status = _run_git_command(
        ["--no-optional-locks", "status", "--short"],
        cwd=path,
    ) or ""

    # Recent commits (up to 5)
    log = _run_git_command(
        ["--no-optional-locks", "log", "--oneline", "-n", "5"],
        cwd=path,
    ) or ""

    # Truncate if too long
    is_truncated = len(status) > MAX_STATUS_CHARS
    if is_truncated:
        status = status[:MAX_STATUS_CHARS] + (
            "\n... (truncated because it exceeds 2k characters. "
            'If you need more information, run "git status" using BashTool)'
        )

    # Build formatted string (mimics TS getGitStatus)
    parts = [
        "This is the git status at the start of the conversation. "
        "Note that this status is a snapshot in time, and will not update during the conversation.",
        f"Current branch: {branch}",
        f"Main branch (you will usually use this for PRs): {main_branch}",
    ]
    if git_user:
        parts.append(f"Git user: {git_user}")
    parts.append(f"Status:\n{status or '(clean)'}")
    parts.append(f"Recent commits:\n{log}")

    return "\n\n".join(parts)


# ------------------------------------------------------------------
# Claude.md discovery and loading
# ------------------------------------------------------------------


def _get_claude_config_home() -> Path:
    """Get the Claude config home directory."""
    return Path.home() / ".claude"


def _find_claude_md_files(cwd: Path | None = None) -> list[tuple[Path, str]]:
    """
    Find all claude.md files from current directory up to root.

    Returns list of (path, priority) tuples where higher priority = closer to cwd.
    Priority is based on directory depth - files closer to current dir get higher priority.
    """
    if cwd is None:
        cwd = Path.cwd()

    files: list[tuple[Path, str]] = []

    # Project-level claude.md files (traverse from cwd to root)
    current = cwd
    while True:
        candidates = [
            current / "CLAUDE.md",
            current / ".claude" / "CLAUDE.md",
        ]
        # Also check .claude/rules/ directory
        rules_dir = current / ".claude" / "rules"
        if rules_dir.is_dir():
            try:
                for md_file in rules_dir.glob("*.md"):
                    candidates.append(md_file)
            except OSError:
                pass

        for candidate in candidates:
            if candidate.is_file():
                try:
                    # Use depth as priority (higher = closer to start)
                    depth = len(cwd.parts) - len(current.parts)
                    files.append((candidate, str(100 - depth)))
                except OSError:
                    pass

        parent = current.parent
        if parent == current:
            break
        current = parent

    # User-level ~/.claude/CLAUDE.md
    user_claude_md = _get_claude_config_home() / "CLAUDE.md"
    if user_claude_md.is_file():
        try:
            files.append((user_claude_md, "0"))
        except OSError:
            pass

    # Managed memory /etc/claude-code/CLAUDE.md (Unix only)
    if hasattr(Path, "/etc"):
        managed_md = Path("/etc/claude-code/CLAUDE.md")
        if managed_md.is_file():
            try:
                files.append((managed_md, "-1"))
            except OSError:
                pass

    # Sort by priority (higher first), then return just paths
    files.sort(key=lambda x: int(x[1]) if x[1].isdigit() else 0, reverse=True)
    return [(path, priority) for path, priority in files]


@lru_cache(maxsize=1)
def get_claude_md_content(cwd: str | None = None) -> str | None:
    """
    Load claude.md content from all discovered locations.

    Files are loaded in reverse priority order (lowest first), so higher
    priority content overwrites lower priority. This matches the TS behavior
    where "files closer to the current directory have higher priority".

    Returns:
        Combined claude.md content, or None if no files found or all disabled.
    """
    config = get_context_config()
    if not config.should_include_claude_md():
        return None

    if cwd is None:
        cwd = Path.cwd()
    else:
        cwd = Path(cwd)

    files_with_priority = _find_claude_md_files(cwd)
    if not files_with_priority:
        return None

    config_obj = get_context_config()
    max_chars = config_obj.max_memory_chars
    total_len = 0
    parts: list[str] = []

    for path, _priority in reversed(files_with_priority):  # Low priority first
        try:
            content = path.read_text(encoding="utf-8")
            if total_len + len(content) <= max_chars:
                parts.append(content)
                total_len += len(content)
            else:
                # Truncate if adding this file would exceed limit
                remaining = max_chars - total_len
                if remaining > 100:  # Only add if meaningful content fits
                    parts.append(content[:remaining])
                break
        except (OSError, UnicodeDecodeError):
            continue

    return "\n\n".join(parts) if parts else None


# ------------------------------------------------------------------
# System and User context (memoized)
# ------------------------------------------------------------------


_system_context_cache: SystemContext | None = None
_user_context_cache: UserContext | None = None


def get_system_context(
    include_git: bool = True,
    cache_breaker: str | None = None,
) -> SystemContext:
    """
    Get system context for conversation injection.

    Memoized for the session duration.

    Args:
        include_git: Whether to include git status.
        cache_breaker: Optional cache breaker string.

    Returns:
        SystemContext with git status and cache breaker.
    """
    global _system_context_cache

    if _system_context_cache is None:
        git_status: str | None = None
        if include_git:
            try:
                git_status = get_git_status()
            except Exception:
                pass

        _system_context_cache = SystemContext(
            git_status=git_status,
            cache_breaker=cache_breaker,
        )

    return _system_context_cache


def get_user_context() -> UserContext:
    """
    Get user context for conversation injection.

    Memoized for the session duration.

    Returns:
        UserContext with claude.md content and current date.
    """
    global _user_context_cache

    if _user_context_cache is None:
        claude_md = None
        try:
            claude_md = get_claude_md_content()
        except Exception:
            pass

        today = datetime.now()
        current_date = f"Today is {today.year}/{today.month:02d}/{today.day:02d}."

        _user_context_cache = UserContext(
            claude_md=claude_md,
            current_date=current_date,
        )

    return _user_context_cache


def get_context() -> ContextResult:
    """
    Get combined system and user context.

    Returns:
        ContextResult containing both system and user context.
    """
    config = get_context_config()
    return ContextResult(
        system=get_system_context(include_git=config.should_include_git()),
        user=get_user_context(),
    )


def clear_context_cache() -> None:
    """Clear the context caches (for testing or cache invalidation)."""
    global _system_context_cache, _user_context_cache
    _system_context_cache = None
    _user_context_cache = None
    get_git_status.cache_clear()
    get_claude_md_content.cache_clear()
