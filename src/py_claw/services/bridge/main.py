"""Standalone bridge server implementation.

Provides a standalone bridge server with poll loop and
support for up to 32 concurrent sessions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from py_claw.services.bridge.config import get_bridge_config
from py_claw.services.bridge.core import (
    BridgeCore,
    BridgeCoreParams,
    create_bridge_core,
)
from py_claw.services.bridge.state import get_bridge_state
from py_claw.services.bridge.types import BridgeConfig, BridgeState

logger = logging.getLogger(__name__)


# Server constants
MAX_CONCURRENT_SESSIONS = 32
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8090


@dataclass
class BridgeServerConfig:
    """Configuration for the bridge server."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    max_concurrent_sessions: int = MAX_CONCURRENT_SESSIONS
    poll_interval_seconds: float = 1.0
    max_poll_interval_seconds: float = 30.0


@dataclass
class SessionRecord:
    """Record of an active session in the server."""

    session_id: str
    core: BridgeCore
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)


class BridgeServer:
    """Standalone bridge server.

    Manages multiple concurrent bridge sessions with:
    - Poll loop for message fetching
    - Concurrent session management (up to 32)
    - Automatic reconnection
    - Graceful shutdown
    """

    def __init__(self, config: BridgeServerConfig | None = None):
        self.config = config or BridgeServerConfig()
        self._sessions: dict[str, SessionRecord] = {}
        self._server: asyncio.Server | None = None
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self) -> bool:
        """Start the bridge server.

        Returns:
            True if server started successfully
        """
        if self._running:
            logger.warning("Server already running")
            return False

        try:
            # Create TCP server for control connections
            self._server = await asyncio.start_server(
                self._handle_client,
                self.config.host,
                self.config.port,
            )

            self._running = True

            logger.info(
                "Bridge server started: %s:%d max_sessions=%d",
                self.config.host,
                self.config.port,
                self.config.max_concurrent_sessions,
            )

            return True

        except Exception as e:
            logger.error("Failed to start server: %s", e)
            return False

    async def stop(self) -> None:
        """Stop the bridge server gracefully."""
        self._running = False

        # Close all sessions
        async with self._lock:
            for record in list(self._sessions.values()):
                await record.core.teardown()
            self._sessions.clear()

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("Bridge server stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a client connection.

        Args:
            reader: Client input stream
            writer: Client output stream
        """
        addr = writer.get_extra_info("peername")
        logger.debug("Client connected: %s", addr)

        try:
            while self._running:
                # Read command from client
                line = await reader.readline()
                if not line:
                    break

                # Parse command
                try:
                    import json

                    cmd = json.loads(line.decode().strip())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                # Process command
                response = await self._process_command(cmd)

                # Send response
                if response:
                    writer.write((json.dumps(response) + "\n").encode())
                    await writer.drain()

        except Exception as e:
            logger.error("Client handler error: %s", e)

        finally:
            writer.close()
            await writer.wait_closed()
            logger.debug("Client disconnected: %s", addr)

    async def _process_command(
        self,
        cmd: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Process a client command.

        Args:
            cmd: Command object

        Returns:
            Response object, or None for no response
        """
        action = cmd.get("action")

        if action == "create_session":
            return await self._cmd_create_session(cmd)
        elif action == "close_session":
            return await self._cmd_close_session(cmd)
        elif action == "send_message":
            return await self._cmd_send_message(cmd)
        elif action == "list_sessions":
            return await self._cmd_list_sessions()
        else:
            return {"error": f"Unknown action: {action}"}

    async def _cmd_create_session(
        self,
        cmd: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle create_session command."""
        async with self._lock:
            # Check session limit
            if len(self._sessions) >= self.config.max_concurrent_sessions:
                return {
                    "success": False,
                    "error": f"Session limit reached ({self.config.max_concurrent_sessions})",
                }

        # Extract parameters
        base_url = cmd.get("base_url", "")
        session_ingress_url = cmd.get("session_ingress_url", "")
        environment_id = cmd.get("environment_id", "")
        access_token = cmd.get("access_token", "")

        if not all([base_url, session_ingress_url, environment_id, access_token]):
            return {"success": False, "error": "Missing required parameters"}

        # Create bridge core params
        params = BridgeCoreParams(
            base_url=base_url,
            session_ingress_url=session_ingress_url,
            environment_id=environment_id,
            access_token=access_token,
            title=cmd.get("title"),
            git_repo_url=cmd.get("git_repo_url"),
            branch=cmd.get("branch"),
            permission_mode=cmd.get("permission_mode"),
        )

        # Create core
        core = create_bridge_core(params)

        # Initialize
        success = await core.initialize()

        if not success:
            return {"success": False, "error": "Failed to initialize session"}

        # Record session
        async with self._lock:
            session_id = core.bridge_session_id
            if session_id:
                self._sessions[session_id] = SessionRecord(
                    session_id=session_id,
                    core=core,
                )

        return {
            "success": True,
            "session_id": session_id,
        }

    async def _cmd_close_session(
        self,
        cmd: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle close_session command."""
        session_id = cmd.get("session_id")
        if not session_id:
            return {"success": False, "error": "Missing session_id"}

        async with self._lock:
            record = self._sessions.pop(session_id, None)

        if not record:
            return {"success": False, "error": "Session not found"}

        await record.core.teardown()

        return {"success": True}

    async def _cmd_send_message(
        self,
        cmd: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle send_message command."""
        session_id = cmd.get("session_id")
        message = cmd.get("message")

        if not session_id or not message:
            return {"success": False, "error": "Missing session_id or message"}

        record = self._sessions.get(session_id)
        if not record:
            return {"success": False, "error": "Session not found"}

        success = await record.core.send_message(message)

        if success:
            record.last_activity = datetime.utcnow()

        return {"success": success}

    async def _cmd_list_sessions(
        self,
    ) -> dict[str, Any]:
        """Handle list_sessions command."""
        async with self._lock:
            sessions = [
                {
                    "session_id": r.session_id,
                    "state": r.core.state.value,
                    "created_at": r.created_at.isoformat(),
                    "last_activity": r.last_activity.isoformat(),
                }
                for r in self._sessions.values()
            ]

        return {
            "sessions": sessions,
            "count": len(sessions),
            "max": self.config.max_concurrent_sessions,
        }

    @property
    def session_count(self) -> int:
        """Get current session count."""
        return len(self._sessions)

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running


# Global server instance
_server: BridgeServer | None = None


def get_bridge_server() -> BridgeServer:
    """Get the global bridge server singleton."""
    global _server
    if _server is None:
        _server = BridgeServer()
    return _server


async def run_bridge_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    """Run the bridge server.

    Args:
        host: Host to bind to
        port: Port to listen on
    """
    server = get_bridge_server()
    server.config.host = host
    server.config.port = port

    if not await server.start():
        return

    # Keep running until interrupted
    try:
        while server.is_running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()
