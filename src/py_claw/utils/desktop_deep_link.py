"""
Desktop deep link utility for Claude Desktop integration.

Handles building deep link URLs for session resume and checking
Claude Desktop installation status.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Optional

# Minimum required Claude Desktop version
MIN_DESKTOP_VERSION = "1.1.2396"


def _is_dev_mode() -> bool:
    """Check if running in dev mode."""
    if os.environ.get("NODE_ENV") == "development":
        return True

    # Local builds from build directories are dev mode
    paths_to_check = [
        os.environ.get("argv_1", ""),
        getattr(os, "exec_path", "") or "",
    ]
    build_dirs = [
        "/build-ant/",
        "/build-ant-native/",
        "/build-external/",
        "/build-external-native/",
    ]

    return any(
        any(build_dir in path for build_dir in build_dirs)
        for path in paths_to_check
        if path
    )


def _get_cwd() -> str:
    """Get current working directory."""
    try:
        return os.getcwd()
    except OSError:
        return ""


def _get_session_id() -> str:
    """Get current session ID from bootstrap state."""
    # Lazy import to avoid circular dependency
    try:
        from py_claw.bootstrap import get_session_id
        return get_session_id()
    except (ImportError, Exception):
        # Fallback: generate a simple session ID
        import uuid
        return str(uuid.uuid4())


def _exec_file_no_throw(cmd: list[str]) -> tuple[int, str]:
    """Execute a command and return exit code and stdout."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _path_exists(path: str) -> bool:
    """Check if a path exists."""
    try:
        return os.path.exists(path)
    except OSError:
        return False


def build_desktop_deep_link(session_id: str) -> str:
    """
    Builds a deep link URL for Claude Desktop to resume a CLI session.

    Format: claude://resume?session={sessionId}&cwd={cwd}
    In dev mode: claude-dev://resume?session={sessionId}&cwd={cwd}
    """
    protocol = "claude-dev" if _is_dev_mode() else "claude"
    url = f"{protocol}://resume?session={session_id}&cwd={_get_cwd()}"
    return url


async def is_desktop_installed() -> bool:
    """
    Check if Claude Desktop app is installed.

    On macOS, checks for /Applications/Claude.app.
    On Linux, checks if xdg-open can handle claude:// protocol.
    On Windows, checks if the protocol handler exists.
    In dev mode, always returns True (assumes dev Desktop is running).
    """
    # In dev mode, assume the dev Desktop app is running
    if _is_dev_mode():
        return True

    platform = os.name

    if platform == "darwin" or os.uname().sysname == "Darwin":
        return _path_exists("/Applications/Claude.app")
    elif platform == "linux" or os.uname().sysname == "Linux":
        # Check if xdg-mime can find a handler for claude://
        code, stdout = _exec_file_no_throw([
            "xdg-mime", "query", "default", "x-scheme-handler/claude",
        ])
        return code == 0 and stdout.strip()
    elif platform == "nt" or os.uname().sysname == "Windows":
        # On Windows, try to query the registry for the protocol handler
        code, _ = _exec_file_no_throw([
            "reg", "query", "HKEY_CLASSES_ROOT\\claude", "/ve",
        ])
        return code == 0

    return False


