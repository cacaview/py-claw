"""
Agent worktree management service.

Provides lightweight worktree creation/removal for subagents, independent of
the global session state.

Key functions:
- create_agent_worktree(): Create a lightweight worktree for a subagent
- remove_agent_worktree(): Remove a worktree created by create_agent_worktree
- cleanup_stale_agent_worktrees(): Remove stale ephemeral worktrees older than cutoff
- is_ephemeral_slug(): Check if a slug matches an ephemeral pattern
- validate_worktree_slug(): Validate a worktree slug
"""
from __future__ import annotations

from .agent_worktree import (
    cleanup_stale_agent_worktrees,
    create_agent_worktree,
    flatten_slug,
    is_ephemeral_slug,
    remove_agent_worktree,
    validate_worktree_slug,
    worktree_branch_name,
    worktree_path_for,
)
from .types import AgentWorktreeResult, WorktreeSession

__all__ = [
    "AgentWorktreeResult",
    "WorktreeSession",
    "cleanup_stale_agent_worktrees",
    "create_agent_worktree",
    "flatten_slug",
    "is_ephemeral_slug",
    "remove_agent_worktree",
    "validate_worktree_slug",
    "worktree_branch_name",
    "worktree_path_for",
]
