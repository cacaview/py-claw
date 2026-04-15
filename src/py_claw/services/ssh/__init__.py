"""SSH tunnel service - SSH port forwarding management."""
from __future__ import annotations

from .client import SSHClient, SSHError, TunnelManager, get_tunnel_manager
from .service import SSHService, get_ssh_service
from .types import (
    PortForward,
    SSHConfig,
    TunnelCreateOptions,
    TunnelInfo,
    TunnelStatus,
)

__all__ = [
    "SSHService",
    "SSHClient",
    "SSHError",
    "TunnelManager",
    "TunnelInfo",
    "TunnelStatus",
    "SSHConfig",
    "PortForward",
    "TunnelCreateOptions",
    "get_ssh_service",
    "get_tunnel_manager",
]