def _semver_coerce(version: str) -> tuple[int, int, int] | None:
    """Parse a semantic version string into (major, minor, patch)."""
    import re
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        # Try without patch
        match = re.match(r"(\d+)\.(\d+)", version)
        if not match:
            return None
        return (int(match.group(1)), int(match.group(2)), 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _semver_gte(version: tuple[int, int, int], min_version: tuple[int, int, int]) -> bool:
    """Compare two semantic versions."""
    return version >= min_version


async def get_desktop_version() -> str | None:
    """
    Detect the installed Claude Desktop version.

    On macOS, reads CFBundleShortVersionString from the app plist.
    On Windows, finds the highest app-X.Y.Z directory in the Squirrel install.
    Returns None if version cannot be determined.
    """
    import os
    from pathlib import Path

    platform = os.name

    if platform == "darwin" or os.uname().sysname == "Darwin":
        code, stdout = _exec_file_no_throw([
            "defaults", "read",
            "/Applications/Claude.app/Contents/Info.plist",
            "CFBundleShortVersionString",
        ])
        if code != 0:
            return None
        version = stdout.strip()
        return version if version else None

    elif platform == "nt" or os.uname().sysname == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None

        install_dir = Path(local_app_data) / "AnthropicClaude"
        if not install_dir.is_dir():
            return None

        try:
            entries = os.listdir(install_dir)
            versions = []
            for entry in entries:
                if entry.startswith("app-"):
                    version_str = entry[4:]
                    coerced = _semver_coerce(version_str)
                    if coerced is not None:
                        versions.append(coerced)

            if not versions:
                return None

            versions.sort()
            highest = versions[-1]
            return f"{highest[0]}.{highest[1]}.{highest[2]}"
        except OSError:
            return None

    return None


@dataclass
class DesktopInstallStatus:
    """Desktop installation status result."""
    status: Literal["not-installed", "version-too-old", "ready"]
    version: str = "unknown"


async def get_desktop_install_status() -> DesktopInstallStatus:
    """
    Check Desktop install status including version compatibility.
    """
    installed = await is_desktop_installed()
    if not installed:
        return DesktopInstallStatus(status="not-installed")

    try:
        version = await get_desktop_version()
    except Exception:
        # Best effort — proceed with handoff if version detection fails
        return DesktopInstallStatus(status="ready", version="unknown")

    if not version:
        # Can't determine version — assume it's ready
        return DesktopInstallStatus(status="ready", version="unknown")

    coerced = _semver_coerce(version)
    min_version = _semver_coerce(MIN_DESKTOP_VERSION)

    if coerced is None or min_version is None:
        return DesktopInstallStatus(status="ready", version=version)

    if not _semver_gte(coerced, min_version):
        return DesktopInstallStatus(status="version-too-old", version=version)

    return DesktopInstallStatus(status="ready", version=version)


async def _open_deep_link(deep_link_url: str) -> bool:
    """
    Opens a deep link URL using the platform-specific mechanism.
    Returns True if the command succeeded, False otherwise.
    """
    import subprocess

    platform = os.name

    if platform == "darwin" or os.uname().sysname == "Darwin":
        if _is_dev_mode():
            # Use AppleScript to route the URL to the already-running Electron app
            code, _ = _exec_file_no_throw([
                "osascript", "-e",
                f'tell application "Electron" to open location "{deep_link_url}"',
            ])
            return code == 0
        code, _ = _exec_file_no_throw(["open", deep_link_url])
        return code == 0

    elif platform == "linux" or os.uname().sysname == "Linux":
        code, _ = _exec_file_no_throw(["xdg-open", deep_link_url])
        return code == 0

    elif platform == "nt" or os.uname().sysname == "Windows":
        code, _ = _exec_file_no_throw(["cmd", "/c", "start", "", deep_link_url])
        return code == 0

    return False


async def open_current_session_in_desktop() -> dict:
    """
    Build and open a deep link to resume the current session in Claude Desktop.

    Returns:
        dict with success status and any error message or deepLinkUrl
    """
    session_id = _get_session_id()

    # Check if Desktop is installed
    installed = await is_desktop_installed()
    if not installed:
        return {
            "success": False,
            "error": "Claude Desktop is not installed. Install it from https://claude.ai/download",
        }

    # Build and open the deep link
    deep_link_url = build_desktop_deep_link(session_id)
    opened = await _open_deep_link(deep_link_url)

    if not opened:
        return {
            "success": False,
            "error": "Failed to open Claude Desktop. Please try opening it manually.",
            "deepLinkUrl": deep_link_url,
        }

    return {"success": True, "deepLinkUrl": deep_link_url}
