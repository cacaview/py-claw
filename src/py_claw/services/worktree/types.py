"""Worktree service types."""
from __future__ import annotations

from pydantic import BaseModel


class AgentWorktreeResult(BaseModel):
    """Result of creating an agent worktree."""

    worktree_path: str
    worktree_branch: str | None = None
    head_commit: str | None = None
    git_root: str | None = None
    hook_based: bool = False


class WorktreeSession(BaseModel):
    """Session state for an active worktree."""

    original_cwd: str
    worktree_path: str
    worktree_branch: str | None = None
    original_branch: str | None = None
    original_head_commit: str | None = None
    session_id: str | None = None
    tmux_session_name: str | None = None
    hook_based: bool = False
    creation_duration_ms: int | None = None
    used_sparse_paths: bool = False
