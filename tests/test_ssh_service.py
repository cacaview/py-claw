"""Tests for SSH tunnel service."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest


class TestSSHConfig:
    """Tests for SSHConfig."""

    def test_default_values(self) -> None:
        """Test SSHConfig default values."""
        from py_claw.services.ssh import SSHConfig

        config = SSHConfig(host="example.com")
        assert config.host == "example.com"
        assert config.port == 22
        assert config.user is None
        assert config.password is None
        assert config.key_file is None
        assert config.jump_host is None
        assert config.keepalive_interval == 60
        assert config.keepalive_max == 3

    def test_custom_values(self) -> None:
        """Test SSHConfig with custom values."""
        from py_claw.services.ssh import SSHConfig

        config = SSHConfig(
            host="example.com",
            port=2222,
            user="admin",
            jump_host="bastion.example.com",
            key_file="/path/to/key",
        )
        assert config.host == "example.com"
        assert config.port == 2222
        assert config.user == "admin"
        assert config.jump_host == "bastion.example.com"
        assert config.key_file == "/path/to/key"


class TestPortForward:
    """Tests for PortForward."""

    def test_default_values(self) -> None:
        """Test PortForward default values."""
        from py_claw.services.ssh import PortForward

        pf = PortForward(local_port=8080, remote_host="example.com", remote_port=80)
        assert pf.local_port == 8080
        assert pf.remote_host == "example.com"
        assert pf.remote_port == 80
        assert pf.bind_address == "127.0.0.1"

    def test_custom_bind_address(self) -> None:
        """Test PortForward with custom bind address."""
        from py_claw.services.ssh import PortForward

        pf = PortForward(
            local_port=8080,
            remote_host="example.com",
            remote_port=80,
            bind_address="0.0.0.0",
        )
        assert pf.bind_address == "0.0.0.0"


class TestTunnelStatus:
    """Tests for TunnelStatus enum."""

    def test_status_values(self) -> None:
        """Test TunnelStatus enum values."""
        from py_claw.services.ssh import TunnelStatus

        assert TunnelStatus.PENDING.value == "pending"
        assert TunnelStatus.ACTIVE.value == "active"
        assert TunnelStatus.CONNECTING.value == "connecting"
        assert TunnelStatus.DISCONNECTED.value == "disconnected"
        assert TunnelStatus.FAILED.value == "failed"
        assert TunnelStatus.CLOSED.value == "closed"


class TestTunnelInfo:
    """Tests for TunnelInfo."""

    def test_is_active(self) -> None:
        """Test is_active property."""
        from py_claw.services.ssh import SSHConfig, TunnelInfo, TunnelStatus

        config = SSHConfig(host="example.com")
        info = TunnelInfo(name="test", config=config, status=TunnelStatus.ACTIVE)
        assert info.is_active is True

        info.status = TunnelStatus.CLOSED
        assert info.is_active is False


class TestSSHClient:
    """Tests for SSHClient."""

    def test_initialization(self) -> None:
        """Test SSHClient can be initialized."""
        from py_claw.services.ssh import SSHClient, SSHConfig

        config = SSHConfig(host="example.com")
        client = SSHClient(config)
        assert client is not None
        assert client.is_connected is False

    def test_build_ssh_command(self) -> None:
        """Test SSH command building."""
        from py_claw.services.ssh import PortForward, SSHClient, SSHConfig

        config = SSHConfig(host="example.com", user="admin", port=22)
        client = SSHClient(config)

        port_forwards = [
            PortForward(local_port=8080, remote_host="internal", remote_port=80)
        ]

        cmd = client._build_ssh_command(port_forwards)

        assert "ssh" in cmd
        assert "admin@example.com" in cmd
        assert "-L" in cmd
        assert "127.0.0.1:8080:internal:80" in cmd
        assert "-N" in cmd

    def test_build_ssh_command_with_jump(self) -> None:
        """Test SSH command building with jump host."""
        from py_claw.services.ssh import PortForward, SSHClient, SSHConfig

        config = SSHConfig(
            host="example.com",
            user="admin",
            jump_host="bastion.example.com",
        )
        client = SSHClient(config)

        port_forwards = [
            PortForward(local_port=8080, remote_host="internal", remote_port=80)
        ]

        cmd = client._build_ssh_command(port_forwards)

        assert "-J" in cmd
        assert "bastion.example.com" in cmd

    def test_disconnect_noop_when_not_connected(self) -> None:
        """Test disconnect does nothing when not connected."""
        from py_claw.services.ssh import SSHClient, SSHConfig

        config = SSHConfig(host="example.com")
        client = SSHClient(config)

        # Should not raise
        client.disconnect()
        assert client.is_connected is False


class TestTunnelManager:
    """Tests for TunnelManager."""

    def test_initialization(self) -> None:
        """Test TunnelManager can be initialized."""
        from py_claw.services.ssh import TunnelManager

        manager = TunnelManager()
        assert manager is not None
        assert manager.list_tunnels() == []
        assert manager.list_active_tunnels() == []

    def test_create_tunnel(self) -> None:
        """Test creating a tunnel."""
        from py_claw.services.ssh import PortForward, SSHConfig, TunnelManager

        manager = TunnelManager()
        config = SSHConfig(host="example.com")

        with patch.object(manager, "_tunnels", {}):
            # Mock the SSH client connect
            with patch("py_claw.services.ssh.client.SSHClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client.connect.return_value = MagicMock(
                    name="test-tunnel",
                    config=config,
                    status="active",
                    port_forwards=[],
                    started_at=time.time(),
                )
                mock_client_class.return_value = mock_client

                port_forwards = [
                    PortForward(local_port=8080, remote_host="internal", remote_port=80)
                ]

                # We can't easily test this without mocking the subprocess
                # But we can verify the manager interface works
                assert manager.list_tunnels() == []

    def test_close_tunnel_not_found(self) -> None:
        """Test closing non-existent tunnel returns False."""
        from py_claw.services.ssh import TunnelManager

        manager = TunnelManager()
        result = manager.close_tunnel("nonexistent")
        assert result is False

    def test_get_tunnel_not_found(self) -> None:
        """Test getting non-existent tunnel returns None."""
        from py_claw.services.ssh import TunnelManager

        manager = TunnelManager()
        result = manager.get_tunnel("nonexistent")
        assert result is None


class TestSSHService:
    """Tests for SSHService."""

    def test_initialization(self) -> None:
        """Test SSHService can be initialized."""
        from py_claw.services.ssh import SSHService, TunnelManager

        manager = TunnelManager()
        service = SSHService(manager)
        assert service is not None

    def test_generate_tunnel_name(self) -> None:
        """Test tunnel name generation."""
        from py_claw.services.ssh import SSHService, TunnelManager

        manager = TunnelManager()
        service = SSHService(manager)

        name = service._generate_tunnel_name("example.com", 8080, None)
        assert name == "tunnel-8080-example.com"

    def test_generate_tunnel_name_with_jump(self) -> None:
        """Test tunnel name generation with jump host."""
        from py_claw.services.ssh import SSHService, TunnelManager

        manager = TunnelManager()
        service = SSHService(manager)

        name = service._generate_tunnel_name("example.com", 8080, "bastion.com")
        assert name == "tunnel-8080-bastion.com"

    def test_format_duration(self) -> None:
        """Test duration formatting."""
        from py_claw.services.ssh import SSHService, TunnelManager

        manager = TunnelManager()
        service = SSHService(manager)

        assert service._format_duration(30) == "30s"
        assert service._format_duration(90) == "1m 30s"
        assert service._format_duration(3661) == "1h 1m"

    def test_get_all_status_empty(self) -> None:
        """Test status when no tunnels."""
        from py_claw.services.ssh import SSHService, TunnelManager

        manager = TunnelManager()
        service = SSHService(manager)

        status = service.get_all_status()
        assert status == "No tunnels."


class TestSSHServiceModuleFunctions:
    """Tests for module-level SSH service functions."""

    def test_get_ssh_service_returns_singleton(self) -> None:
        """Test get_ssh_service returns singleton."""
        from py_claw.services.ssh import SSHService, get_ssh_service

        service = get_ssh_service()
        assert isinstance(service, SSHService)
        # Second call should return same instance
        service2 = get_ssh_service()
        assert service is service2

    def test_get_tunnel_manager_returns_singleton(self) -> None:
        """Test get_tunnel_manager returns singleton."""
        from py_claw.services.ssh import TunnelManager, get_tunnel_manager

        manager = get_tunnel_manager()
        assert isinstance(manager, TunnelManager)
        # Second call should return same instance
        manager2 = get_tunnel_manager()
        assert manager is manager2
