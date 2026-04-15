"""
IDE detection and management service.

Based on ClaudeCode-main/src/utils/ide.ts
"""
from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from .types import (
    EDITOR_DISPLAY_NAMES,
    IdeConfig,
    IdeKind,
    IdeLockfileInfo,
    IdeType,
    SUPPORTED_IDE_CONFIGS,
    DetectedIDEInfo,
    IDEExtensionInstallationStatus,
    check_port_open,
    is_jetbrains_ide,
    is_vscode_ide,
    to_ide_display_name,
)

logger = logging.getLogger(__name__)

# Environment variable to check for IDE port
SSE_PORT_ENV = "CLAUDE_CODE_SSE_PORT"
WSL_DISTRO_ENV = "WSL_DISTRO_NAME"
IDE_HOST_OVERRIDE_ENV = "CLAUDE_CODE_IDE_HOST_OVERRIDE"
SKIP_VALID_CHECK_ENV = "CLAUDE_CODE_IDE_SKIP_VALID_CHECK"
SKIP_AUTO_INSTALL_ENV = "CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL"


def _get_claude_config_home() -> Path:
    """Get the Claude config home directory."""
    return Path.home() / ".claude"


def _get_ide_lockfile_dir() -> Path:
    """Get the IDE lockfile directory."""
    return _get_claude_config_home() / "ide"


def _get_lockfiles() -> list[Path]:
    """Get sorted IDE lockfiles by modification time (newest first)."""
    lockfile_dir = _get_ide_lockfile_dir()
    if not lockfile_dir.exists():
        return []

    try:
        lockfiles: list[tuple[Path, float]] = []
        for entry in lockfile_dir.iterdir():
            if entry.suffix == ".lock":
                mtime = entry.stat().st_mtime
                lockfiles.append((entry, mtime))
        # Sort by modification time, newest first
        lockfiles.sort(key=lambda x: x[1], reverse=True)
        return [lf[0] for lf in lockfiles]
    except OSError as exc:
        logger.debug("Failed to read IDE lockfile directory: %s", exc)
        return []


def _read_lockfile(path: Path) -> IdeLockfileInfo | None:
    """Read and parse an IDE lockfile."""
    try:
        content = path.read_text(encoding="utf-8")

        # Extract port from filename (e.g., 12345.lock -> 12345)
        filename = path.name
        port_str = filename.replace(".lock", "")
        port = int(port_str)

        try:
            parsed = json.loads(content)
            # New format with JSON
            workspace_folders = parsed.get("workspace_folders", [])
            pid = parsed.get("pid")
            ide_name = parsed.get("ide_name")
            use_web_socket = parsed.get("transport") == "ws"
            running_in_windows = parsed.get("running_in_windows", False)
            auth_token = parsed.get("auth_token")
        except json.JSONDecodeError:
            # Old format - just a list of paths
            workspace_folders = [line.strip() for line in content.split("\n") if line.strip()]
            pid = None
            ide_name = None
            use_web_socket = False
            running_in_windows = False
            auth_token = None

        return IdeLockfileInfo(
            workspace_folders=workspace_folders,
            port=port,
            pid=pid,
            ide_name=ide_name,
            use_web_socket=use_web_socket,
            running_in_windows=running_in_windows,
            auth_token=auth_token,
        )
    except (OSError, ValueError) as exc:
        logger.debug("Failed to read lockfile %s: %s", path, exc)
        return None


def _is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        # On Windows, use taskkill to check if process exists
        if platform.system() == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
            )
            return str(pid) in result.stdout
        else:
            # On Unix, use kill -0
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False
    except PermissionError:
        # Process exists but we don't have permission - treat as running
        return True


