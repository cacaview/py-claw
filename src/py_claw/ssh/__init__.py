"""SSH session management module.

Provides SSH session management for remote Claude Code connections.
This module handles SSH tunnel creation and session management.
"""

from __future__ import annotations

from py_claw.ssh.session import SSH_SESSION_VERSION, SSHSession, SSHSessionManager, create_ssh_session

__all__ = [
    "SSH_SESSION_VERSION",
    "SSHSession",
    "SSHSessionManager",
    "create_ssh_session",
]
