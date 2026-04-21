"""SSH tunnel service - high-level SSH tunnel management.

Provides a service interface for creating and managing SSH tunnels,
integrating with the command system.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .client import SSHClient, SSHError, TunnelManager, get_tunnel_manager
from .types import PortForward, SSHConfig, TunnelCreateOptions, TunnelInfo, TunnelStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SSHService:
    """High-level SSH tunnel service.

    Provides a clean interface for tunnel management with
    automatic naming and lifecycle handling.
    """

    def __init__(self, manager: TunnelManager | None = None) -> None:
        """Initialize SSH service.

        Args:
            manager: Optional TunnelManager instance (uses global if not provided).
        """
        self._manager = manager or get_tunnel_manager()

    def create_tunnel(
        self,
        host: str,
        local_port: int,
        remote_host: str,
        remote_port: int,
        user: str | None = None,
        jump_host: str | None = None,
        name: str | None = None,
    ) -> TunnelInfo:
        """Create an SSH tunnel with a single port forward.

        Args:
            host: Remote SSH host.
            local_port: Local port to bind.
            remote_host: Remote host to forward to.
            remote_port: Remote port to forward to.
            user: Optional SSH username.
            jump_host: Optional jump/bastion host.
            name: Optional tunnel name (auto-generated if not provided).

        Returns:
            Created TunnelInfo.

        Raises:
            SSHError: If tunnel creation fails.
        """
        config = SSHConfig(
            host=host,
            user=user,
            jump_host=jump_host,
        )

        port_forward = PortForward(
            local_port=local_port,
            remote_host=remote_host,
            remote_port=remote_port,
        )

        # Generate name if not provided
        if name is None:
            name = self._generate_tunnel_name(host, local_port, jump_host)

        return self._manager.create_tunnel(name, config, [port_forward])

    def create_reverse_tunnel(
        self,
        host: str,
        remote_port: int,
        local_port: int,
        user: str | None = None,
        name: str | None = None,
    ) -> TunnelInfo:
        """Create a reverse SSH tunnel (-R instead of -L).

        Args:
            host: Remote SSH host.
            remote_port: Port on remote host to bind.
            local_port: Local port to forward from.
            user: Optional SSH username.
            name: Optional tunnel name.

        Returns:
            Created TunnelInfo.

        Raises:
            SSHError: If tunnel creation fails.
        """
        config = SSHConfig(
            host=host,
            user=user,
        )

        if name is None:
            name = self._generate_reverse_tunnel_name(host, remote_port)

        # Create client and connect with reverse tunnel
        client = SSHClient(config)
        tunnel_info = client.connect_reverse(remote_port, local_port)
        tunnel_info.name = name

        # Register with manager
        self._manager._tunnels[name] = tunnel_info

        logger.info(f"Created reverse tunnel '{name}': remote :{remote_port} -> local :{local_port}")
        return tunnel_info

    def _generate_reverse_tunnel_name(
        self,
        host: str,
        remote_port: int,
    ) -> str:
        """Generate a unique reverse tunnel name.

        Args:
            host: Remote host.
            remote_port: Remote port.

        Returns:
            Generated tunnel name.
        """
        base = f"reverse-tunnel-{remote_port}-{host}"

        # Check for existing name and add suffix if needed
        counter = 1
        while self._manager.get_tunnel(base) is not None:
            base = f"reverse-tunnel-{remote_port}-{host}-{counter}"
            counter += 1

        return base

    def close_tunnel(self, name: str) -> bool:
        """Close a tunnel by name.

        Args:
            name: Tunnel name.

        Returns:
            True if closed, False if not found.
        """
        return self._manager.close_tunnel(name)

    def get_tunnel(self, name: str) -> TunnelInfo | None:
        """Get tunnel info by name.

        Args:
            name: Tunnel name.

        Returns:
            TunnelInfo or None.
        """
        return self._manager.get_tunnel(name)

    def list_tunnels(self, active_only: bool = False) -> list[TunnelInfo]:
        """List tunnels.

        Args:
            active_only: If True, only return active tunnels.

        Returns:
            List of TunnelInfo.
        """
        if active_only:
            return self._manager.list_active_tunnels()
        return self._manager.list_tunnels()

    def close_all(self) -> int:
        """Close all tunnels.

        Returns:
            Number of tunnels closed.
        """
        return self._manager.close_all()

    def get_tunnel_status(self, name: str) -> str:
        """Get formatted status of a tunnel.

        Args:
            name: Tunnel name.

        Returns:
            Formatted status string.
        """
        tunnel = self._manager.get_tunnel(name)
        if tunnel is None:
            return f"Tunnel '{name}' not found."

        lines = [f"=== Tunnel: {name} ==="]
        lines.append(f"Status: {tunnel.status.value}")
        lines.append(f"Host: {tunnel.config.host}")

        if tunnel.config.user:
            lines.append(f"User: {tunnel.config.user}")

        if tunnel.config.jump_host:
            lines.append(f"Jump Host: {tunnel.config.jump_host}")

        for pf in tunnel.port_forwards:
            lines.append(f"Forward: {pf.bind_address}:{pf.local_port} -> {pf.remote_host}:{pf.remote_port}")

        if tunnel.started_at:
            elapsed = time.time() - tunnel.started_at
            lines.append(f"Uptime: {self._format_duration(elapsed)}")

        if tunnel.error:
            lines.append(f"Error: {tunnel.error}")

        return "\n".join(lines)

    def get_all_status(self) -> str:
        """Get status of all tunnels.

        Returns:
            Formatted status string for all tunnels.
        """
        tunnels = self.list_tunnels()
        if not tunnels:
            return "No tunnels."

        active = [t for t in tunnels if t.is_active]
        closed = [t for t in tunnels if not t.is_active]

        lines = ["=== SSH Tunnels ===", ""]

        if active:
            lines.append(f"Active Tunnels ({len(active)}):")
            for t in active:
                elapsed = time.time() - t.started_at if t.started_at else 0
                pf = t.port_forwards[0] if t.port_forwards else None
                if pf:
                    lines.append(
                        f"  {t.name}: localhost:{pf.local_port} -> {t.config.host} -> {pf.remote_host}:{pf.remote_port} ({self._format_duration(elapsed)})"
                    )
                else:
                    lines.append(f"  {t.name}: {t.config.host}")
            lines.append("")

        if closed:
            lines.append(f"Closed Tunnels ({len(closed)}):")
            for t in closed:
                lines.append(f"  {t.name}: {t.status.value}")

        return "\n".join(lines)

    def _generate_tunnel_name(
        self,
        host: str,
        local_port: int,
        jump_host: str | None = None,
    ) -> str:
        """Generate a unique tunnel name.

        Args:
            host: Remote host.
            local_port: Local port.
            jump_host: Optional jump host.

        Returns:
            Generated tunnel name.
        """
        if jump_host:
            base = f"tunnel-{local_port}-{jump_host}"
        else:
            base = f"tunnel-{local_port}-{host}"

        # Check for existing name and add suffix if needed
        name = base
        counter = 1
        while self._manager.get_tunnel(name) is not None:
            name = f"{base}-{counter}"
            counter += 1

        return name

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted string like "1h 23m 45s".
        """
        if seconds < 60:
            return f"{seconds:.0f}s"

        minutes = int(seconds // 60)
        seconds = int(seconds % 60)

        if minutes < 60:
            return f"{minutes}m {seconds}s"

        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}h {minutes}m"


# Global service instance
_service: SSHService | None = None
_service_lock = None


def get_ssh_service() -> SSHService:
    """Get the global SSHService singleton."""
    global _service, _service_lock
    if _service is None:
        try:
            import threading
            if _service_lock is None:
                _service_lock = threading.Lock()
            with _service_lock:
                if _service is None:
                    _service = SSHService()
        except Exception:
            if _service is None:
                _service = SSHService()
    return _service
