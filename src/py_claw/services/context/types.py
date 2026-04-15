"""
Context types for system and user context.

Provides structured types for git status, system context, and user context
that are prepended to each conversation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class GitStatus:
    """Git status snapshot for a repository."""

    branch: str
    """Current branch name."""

    main_branch: str
    """Default/main branch name (typically 'main' or 'master')."""

    status: str
    """Short git status output, or '(clean)' if no changes."""

    recent_commits: str
    """Recent commit log (up to 5 commits, oneline format)."""

    git_user: str | None = None
    """Git user configured via git config user.name, if available."""

    is_truncated: bool = False
    """Whether the status was truncated due to length."""

    @property
    def formatted(self) -> str:
        """Format as a human-readable string for injection into context."""
        lines = [
            "This is the git status at the start of the conversation. Note that this status is a snapshot in time, and will not update during the conversation.",
            f"Current branch: {self.branch}",
            f"Main branch (you will usually use this for PRs): {self.main_branch}",
        ]
        if self.git_user:
            lines.append(f"Git user: {self.git_user}")
        lines.append(f"Status:\n{self.status}")
        lines.append(f"Recent commits:\n{self.recent_commits}")
        return "\n\n".join(lines)


@dataclass(slots=True)
class SystemContext:
    """System context containing git status and cache breaker injections."""

    git_status: str | None = None
    """Git status string, or None if not in a git repo or disabled."""

    cache_breaker: str | None = None
    """Cache breaker injection string, or None if not set."""

    @property
    def as_dict(self) -> dict[str, str]:
        """Convert to dict for SDK injection."""
        result: dict[str, str] = {}
        if self.git_status:
            result["gitStatus"] = self.git_status
        if self.cache_breaker:
            result["cacheBreaker"] = f"[CACHE_BREAKER: {self.cache_breaker}]"
        return result


@dataclass(slots=True)
class UserContext:
    """User context containing claude.md content and current date."""

    claude_md: str | None = None
    """Claude.md content loaded from various locations, or None if disabled."""

    current_date: str | None = None
    """Current date string formatted as 'Today is YYYY/MM/DD'."""

    @property
    def as_dict(self) -> dict[str, str]:
        """Convert to dict for SDK injection."""
        result: dict[str, str] = {}
        if self.claude_md:
            result["claudeMd"] = self.claude_md
        if self.current_date:
            result["currentDate"] = self.current_date
        return result


@dataclass(slots=True)
class ContextResult:
    """Combined result from get_system_context() and get_user_context()."""

    system: SystemContext
    """System context (git status, cache breaker)."""

    user: UserContext
    """User context (claude.md, current date)."""

    @property
    def all_strings(self) -> dict[str, str]:
        """Get all context strings merged together."""
        return {**self.system.as_dict, **self.user.as_dict}
