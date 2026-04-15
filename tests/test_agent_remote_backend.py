"""Tests for agent remote backend service."""

import pytest

from py_claw.services.agent.remote_backend import (
    RemoteBackendConfig,
    RemoteAgentBackend,
    SSHAgentBackend,
    TmuxAgentBackend,
    create_remote_backend,
)


class TestRemoteBackendConfig:
    """Test RemoteBackendConfig dataclass."""

    def test_defaults(self):
        config = RemoteBackendConfig()
        assert config.backend_type == "tmux"
        assert config.host is None
        assert config.user is None
        assert config.port is None
        assert config.key_file is None
        assert config.tmux_session is None
        assert config.remote_cwd is None
        assert config.python_path == "python"

    def test_with_values(self):
        config = RemoteBackendConfig(
            backend_type="ssh",
            host="example.com",
            user="developer",
            port=2222,
            key_file="/path/to/key",
        )
        assert config.backend_type == "ssh"
        assert config.host == "example.com"
        assert config.user == "developer"
        assert config.port == 2222
        assert config.key_file == "/path/to/key"


class TestCreateRemoteBackend:
    """Test backend factory function."""

    def test_create_tmux_backend(self):
        config = RemoteBackendConfig(backend_type="tmux")
        backend = create_remote_backend(config)
        assert isinstance(backend, TmuxAgentBackend)

    def test_create_ssh_backend(self):
        config = RemoteBackendConfig(backend_type="ssh", host="example.com")
        backend = create_remote_backend(config)
        assert isinstance(backend, SSHAgentBackend)

    def test_invalid_backend_type(self):
        config = RemoteBackendConfig(backend_type="invalid")
        with pytest.raises(ValueError, match="Unsupported backend_type"):
            create_remote_backend(config)


class TestTmuxAgentBackend:
    """Test TmuxAgentBackend class."""

    def test_requires_tmux_type(self):
        config = RemoteBackendConfig(backend_type="ssh")
        with pytest.raises(ValueError, match="backend_type='tmux'"):
            TmuxAgentBackend(config)

    def test_instantiation(self):
        config = RemoteBackendConfig(backend_type="tmux")
        backend = TmuxAgentBackend(config)
        assert backend._config is config
        assert backend._connected is False
        assert backend._tmux_session == ""


class TestSSHAgentBackend:
    """Test SSHAgentBackend class."""

    def test_requires_ssh_type(self):
        config = RemoteBackendConfig(backend_type="tmux")
        with pytest.raises(ValueError, match="backend_type='ssh'"):
            SSHAgentBackend(config)

    def test_instantiation(self):
        config = RemoteBackendConfig(backend_type="ssh", host="example.com")
        backend = SSHAgentBackend(config)
        assert backend._config is config
        assert backend._connected is False

    def test_build_ssh_command_minimal(self):
        config = RemoteBackendConfig(backend_type="ssh", host="example.com")
        backend = SSHAgentBackend(config)
        cmd = backend._build_ssh_command()
        assert "ssh" in cmd
        assert "example.com" in cmd

    def test_build_ssh_command_full(self):
        config = RemoteBackendConfig(
            backend_type="ssh",
            host="example.com",
            user="developer",
            port=2222,
            key_file="/path/to/key",
        )
        backend = SSHAgentBackend(config)
        cmd = backend._build_ssh_command()
        assert "-l" in cmd
        assert "developer" in cmd
        assert "-p" in cmd
        assert "2222" in cmd
        assert "-i" in cmd
        assert "/path/to/key" in cmd


class TestRemoteAgentBackendInterface:
    """Test RemoteAgentBackend interface compliance."""

    def test_close_not_implemented(self):
        """Base class close() should raise NotImplementedError."""
        config = RemoteBackendConfig(backend_type="tmux")
        backend = RemoteAgentBackend(config)
        with pytest.raises(NotImplementedError):
            backend.close()

    def test_send_command_not_implemented(self):
        """Base class _send_command() should raise NotImplementedError."""
        config = RemoteBackendConfig(backend_type="tmux")
        backend = RemoteAgentBackend(config)
        with pytest.raises(NotImplementedError):
            backend._send_command({"type": "test"})

    def test_start_remote_not_implemented(self):
        """Base class _start_remote() should raise NotImplementedError."""
        config = RemoteBackendConfig(backend_type="tmux")
        backend = RemoteAgentBackend(config)
        with pytest.raises(NotImplementedError):
            backend._start_remote(None)

    def test_recv_messages_default(self):
        """Default _recv_messages() returns empty list."""
        config = RemoteBackendConfig(backend_type="tmux")
        backend = RemoteAgentBackend(config)
        assert backend._recv_messages() == []


class TestBackendIntegration:
    """Integration tests for backend factory."""

    def test_tmux_backend_connection_lifecycle(self):
        """Test that tmux backend starts disconnected."""
        config = RemoteBackendConfig(backend_type="tmux")
        backend = create_remote_backend(config)
        assert backend._connected is False

        # close() should work even when not connected
        backend.close()
        assert backend._connected is False

    def test_ssh_backend_connection_lifecycle(self):
        """Test that SSH backend starts disconnected."""
        config = RemoteBackendConfig(backend_type="ssh", host="localhost")
        backend = create_remote_backend(config)
        assert backend._connected is False

        # close() should work even when not connected
        backend.close()
        assert backend._connected is False
