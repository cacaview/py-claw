"""SSH service types and configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TunnelStatus(str, Enum):
    """Status of an SSH tunnel."""

    PENDING = "pending"
    ACTIVE = "active"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    CLOSED = "closed"


@dataclass
class SSHConfig:
    """Configuration for SSH connections.

    Attributes:
        host: Remote SSH host.
        port: SSH port (default 22).
        user: SSH username.
        password: SSH password (if not using key auth).
        key_file: Path to private key file.
        jump_host: Optional bastion/jump host for tunneling.
        keepalive_interval: Keepalive interval in seconds.
        keepalive_max: Maximum keepalive attempts before disconnect.
        connect_timeout: Connection timeout in seconds.
        server_alive_interval: SSH server alive interval.
        server_alive_count_max: SSH server alive max count.
    """

    host: str
    port: int = 22
    user: str | None = None
    password: str | None = None
    key_file: str | None = None
    jump_host: str | None = None
    keepalive_interval: int = 60
    keepalive_max: int = 3
    connect_timeout: int = 30
    server_alive_interval: int = 60
    server_alive_count_max: int = 3


@dataclass
class PortForward:
    """A port forwarding configuration.

    Attributes:
        local_port: Local port to bind.
        remote_host: Remote host to forward to.
        remote_port: Remote port to forward to.
        bind_address: Address to bind to locally (default 127.0.0.1).
    """

    local_port: int
    remote_host: str
    remote_port: int
    bind_address: str = "127.0.0.1"


@dataclass
class TunnelInfo:
    """Information about an active or historical tunnel.

    Attributes:
        name: Unique tunnel name.
        config: SSH configuration used.
        port_forwards: List of port forwards.
        status: Current tunnel status.
        process: Associated subprocess (if using CLI mode).
        started_at: When the tunnel was started.
        ended_at: When the tunnel ended (if closed).
        error: Error message if failed.
    """

    name: str
    config: SSHConfig
    port_forwards: list[PortForward] = field(default_factory=list)
    status: TunnelStatus = TunnelStatus.PENDING
    process: Any = None  # subprocess.Popen or async client
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error: str | None = None

    @property
    def is_active(self) -> bool:
        """Check if tunnel is currently active."""
        return self.status == TunnelStatus.ACTIVE


@dataclass
class TunnelCreateOptions:
    """Options for creating a tunnel.

    Attributes:
        ssh_config: SSH connection configuration.
        name: Optional tunnel name (auto-generated if not provided).
        port_forwards: List of port forwards to set up.
        background: Whether to run in background.
    """

    ssh_config: SSHConfig
    name: str | None = None
    port_forwards: list[PortForward] = field(default_factory=list)
    background: bool = True
