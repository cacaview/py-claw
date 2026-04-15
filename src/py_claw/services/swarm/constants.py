"""
Swarm constants.

Constants for the Swarm multi-agent system.
"""
from __future__ import annotations

import os

# Team lead identifier
TEAM_LEAD_NAME = "team-lead"

# Swarm session names
SWARM_SESSION_NAME = "claude-swarm"
SWARM_VIEW_WINDOW_NAME = "swarm-view"

# tmux command
TMUX_COMMAND = "tmux"

# Hidden session for background operations
HIDDEN_SESSION_NAME = "claude-hidden"


def get_swarm_socket_name() -> str:
    """
    Gets the socket name for external swarm sessions (when user is not in tmux).
    Uses a separate socket to isolate swarm operations from user's tmux sessions.
    Includes PID to ensure multiple Claude instances don't conflict.

    Returns:
        Socket name string
    """
    return f"claude-swarm-{os.getpid()}"


# Environment variable to override the command used to spawn teammate instances
# If not set, defaults to the current Claude binary
TEAMMATE_COMMAND_ENV_VAR = "CLAUDE_CODE_TEAMMATE_COMMAND"

# Environment variable set on spawned teammates to indicate their assigned color
# Used for colored output and pane identification
TEAMMATE_COLOR_ENV_VAR = "CLAUDE_CODE_AGENT_COLOR"

# Environment variable set on spawned teammates to require plan mode before implementation
# When set to 'true', teammates must enter plan mode and get approval before writing code
PLAN_MODE_REQUIRED_ENV_VAR = "CLAUDE_CODE_PLAN_MODE_REQUIRED"

# Mailbox directory name
MAILBOX_DIR_NAME = ".claude-mailbox"

# Default poll interval for mailbox checking (ms)
MAILBOX_POLL_INTERVAL_MS = 500

# Permission poll interval (ms)
PERMISSION_POLL_INTERVAL_MS = 500

# Session end hook timeout default (ms)
SESSION_END_HOOK_TIMEOUT_MS = 1500
