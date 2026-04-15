"""
Swarm module for multi-agent team orchestration.

Based on ClaudeCode-main/src/utils/swarm/

Handles:
- Team file management
- Teammate lifecycle
- tmux pane management
- Git worktree management
- Session cleanup
"""
from __future__ import annotations

TEAM_LEAD_NAME = "team-lead"
SWARM_SESSION_NAME = "claude-swarm"
SWARM_VIEW_WINDOW_NAME = "swarm-view"
TMUX_COMMAND = "tmux"
HIDDEN_SESSION_NAME = "claude-hidden"

# Environment variables
TEAMMATE_COMMAND_ENV_VAR = "CLAUDE_CODE_TEAMMATE_COMMAND"
TEAMMATE_COLOR_ENV_VAR = "CLAUDE_CODE_AGENT_COLOR"
PLAN_MODE_REQUIRED_ENV_VAR = "CLAUDE_CODE_PLAN_MODE_REQUIRED"


def get_swarm_socket_name() -> str:
    """
    Gets the socket name for external swarm sessions (when user is not in tmux).
    Uses a separate socket to isolate swarm operations from user's tmux sessions.
    Includes PID to ensure multiple Claude instances don't conflict.
    """
    import os

    return f"claude-swarm-{os.getpid()}"


# Import backends for convenience
from . import backends


__all__ = [
    # Constants
    "TEAM_LEAD_NAME",
    "SWARM_SESSION_NAME",
    "SWARM_VIEW_WINDOW_NAME",
    "TMUX_COMMAND",
    "HIDDEN_SESSION_NAME",
    "TEAMMATE_COMMAND_ENV_VAR",
    "TEAMMATE_COLOR_ENV_VAR",
    "PLAN_MODE_REQUIRED_ENV_VAR",
    # Functions
    "get_swarm_socket_name",
    # Backends
    "backends",
    # Submodules
    "spawn_utils",
    "leader_permission_bridge",
    "permission_sync",
    "reconnection",
    "in_process_runner",
    "teammate_init",
    "teammate_layout_manager",
    "teammate_model",
    "teammate_prompt_addendum",
    "team_helpers",
]