def _detect_host_ip(is_ide_running_in_windows: bool, port: int) -> str:
    """Detect the host IP to use for IDE connection."""
    # Check for override
    override = os.environ.get(IDE_HOST_OVERRIDE_ENV)
    if override:
        return override

    # Not on WSL or not Windows IDE - use localhost
    if platform.system() != "Linux" or not is_ide_running_in_windows:
        return "127.0.0.1"

    # On WSL connecting to Windows IDE - need gateway IP
    try:
        result = subprocess.run(
            ["ip", "route", "show"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "default" in line.lower():
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "via" and i + 1 < len(parts):
                            gateway = parts[i + 1]
                            # Verify gateway is reachable on the port
                            if check_port_open(gateway, port):
                                return gateway
    except (OSError, subprocess.SubprocessError):
        pass

    return "127.0.0.1"


def _is_wsl() -> bool:
    """Check if running under WSL."""
    return platform.system() == "Linux" and os.environ.get(WSL_DISTRO_ENV) is not None


def _get_cwd() -> str:
    """Get current working directory, normalized."""
    return os.getcwd().replace("\\", "/")


def _path_matches_cwd(ide_path: str, cwd: str) -> bool:
    """Check if an IDE workspace path matches the current working directory."""
    import os.path

    # Normalize paths for comparison
    ide_path = os.path.normpath(ide_path).replace("\\", "/")
    cwd_norm = os.path.normpath(cwd).replace("\\", "/")

    # Direct match or cwd is inside the IDE path
    return cwd_norm == ide_path or cwd_norm.startswith(ide_path + "/")


async def detect_ides(
    include_invalid: bool = False,
    cwd: str | None = None,
) -> list[DetectedIDEInfo]:
    """Detect available IDEs with running Claude Code extensions.

    Args:
        include_invalid: If True, also return IDEs that don't match the cwd
        cwd: Current working directory (defaults to actual cwd)

    Returns:
        List of detected IDEs
    """
    import asyncio

    detected: list[DetectedIDEInfo] = []

    # Get environment port if set
    sse_port = os.environ.get(SSE_PORT_ENV)
    env_port: int | None = int(sse_port) if sse_port else None

    # Get current working directory
    current_cwd = cwd or _get_cwd()

    # Get lockfiles
    lockfiles = _get_lockfiles()

    for lockfile_path in lockfiles:
        lockfile_info = _read_lockfile(lockfile_path)
        if not lockfile_info:
            continue

        is_valid = False

        # Check if we should skip validation
        skip_check = os.environ.get(SKIP_VALID_CHECK_ENV, "").lower() in ("1", "true", "yes")
        if skip_check:
            is_valid = True
        elif lockfile_info.port == env_port:
            # Port matches environment variable - mark as valid
            is_valid = True
        else:
            # Check if cwd is within workspace folders
            for ide_path in lockfile_info.workspace_folders:
                if not ide_path:
                    continue

                # Handle WSL path conversion
                if _is_wsl() and lockfile_info.running_in_windows:
                    # For WSL, try both original and converted paths
                    if _path_matches_cwd(ide_path, current_cwd):
                        is_valid = True
                        break
                    # Could add WSL path conversion here
                else:
                    if _path_matches_cwd(ide_path, current_cwd):
                        is_valid = True
                        break

        if not is_valid and not include_invalid:
            continue

        # PID ancestry check for non-WSL
        if not _is_wsl() and is_vscode_ide(None):
            # Check if the IDE process is still running
            if lockfile_info.pid and not _is_process_running(lockfile_info.pid):
                if not include_invalid:
                    continue

        # Determine IDE name
        ide_name = lockfile_info.ide_name
        if not ide_name:
            ide_name = "IDE"

        # Get host IP
        host = _detect_host_ip(lockfile_info.running_in_windows, lockfile_info.port)

        # Build URL
        if lockfile_info.use_web_socket:
            url = f"ws://{host}:{lockfile_info.port}"
        else:
            url = f"http://{host}:{lockfile_info.port}/sse"

        detected.append(
            DetectedIDEInfo(
                name=ide_name,
                port=lockfile_info.port,
                workspace_folders=lockfile_info.workspace_folders,
                url=url,
                is_valid=is_valid,
                auth_token=lockfile_info.auth_token,
                ide_running_in_windows=lockfile_info.running_in_windows,
            )
        )

    # If we have an env_port and found exactly one match, return only that
    if not include_invalid and env_port:
        matching = [ide for ide in detected if ide.is_valid and ide.port == env_port]
        if len(matching) == 1:
            return matching

    return detected


async def cleanup_stale_lockfiles() -> None:
    """Clean up stale IDE lockfiles (for processes no longer running or ports not responding)."""
    lockfiles = _get_lockfiles()

    for lockfile_path in lockfiles:
        lockfile_info = _read_lockfile(lockfile_path)
        if not lockfile_info:
            # Can't read lockfile - delete it
            try:
                lockfile_path.unlink()
            except OSError:
                pass
            continue

        host = _detect_host_ip(lockfile_info.running_in_windows, lockfile_info.port)
        should_delete = False

        if lockfile_info.pid:
            # Check if process is still running
            if not _is_process_running(lockfile_info.pid):
                if _is_wsl():
                    # On WSL, also check connection
                    if not check_port_open(host, lockfile_info.port):
                        should_delete = True
                else:
                    should_delete = True
        else:
            # No PID, check if port is responding
            if not check_port_open(host, lockfile_info.port):
                should_delete = True

        if should_delete:
            try:
                lockfile_path.unlink()
            except OSError:
                pass


async def find_available_ide(
    timeout: float = 30.0,
    interval: float = 1.0,
) -> DetectedIDEInfo | None:
    """Find an available IDE with a running extension.

    Polls for IDE detection up to the timeout, returning as soon as exactly
    one IDE is found (for supported built-in terminals).

    Args:
        timeout: Maximum time to wait in seconds
        interval: Time between detection attempts
        cwd: Current working directory

    Returns:
        DetectedIDEInfo if found, None otherwise
    """
    import asyncio
    import time

    # Clean up stale lockfiles first
    await cleanup_stale_lockfiles()

    start_time = time.monotonic()

    while time.monotonic() - start_time < timeout:
        ides = await detect_ides(include_invalid=False)

        # Return IDE if exactly one match
        if len(ides) == 1:
            return ides[0]

        await asyncio.sleep(interval)

    return None


def detect_running_ides() -> list[IdeType]:
    """Detect which IDEs are currently running on the system.

    Returns:
        List of running IDE types
    """
    running: list[IdeType] = []
    system = platform.system()

    try:
        if system == "Darwin":
            # macOS - use ps to detect
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
            )
            output = result.stdout

            for ide_type, config in SUPPORTED_IDE_CONFIGS.items():
                for keyword in config.process_keywords_mac:
                    if keyword in output:
                        running.append(ide_type)
                        break

        elif system == "Windows":
            # Windows - use tasklist
            result = subprocess.run(
                ["tasklist"],
                capture_output=True,
                text=True,
            )
            output = result.stdout.lower()

            for ide_type, config in SUPPORTED_IDE_CONFIGS.items():
                for keyword in config.process_keywords_windows:
                    if keyword.lower() in output:
                        running.append(ide_type)
                        break

        else:
            # Linux - use ps
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
            )
            output = result.stdout.lower()

            for ide_type, config in SUPPORTED_IDE_CONFIGS.items():
                for keyword in config.process_keywords_linux:
                    if keyword.lower() in output:
                        # Special case for VS Code on Linux
                        if ide_type == IdeType.VSCODE:
                            # Avoid false positive from cursor or appcode
                            if "cursor" not in output and "appcode" not in output:
                                running.append(ide_type)
                        else:
                            running.append(ide_type)
                        break

    except subprocess.SubprocessError as exc:
        logger.debug("Failed to detect running IDEs: %s", exc)

    return running


