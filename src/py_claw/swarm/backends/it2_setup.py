"""
iTerm2 setup and installation utilities.

Handles detection, installation, and verification of the it2 CLI tool
for iTerm2 split pane support.

Based on ClaudeCode-main/src/utils/swarm/backends/it2Setup.ts
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Package manager types for installing it2
PythonPackageManager = str  # 'uvx' | 'pipx' | 'pip'


@dataclass
class It2InstallResult:
    """Result of attempting to install it2."""
    success: bool
    error: Optional[str] = None
    package_manager: Optional[PythonPackageManager] = None


@dataclass
class It2VerifyResult:
    """Result of verifying it2 setup."""
    success: bool
    error: Optional[str] = None
    needs_python_api_enabled: bool = False


def detect_python_package_manager() -> Optional[PythonPackageManager]:
    """
    Detects which Python package manager is available on the system.

    Checks in order of preference: uvx (uv), pipx, pip.

    Returns:
        The detected package manager, or None if none found
    """
    # Check uv first (preferred for isolated environments)
    if shutil.which("uv"):
        logger.debug("[it2Setup] Found uv (will use uv tool install)")
        return "uvx"

    # Check pipx (good for isolated environments)
    if shutil.which("pipx"):
        logger.debug("[it2Setup] Found pipx package manager")
        return "pipx"

    # Check pip (fallback)
    if shutil.which("pip"):
        logger.debug("[it2Setup] Found pip package manager")
        return "pip"

    # Also check pip3
    if shutil.which("pip3"):
        logger.debug("[it2Setup] Found pip3 package manager")
        return "pip"

    logger.debug("[it2Setup] No Python package manager found")
    return None


def is_it2_cli_available() -> bool:
    """
    Checks if the it2 CLI tool is installed and accessible.

    Returns:
        True if it2 is available
    """
    return shutil.which("it2") is not None


async def install_it2(package_manager: PythonPackageManager) -> It2InstallResult:
    """
    Installs the it2 CLI tool using the detected package manager.

    Args:
        package_manager: The package manager to use for installation

    Returns:
        Result indicating success or failure
    """
    logger.debug(f"[it2Setup] Installing it2 using {package_manager}")

    # Get home directory for installation
    home_dir = os.path.expanduser("~")

    cmd: list[str] = []
    cwd = home_dir

    if package_manager == "uvx":
        # uv tool install it2 installs it globally in isolated env
        cmd = ["uv", "tool", "install", "it2"]
    elif package_manager == "pipx":
        cmd = ["pipx", "install", "it2"]
    elif package_manager == "pip":
        # Use --user to install without sudo
        cmd = ["pip", "install", "--user", "it2"]
        # Try pip3 if pip fails
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=cwd,
            )
            if result.returncode != 0:
                cmd = ["pip3", "install", "--user", "it2"]
        except Exception:
            pass
    else:
        return It2InstallResult(
            success=False,
            error=f"Unknown package manager: {package_manager}",
        )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cwd,
        )

        if result.returncode != 0:
            error = result.stderr or "Unknown installation error"
            logger.error(f"[it2Setup] Failed to install it2: {error}")
            return It2InstallResult(
                success=False,
                error=error,
                package_manager=package_manager,
            )

        logger.debug("[it2Setup] it2 installed successfully")
        return It2InstallResult(
            success=True,
            package_manager=package_manager,
        )
    except subprocess.TimeoutExpired:
        error = "Installation timed out"
        logger.error(f"[it2Setup] Failed to install it2: {error}")
        return It2InstallResult(
            success=False,
            error=error,
            package_manager=package_manager,
        )
    except Exception as e:
        error = str(e)
        logger.error(f"[it2Setup] Failed to install it2: {error}")
        return It2InstallResult(
            success=False,
            error=error,
            package_manager=package_manager,
        )


async def verify_it2_setup() -> It2VerifyResult:
    """
    Verifies that it2 is properly configured and can communicate with iTerm2.

    This tests the Python API connection by running a simple it2 command.

    Returns:
        Result indicating success or the specific failure reason
    """
    logger.debug("[it2Setup] Verifying it2 setup...")

    # First check if it2 is installed
    if not is_it2_cli_available():
        return It2VerifyResult(
            success=False,
            error="it2 CLI is not installed or not in PATH",
        )

    # Try to list sessions - this tests the Python API connection
    try:
        result = subprocess.run(
            ["it2", "session", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            stderr = result.stderr.lower()

            # Check for common Python API errors
            if any(
                keyword in stderr
                for keyword in ["api", "python", "connection refused", "not enabled"]
            ):
                logger.debug("[it2Setup] Python API not enabled in iTerm2")
                return It2VerifyResult(
                    success=False,
                    error="Python API not enabled in iTerm2 preferences",
                    needs_python_api_enabled=True,
                )

            return It2VerifyResult(
                success=False,
                error=result.stderr or "Failed to communicate with iTerm2",
            )

        logger.debug("[it2Setup] it2 setup verified successfully")
        return It2VerifyResult(success=True)

    except subprocess.TimeoutExpired:
        return It2VerifyResult(
            success=False,
            error="Verification timed out",
        )
    except Exception as e:
        logger.debug(f"[it2Setup] Verification failed: {e}")
        return It2VerifyResult(
            success=False,
            error=str(e),
        )


def get_python_api_instructions() -> list[str]:
    """
    Returns instructions for enabling the Python API in iTerm2.

    Returns:
        List of instruction strings
    """
    return [
        "Almost done! Enable the Python API in iTerm2:",
        "",
        "  iTerm2 → Settings → General → Magic → Enable Python API",
        "",
        "After enabling, you may need to restart iTerm2.",
    ]


def is_macos() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"


__all__ = [
    "PythonPackageManager",
    "It2InstallResult",
    "It2VerifyResult",
    "detect_python_package_manager",
    "is_it2_cli_available",
    "install_it2",
    "verify_it2_setup",
    "get_python_api_instructions",
    "is_macos",
]
