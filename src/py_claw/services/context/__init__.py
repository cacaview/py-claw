"""
Context service for system and user context injection.

Provides get_system_context() and get_user_context() for injecting
git status, claude.md content, and current date into conversations.

Aligned with TS reference: ClaudeCode-main/src/context.ts
"""
from py_claw.services.context.config import (
    ContextConfig,
    get_context_config,
    set_context_config,
    MAX_STATUS_CHARS,
    DEFAULT_MAX_MEMORY_CHARACTER_COUNT,
)
from py_claw.services.context.service import (
    get_git_status,
    get_claude_md_content,
    get_system_context,
    get_user_context,
    get_context,
    clear_context_cache,
)
from py_claw.services.context.types import (
    GitStatus,
    SystemContext,
    UserContext,
    ContextResult,
)


__all__ = [
    # Config
    "ContextConfig",
    "get_context_config",
    "set_context_config",
    "MAX_STATUS_CHARS",
    "DEFAULT_MAX_MEMORY_CHARACTER_COUNT",
    # Git status
    "get_git_status",
    # Claude.md
    "get_claude_md_content",
    # Context
    "get_system_context",
    "get_user_context",
    "get_context",
    "clear_context_cache",
    # Types
    "GitStatus",
    "SystemContext",
    "UserContext",
    "ContextResult",
]