def get_ide_kind(ide_type: IdeType | None) -> IdeKind | None:
    """Get the IDE kind for an IDE type."""
    if ide_type is None:
        return None
    config = SUPPORTED_IDE_CONFIGS.get(ide_type)
    return config.ide_kind if config else None


def is_supported_vscode_terminal() -> bool:
    """Check if terminal is a supported VS Code variant."""
    terminal = os.environ.get("TERM")
    if not terminal:
        return False
    try:
        return is_vscode_ide(IdeType(terminal))
    except ValueError:
        return False


def is_supported_jetbrains_terminal() -> bool:
    """Check if terminal is a supported JetBrains variant."""
    terminal = os.environ.get("TERM")
    if not terminal:
        return False
    try:
        return is_jetbrains_ide(IdeType(terminal))
    except ValueError:
        return False


def is_supported_terminal() -> bool:
    """Check if running in a supported IDE terminal."""
    return (
        is_supported_vscode_terminal()
        or is_supported_jetbrains_terminal()
        or os.environ.get("FORCE_CODE_TERMINAL") is not None
    )


def get_terminal_ide_type() -> IdeType | None:
    """Get the IDE type for the current terminal, if supported."""
    if not is_supported_terminal():
        return None
    terminal = os.environ.get("TERM")
    if not terminal:
        return None
    try:
        return IdeType(terminal)
    except ValueError:
        return None
