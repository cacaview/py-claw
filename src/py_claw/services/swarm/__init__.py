"""
Swarm multi-agent system.

This module provides multi-agent orchestration capabilities including:
- Team lead and teammate management
- Inter-agent communication via mailbox system
- Task distribution and claiming
- Permission bridging between leader and teammates
- tmux-based session isolation for process teammates

Reference: ClaudeCode-main/src/utils/swarm/
"""
from __future__ import annotations

from .constants import (
    TEAM_LEAD_NAME,
    SWARM_SESSION_NAME,
    SWARM_VIEW_WINDOW_NAME,
    TMUX_COMMAND,
    HIDDEN_SESSION_NAME,
    TEAMMATE_COMMAND_ENV_VAR,
    TEAMMATE_COLOR_ENV_VAR,
    PLAN_MODE_REQUIRED_ENV_VAR,
    get_swarm_socket_name,
)
from .types import (
    TeammateIdentity,
    TeammateContext,
    SwarmMessage,
    MailboxEntry,
    IdleNotification,
    PermissionRequest,
    PermissionResponse,
    ShutdownRequest,
)
from .mailbox import (
    write_to_mailbox,
    read_mailbox,
    mark_message_as_read,
    clear_mailbox,
)
from .service import SwarmService

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
    "get_swarm_socket_name",
    # Types
    "TeammateIdentity",
    "TeammateContext",
    "SwarmMessage",
    "MailboxEntry",
    "IdleNotification",
    "PermissionRequest",
    "PermissionResponse",
    "ShutdownRequest",
    # Mailbox
    "write_to_mailbox",
    "read_mailbox",
    "mark_message_as_read",
    "clear_mailbox",
    # Service
    "SwarmService",
]
