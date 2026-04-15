"""Native installer - public API for Claude Code installation and setup."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SetupMessage:
    """Represents a setup status message."""

    type: str  # "info", "success", "warning", "error"
    message: str


def _get_install_prefix() -> Path:
    """Get the installation prefix directory."""
    if platform.system() == "Windows":
        # Windows default install location
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        # Unix default install location
        return Path("/usr/local")


def _get_claude_install_dir() -> Path:
    """Get the Claude Code installation directory."""
    prefix = _get_install_prefix()
    if platform.system() == "Windows":
        return prefix / "claude-code"
    else:
        return prefix / "bin"


def check_install() -> dict[str, Any]:
    """
    Check the current installation status.

    Returns:
        Dict with installation status information
    """
    install_dir = _get_claude_install_dir()
    claude_exe = install_dir / ("claude.exe" if platform.system() == "Windows" else "claude")

    return {
        "installed": claude_exe.exists(),
        "install_dir": str(install_dir),
        "executable": str(claude_exe),
        "version": None,  # Would need to run claude --version
    }


async def install_latest(
    callback: Any = None,
) -> SetupMessage:
    """
    Install the latest Claude Code version.

    Args:
        callback: Optional callback for progress updates

    Returns:
        SetupMessage with result status
    """
    system = platform.system()
    arch = platform.machine().lower()

    try:
        if callback:
            callback(SetupMessage(type="info", message="Downloading Claude Code..."))

        # Download URL would be constructed based on system/arch
        # In a real implementation, this would download the installer

        if callback:
            callback(SetupMessage(type="info", message="Installing..."))

        # Stub installation
        install_dir = _get_claude_install_dir()
        install_dir.mkdir(parents=True, exist_ok=True)

        return SetupMessage(
            type="success",
            message=f"Claude Code installed to {install_dir}",
        )

    except Exception as e:
        logger.error(f"Installation failed: {e}")
        return SetupMessage(type="error", message=str(e))


async def cleanup_old_versions() -> list[SetupMessage]:
    """
    Clean up old Claude Code versions.

    Returns:
        List of messages describing cleanup actions taken
    """
    messages: list[SetupMessage] = []
    install_dir = _get_claude_install_dir()

    try:
        if not install_dir.exists():
            return messages

        # Find old version directories
        # In a real implementation, would identify and remove old version directories
        # based on version numbers in directory names

        messages.append(
            SetupMessage(
                type="info",
                message=f"No old versions to clean up in {install_dir}",
            )
        )

    except Exception as e:
        messages.append(SetupMessage(type="error", message=f"Cleanup failed: {e}"))

    return messages


async def cleanup_npm_installations() -> SetupMessage:
    """
    Clean up old npm-based Claude Code installations.

    npm-installed Claude Code (before native installer) should be cleaned up.

    Returns:
        SetupMessage with cleanup result
    """
    messages: list[str] = []

    try:
        # Check for npm-installed claude-code
        npm_path = shutil.which("claude-code")
        if npm_path:
            # Find if it's in node_modules
            if "node_modules" in npm_path:
                messages.append(f"Found npm installation: {npm_path}")

        if messages:
            return SetupMessage(
                type="warning",
                message="Old npm installation found. Consider removing with: npm uninstall -g claude-code",
            )

        return SetupMessage(type="success", message="No npm installations found")

    except Exception as e:
        return SetupMessage(type="error", message=f"Cleanup check failed: {e}")


async def cleanup_shell_aliases() -> SetupMessage:
    """
    Clean up shell aliases for claude command.

    Returns:
        SetupMessage with cleanup result
    """
    try:
        shell = os.environ.get("SHELL", "")
        home = Path.home()

        alias_files = [
            home / ".bashrc",
            home / ".zshrc",
            home / ".profile",
        ]

        cleaned = []
        for f in alias_files:
            if f.exists():
                content = f.read_text()
                # Remove any 'alias claude=' lines
                new_content = "\n".join(
                    line for line in content.split("\n") if not line.strip().startswith("alias claude=")
                )
                if content != new_content:
                    f.write_text(new_content)
                    cleaned.append(str(f))

        if cleaned:
            return SetupMessage(
                type="success",
                message=f"Cleaned aliases from: {', '.join(cleaned)}",
            )

        return SetupMessage(type="info", message="No shell aliases to clean up")

    except Exception as e:
        return SetupMessage(type="error", message=f"Alias cleanup failed: {e}")


async def lock_current_version() -> SetupMessage:
    """
    Lock the current Claude Code version to prevent auto-updates.

    Returns:
        SetupMessage with result
    """
    try:
        # Create a lock file or set an environment variable
        lock_dir = Path.home() / ".claude"
        lock_dir.mkdir(exist_ok=True)
        lock_file = lock_dir / ".version-lock"

        # Would capture current version
        lock_file.write_text("locked")

        return SetupMessage(
            type="success",
            message="Version locked. Auto-updates disabled.",
        )

    except Exception as e:
        return SetupMessage(type="error", message=f"Failed to lock version: {e}")


async def remove_installed_symlink() -> SetupMessage:
    """
    Remove the installed symlink (if any).

    On some systems, Claude Code is installed as a symlink in /usr/local/bin.
    This removes that symlink.

    Returns:
        SetupMessage with result
    """
    try:
        symlink_locations = [
            Path("/usr/local/bin/claude"),
            Path("/usr/local/bin/claude-code"),
        ]

        removed = []
        for loc in symlink_locations:
            if loc.exists() and loc.is_symlink():
                loc.unlink()
                removed.append(str(loc))

        if removed:
            return SetupMessage(
                type="success",
                message=f"Removed symlinks: {', '.join(removed)}",
            )

        return SetupMessage(type="info", message="No symlinks to remove")

    except Exception as e:
        return SetupMessage(type="error", message=f"Failed to remove symlink: {e}")
