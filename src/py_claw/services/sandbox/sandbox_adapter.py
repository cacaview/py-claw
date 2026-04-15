"""Sandbox adapter - Claude CLI-specific sandbox integration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

# Sandbox enabled state (initialized lazily)
_initialized: bool = False
_enabled: bool = False


@dataclass
class SandboxRuntimeConfig:
    """Configuration for sandbox runtime."""

    network: dict[str, Any] = field(default_factory=dict)
    filesystem: dict[str, Any] = field(default_factory=dict)
    ignore_violations: bool = False
    enable_weaker_nested_sandbox: bool = False
    enable_weaker_network_isolation: bool = False
    ripgrep: dict[str, Any] | None = None


@dataclass
class SandboxViolationEvent:
    """Event representing a sandbox violation."""

    violation_type: str
    message: str
    timestamp: float
    command: str | None = None


@dataclass
class SandboxDependencyCheck:
    """Result of sandbox dependency check."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def is_supported_platform() -> bool:
    """Check if the current platform supports sandboxing."""
    # Simplified check - full impl would check for bubblewrap/socat on Linux
    return os.name == "posix" or os.name == "nt"


def is_sandboxing_enabled() -> bool:
    """
    Check if sandboxing is enabled.

    Checks user's enabled setting, platform support, and enabledPlatforms restriction.
    """
    if not is_supported_platform():
        return False

    # Check settings for sandbox.enabled
    enabled = os.environ.get("CLAUDE_CODE_SANDBOX_ENABLED", "").lower()
    if enabled in ("false", "0", "no"):
        return False
    if enabled in ("true", "1", "yes"):
        return True

    # Default to False if not explicitly set
    return False


def is_platform_in_enabled_list() -> bool:
    """
    Check if current platform is in the enabledPlatforms list.

    Returns True if no explicit list is set (all platforms allowed).
    """
    # TODO: Implement enabledPlatforms check from settings
    return True


def get_sandbox_unavailable_reason() -> str | None:
    """
    Get human-readable reason if sandbox is configured but unavailable.

    Returns None if sandbox is available or not explicitly enabled.
    """
    if not is_sandboxing_enabled():
        return None

    if not is_supported_platform():
        import platform

        system = platform.system().lower()
        if system == "windows":
            return "sandbox.enabled is set but Windows sandbox is not yet supported"
        return f"sandbox.enabled is set but {system} is not supported"

    return None


def check_dependencies() -> SandboxDependencyCheck:
    """
    Check if required sandbox dependencies are available.

    On macOS/Linux, checks for bubblewrap and socat.
    """
    result = SandboxDependencyCheck()

    if os.name == "posix":
        import shutil

        # Check for bubblewrap (Linux)
        if platform.system().lower() == "linux":
            if not shutil.which("bubblewrap"):
                result.errors.append("bubblewrap not found")

        # Check for socat
        if not shutil.which("socat"):
            result.warnings.append("socat not found")

    return result


def resolve_path_pattern_for_sandbox(pattern: str, source: str = "localSettings") -> str:
    """
    Resolve Claude Code-specific path patterns for sandbox-runtime.

    Patterns:
    - //path -> absolute from root
    - /path -> relative to settings file directory
    - ~/path -> passed through
    - ./path or path -> passed through
    """
    # Handle // prefix - absolute from root
    if pattern.startswith("//"):
        return pattern[1:]

    # Handle / prefix - relative to settings directory
    if pattern.startswith("/") and not pattern.startswith("//"):
        # Would resolve against settings root in full implementation
        return pattern

    # Other patterns pass through
    return pattern


def resolve_sandbox_filesystem_path(pattern: str, source: str = "localSettings") -> str:
    """
    Resolve paths from sandbox.filesystem.* settings.

    Unlike permission rules, these use standard path semantics.
    """
    from pathlib import Path

    # Legacy permission-rule escape: //path -> /path
    if pattern.startswith("//"):
        return pattern[1:]

    # Expand ~ to home directory
    if pattern.startswith("~"):
        return str(Path(pattern).expanduser())

    return pattern


class SandboxManager:
    """
    Claude CLI sandbox manager.

    Wraps sandbox-runtime with Claude-specific features.
    """

    @staticmethod
    async def initialize(sandbox_ask_callback=None) -> None:
        """Initialize the sandbox manager."""
        global _initialized
        _initialized = True

    @staticmethod
    def is_supported_platform() -> bool:
        """Check if platform supports sandboxing."""
        return is_supported_platform()

    @staticmethod
    def is_sandboxing_enabled() -> bool:
        """Check if sandboxing is enabled."""
        return is_sandboxing_enabled()

    @staticmethod
    def get_sandbox_unavailable_reason() -> str | None:
        """Get reason why sandbox is unavailable."""
        return get_sandbox_unavailable_reason()

    @staticmethod
    def check_dependencies() -> SandboxDependencyCheck:
        """Check sandbox dependencies."""
        return check_dependencies()

    @staticmethod
    def get_excluded_commands() -> list[str]:
        """Get list of commands excluded from sandboxing."""
        # TODO: Read from settings
        return []

    @staticmethod
    async def wrap_with_sandbox(
        command: str,
        bin_shell: str | None = None,
        custom_config: dict | None = None,
        abort_signal: Any = None,
    ) -> str:
        """
        Wrap a command with sandbox.

        Returns the command unchanged in this stub implementation.
        """
        return command

    @staticmethod
    def cleanup_after_command() -> None:
        """Clean up after a sandboxed command."""
        pass

    @staticmethod
    def reset() -> None:
        """Reset sandbox state."""
        global _initialized, _enabled
        _initialized = False
        _enabled = False
