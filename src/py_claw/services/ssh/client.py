"""SSH client for port forwarding tunnels.

This module provides SSH tunnel functionality using the system SSH client
(subprocess-based) for reliable port forwarding.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Any

from .types import PortForward, SSHConfig, TunnelInfo, TunnelStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default SSH command path
DEFAULT_SSH_CMD = "ssh"


class SSHClient:
    """SSH client for managing tunnels.

    Uses the system SSH command for reliable tunnel management.
    """

    def __init__(self, config: SSHConfig) -> None:
        """Initialize SSH client.

        Args:
            config: SSH connection configuration.
        """
        self._config = config
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def connect(self, port_forwards: list[PortForward]) -> TunnelInfo:
        """Establish SSH connection with port forwarding.

        Args:
            port_forwards: List of port forwards to set up.

        Returns:
            TunnelInfo with connection details.

        Raises:
            SSHError: If connection fails.
        """
        if not port_forwards:
            raise SSHError("At least one port forward is required")

        # Build SSH command
        cmd = self._build_ssh_command(port_forwards)

        logger.debug(f"Starting SSH tunnel: {' '.join(cmd)}")

        try:
            # Start SSH process
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Give it a moment to start
            time.sleep(0.5)

            # Check if process started successfully
            if self._process.poll() is not None:
                _, stderr = self._process.communicate()
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                raise SSHError(f"SSH process exited immediately: {error_msg}")

            # Create tunnel info
            tunnel_info = TunnelInfo(
                name="",
                config=self._config,
                port_forwards=port_forwards,
                status=TunnelStatus.ACTIVE,
                process=self._process,
                started_at=time.time(),
            )

            logger.info(f"SSH tunnel established successfully")
            return tunnel_info

        except FileNotFoundError:
            raise SSHError("SSH command not found. Is OpenSSH installed?")
        except OSError as e:
            raise SSHError(f"Failed to start SSH: {e}")

    def disconnect(self) -> None:
        """Disconnect SSH tunnel gracefully."""
        with self._lock:
            if self._process is None:
                return

            proc = self._process
            self._process = None

            try:
                # Try graceful termination first
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    proc.kill()
                    proc.wait(timeout=2)
            except ProcessLookupError:
                pass  # Process already dead
            except Exception as e:
                logger.debug(f"Error during SSH disconnect: {e}")

    def get_process(self) -> subprocess.Popen[bytes] | None:
        """Get the underlying SSH process."""
        return self._process

    def _build_ssh_command(self, port_forwards: list[PortForward]) -> list[str]:
        """Build SSH command with port forwards.

        Args:
            port_forwards: List of port forwards.

        Returns:
            SSH command as list of arguments.
        """
        cmd = [DEFAULT_SSH_CMD]

        # Add user if specified
        if self._config.user:
            cmd.append(f"{self._config.user}@{self._config.host}")
        else:
            cmd.append(self._config.host)

        # Add port forwards (-L flag)
        for pf in port_forwards:
            cmd.extend(["-L", f"{pf.bind_address}:{pf.local_port}:{pf.remote_host}:{pf.remote_port}"])

        # Connection options
        cmd.extend([
            "-o", f"ServerAliveInterval={self._config.server_alive_interval}",
            "-o", f"ServerAliveCountMax={self._config.server_alive_count_max}",
            "-o", f"ConnectTimeout={self._config.connect_timeout}",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",  # Fail instead of prompting
        ])

        # Jump host
        if self._config.jump_host:
            cmd.extend(["-J", self._config.jump_host])

        # Don't execute remote command
        cmd.append("-N")

        # Port
        if self._config.port != 22:
            cmd.extend(["-p", str(self._config.port)])

        # Key file
        if self._config.key_file:
            cmd.extend(["-i", self._config.key_file])

        return cmd


class SSHError(Exception):
    """SSH-related errors."""

    pass


class TunnelManager:
    """Manages multiple SSH tunnels.

    Provides a registry of active tunnels with lifecycle management.
    """

    def __init__(self) -> None:
        """Initialize tunnel manager."""
        self._tunnels: dict[str, TunnelInfo] = {}
        self._lock = threading.Lock()

    def create_tunnel(
        self,
        name: str,
        config: SSHConfig,
        port_forwards: list[PortForward],
    ) -> TunnelInfo:
        """Create a new SSH tunnel.

        Args:
            name: Unique tunnel name.
            config: SSH configuration.
            port_forwards: Port forwards to set up.

        Returns:
            Created TunnelInfo.

        Raises:
            SSHError: If tunnel creation fails or name exists.
        """
        with self._lock:
            if name in self._tunnels:
                existing = self._tunnels[name]
                if existing.is_active:
                    raise SSHError(f"Tunnel '{name}' already exists and is active")

            # Create SSH client and connect
            client = SSHClient(config)
            tunnel_info = client.connect(port_forwards)
            tunnel_info.name = name
            tunnel_info.started_at = time.time()

            self._tunnels[name] = tunnel_info
            return tunnel_info

    def close_tunnel(self, name: str) -> bool:
        """Close and remove a tunnel.

        Args:
            name: Tunnel name.

        Returns:
            True if tunnel was closed, False if not found.
        """
        with self._lock:
            tunnel = self._tunnels.get(name)
            if tunnel is None:
                return False

            # Disconnect SSH client
            if hasattr(tunnel.process, "terminate") or hasattr(tunnel.process, "kill"):
                try:
                    tunnel.process.terminate()
                    tunnel.process.wait(timeout=5)
                except Exception:
                    try:
                        tunnel.process.kill()
                    except Exception:
                        pass

            tunnel.status = TunnelStatus.CLOSED
            tunnel.ended_at = time.time()
            del self._tunnels[name]
            return True

    def get_tunnel(self, name: str) -> TunnelInfo | None:
        """Get tunnel info by name.

        Args:
            name: Tunnel name.

        Returns:
            TunnelInfo or None if not found.
        """
        return self._tunnels.get(name)

    def list_tunnels(self) -> list[TunnelInfo]:
        """List all tunnels.

        Returns:
            List of TunnelInfo (active and recently closed).
        """
        with self._lock:
            return list(self._tunnels.values())

    def list_active_tunnels(self) -> list[TunnelInfo]:
        """List only active tunnels.

        Returns:
            List of active TunnelInfo.
        """
        with self._lock:
            return [t for t in self._tunnels.values() if t.is_active]

    def close_all(self) -> int:
        """Close all tunnels.

        Returns:
            Number of tunnels closed.
        """
        with self._lock:
            count = 0
            for name in list(self._tunnels.keys()):
                if self.close_tunnel(name):
                    count += 1
            return count


# Global tunnel manager instance
_manager: TunnelManager | None = None
_manager_lock = threading.Lock()


def get_tunnel_manager() -> TunnelManager:
    """Get the global TunnelManager singleton."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = TunnelManager()
    return _manager
