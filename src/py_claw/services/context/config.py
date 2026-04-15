"""
Context service configuration.

Controls whether git status and claude.md loading are enabled.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


# Maximum characters for git status before truncation
MAX_STATUS_CHARS = 2000

# Default claude.md max character count
DEFAULT_MAX_MEMORY_CHARACTER_COUNT = 40000


@dataclass(slots=True)
class ContextConfig:
    """Configuration for the context service."""

    include_git_status: bool = True
    """Whether to include git status in system context."""

    include_claude_md: bool = True
    """Whether to include claude.md content in user context."""

    max_status_chars: int = MAX_STATUS_CHARS
    """Maximum characters for git status before truncation."""

    max_memory_chars: int = DEFAULT_MAX_MEMORY_CHARACTER_COUNT
    """Maximum characters for claude.md content."""

    def is_git_disabled_by_env(self) -> bool:
        """Check if git status is disabled by environment variable."""
        return bool(os.environ.get("CLAUDE_CODE_REMOTE"))

    def is_claude_md_disabled_by_env(self) -> bool:
        """Check if claude.md loading is disabled by environment variable."""
        return bool(os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS"))

    def should_include_git(self) -> bool:
        """Determine if git status should be included."""
        return self.include_git_status and not self.is_git_disabled_by_env()

    def should_include_claude_md(self) -> bool:
        """Determine if claude.md should be included."""
        return self.include_claude_md and not self.is_claude_md_disabled_by_env()


# Global config instance
_config: ContextConfig | None = None


def get_context_config() -> ContextConfig:
    """Get the current context configuration."""
    global _config
    if _config is None:
        _config = ContextConfig()
    return _config


def set_context_config(config: ContextConfig) -> None:
    """Set the context configuration."""
    global _config
    _config = config
