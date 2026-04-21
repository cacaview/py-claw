"""SSH session management.

Manages SSH tunnel creation and lifecycle for remote Claude Code sessions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

SSH_SESSION_VERSION = "1.0"


@dataclass
class SSHSession:
    """Represents an SSH session for remote Claude Code connection.

    Attributes:
        session_id: Unique identifier for the session
        created_at: When the session was created
        status: Current session status
        host: Remote host address
        port: SSH port number
        user: SSH username
        tunnel_local_port: Local port for the tunnel
        tunnel_remote_port: Remote port for the tunnel
        metadata: Additional session metadata
    """

    session_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "disconnected"
    host: str | None = None
    port: int = 22
    user: str | None = None
    tunnel_local_port: int | None = None
    tunnel_remote_port: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary.

        Returns:
            Dictionary representation of the session
        """
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "tunnel_local_port": self.tunnel_local_port,
            "tunnel_remote_port": self.tunnel_remote_port,
            "metadata": self.metadata,
        }


class SSHSessionManager:
    """Manages SSH sessions for remote Claude Code connections.

    Provides:
    - SSH tunnel creation and teardown
    - Session lifecycle management
    - Connection state tracking
    """

    def __init__(self) -> None:
        """Initialize the SSH session manager."""
        self._sessions: dict[str, SSHSession] = {}
        self._active_tunnels: dict[str, asyncio.Task] = {}

    def create_session(
        self,
        host: str,
        user: str,
        port: int = 22,
        key_file: str | None = None,
        password: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SSHSession:
        """Create a new SSH session.

        Args:
            host: Remote host address
            user: SSH username
            port: SSH port number (default 22)
            key_file: Path to SSH private key file
            password: SSH password (if not using key)
            metadata: Additional metadata to attach

        Returns:
            New SSH session object
        """
        import uuid

        session_id = str(uuid.uuid4())
        session = SSHSession(
            session_id=session_id,
            status="created",
            host=host,
            port=port,
            user=user,
            metadata=metadata or {},
        )

        self._sessions[session_id] = session
        logger.info("Created SSH session: %s", session_id)

        return session

    async def connect(self, session_id: str) -> bool:
        """Connect an SSH session and establish tunnel.

        Args:
            session_id: ID of the session to connect

        Returns:
            True if connection successful
        """
        import asyncssh

        session = self._sessions.get(session_id)
        if not session:
            logger.error("Session not found: %s", session_id)
            return False

        try:
            session.status = "connecting"

            # Determine SSH port
            port = session.port or 22

            # Build SSH connection options
            conn_options = {
                "host": session.host,
                "port": port,
                "username": session.user,
                "known_hosts": None,  # Disable host key checking for flexibility
            }

            # Add authentication
            if session.metadata.get("key_file"):
                conn_options["client_keys"] = [session.metadata["key_file"]]
            elif session.metadata.get("password"):
                conn_options["password"] = session.metadata["password"]

            # Establish SSH connection
            async with asyncssh.connect(**conn_options) as conn:
                # Create local port forwarding tunnel
                local_port = session.tunnel_local_port or 0
                remote_host = session.metadata.get("tunnel_remote_host", "localhost")
                remote_port = session.tunnel_remote_port or 8080

                # Start a port forwarder
                listener = await conn.forward_remote_listen(
                    remote_host,
                    remote_port,
                    listen_host="localhost",
                    listen_port=local_port,
                )

                # Update session with actual local port if assigned
                if local_port == 0 and listener:
                    local_port = listener._port if hasattr(listener, '_port') else 0
                    session.tunnel_local_port = local_port

                # Keep connection alive until disconnect
                session.status = "connected"
                logger.info(
                    "Connected SSH session: %s -> tunnel local=%s remote=%s:%s",
                    session_id,
                    local_port,
                    remote_host,
                    remote_port,
                )

                # Store the listener for cleanup
                self._active_tunnels[session_id] = listener

                # Wait for tunnel to be closed
                await listener.wait_closed()

        except asyncssh.DisconnectError as e:
            logger.error("SSH disconnect error for session %s: %s", session_id, e)
            session.status = "failed"
            return False
        except asyncssh.ConnectionLost as e:
            logger.error("SSH connection lost for session %s: %s", session_id, e)
            session.status = "disconnected"
            return False
        except Exception as e:
            logger.error("Failed to connect session %s: %s", session_id, e)
            session.status = "failed"
            return False

    async def disconnect(self, session_id: str) -> bool:
        """Disconnect an SSH session.

        Args:
            session_id: ID of the session to disconnect

        Returns:
            True if disconnection successful
        """
        session = self._sessions.get(session_id)
        if not session:
            return False

        try:
            # Cancel active tunnel task if any
            tunnel_task = self._active_tunnels.pop(session_id, None)
            if tunnel_task:
                tunnel_task.cancel()

            session.status = "disconnected"
            logger.info("Disconnected SSH session: %s", session_id)
            return True

        except Exception as e:
            logger.error("Failed to disconnect session %s: %s", session_id, e)
            return False

    async def delete_session(self, session_id: str) -> bool:
        """Delete an SSH session.

        Args:
            session_id: ID of the session to delete

        Returns:
            True if deletion successful
        """
        if session_id not in self._sessions:
            return False

        # Disconnect first if connected
        await self.disconnect(session_id)

        del self._sessions[session_id]
        logger.info("Deleted SSH session: %s", session_id)
        return True

    def get_session(self, session_id: str) -> SSHSession | None:
        """Get a session by ID.

        Args:
            session_id: ID of the session to retrieve

        Returns:
            Session object or None if not found
        """
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[SSHSession]:
        """List all SSH sessions.

        Returns:
            List of all sessions
        """
        return list(self._sessions.values())

    def get_connected_sessions(self) -> list[SSHSession]:
        """Get all connected sessions.

        Returns:
            List of connected sessions
        """
        return [s for s in self._sessions.values() if s.status == "connected"]


# Global session manager instance
_session_manager: SSHSessionManager | None = None


def get_ssh_session_manager() -> SSHSessionManager:
    """Get the global SSH session manager singleton.

    Returns:
        Global SSHSessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SSHSessionManager()
    return _session_manager


async def create_ssh_session(
    host: str,
    user: str,
    port: int = 22,
    key_file: str | None = None,
    password: str | None = None,
) -> SSHSession:
    """Create and connect a new SSH session.

    This is a convenience function that creates a session and connects it.

    Args:
        host: Remote host address
        user: SSH username
        port: SSH port number (default 22)
        key_file: Path to SSH private key file
        password: SSH password (if not using key)

    Returns:
        Connected SSH session object
    """
    manager = get_ssh_session_manager()
    session = manager.create_session(
        host=host,
        user=user,
        port=port,
        key_file=key_file,
        password=password,
    )

    success = await manager.connect(session.session_id)
    if not success:
        session.status = "failed"

    return session
