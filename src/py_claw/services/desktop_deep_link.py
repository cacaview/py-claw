"""Desktop deep link utilities for Claude Desktop handoff.

Mirrors ClaudeCode-main/src/utils/desktopDeepLink.ts behavior.
"""
from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Literal

# Minimum required desktop version
MIN_DESKTOP_VERSION = "1.1.2396"


def _is_dev_mode() -> bool:
    """Check if running in dev mode."""
    if os.environ.get("NODE_ENV") == "development":
        return True

    # Local builds from build directories are dev mode
    # even with NODE_ENV=production
    paths_to_check = [
        os.environ.get("ARGV_1", ""),
        os.path.dirname(os.path.abspath(__file__)),
    ]
    build_dirs = [
        "/build-ant/",
        "/build-ant-native/",
        "/build-external/",
        "/build-external-native/",
    ]

    return any(
        any(build_dir in p for build_dir in build_dirs)
        for p in paths_to_check
        if p
    )


def _get_platform() -> Literal["darwin", "linux", "win32"]:
    """Get the current platform."""
    return platform.system().lower()  # type: ignore


@dataclass
class DesktopInstallStatus:
    """Desktop install status result."""

    status: Literal["not-installed", "version-too-old", "ready"]
    version: str | None = None


async def is_desktop_installed_async() -> bool:
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

    sys_platform = _get_platform()

    if sys_platform == "darwin":
        return os.path.exists("/Applications/Claude.app")
    elif sys_platform == "linux":
        # Check if xdg-mime can find a handler for claude://
        try:
            result = subprocess.run(
                ["xdg-mime", "query", "default", "x-scheme-handler/claude"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except FileNotFoundError:
            return False
    elif sys_platform == "win32":
        # On Windows, try to query the registry for the protocol handler
        try:
            result = subprocess.run(
                ["reg", "query", "HKEY_CLASSES_ROOT\\claude", "/ve"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    return False


def is_desktop_installed() -> bool:
    """Synchronous version of is_desktop_installed_async."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # Can't use run_in_executor easily, just return False for sync context
        return False
    except RuntimeError:
        # No running loop, we can run the async version
        return asyncio.run(is_desktop_installed_async())


async def get_desktop_version_async() -> str | None:
    """
    Detect the installed Claude Desktop version.

    On macOS, reads CFBundleShortVersionString from the app plist.
    On Windows, finds the highest app-X.Y.Z directory in the Squirrel install.
    Returns None if version cannot be determined.
    """
    sys_platform = _get_platform()

    if sys_platform == "darwin":
        try:
            result = subprocess.run(
                [
                    "defaults",
                    "read",
                    "/Applications/Claude.app/Contents/Info.plist",
                    "CFBundleShortVersionString",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return None
            version = result.stdout.strip()
            return version if version else None
        except FileNotFoundError:
            return None
    elif sys_platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None
        install_dir = os.path.join(local_app_data, "AnthropicClaude")
        try:
            entries = os.listdir(install_dir)
            versions = []
            for entry in entries:
                if entry.startswith("app-"):
                    v = entry[4:]  # Remove 'app-' prefix
                    # Basic semver validation
                    parts = v.split(".")
                    if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                        versions.append(v)
            if versions:
                # Sort and return highest version
                versions.sort(key=lambda x: [int(p) for p in x.split(".")])
                return versions[-1]
        except (OSError, ValueError):
            pass
        return None

    return None


async def get_desktop_install_status_async() -> DesktopInstallStatus:
    """
    Check Desktop install status including version compatibility.
    """
    installed = await is_desktop_installed_async()
    if not installed:
        return DesktopInstallStatus(status="not-installed")

    try:
        version = await get_desktop_version_async()
    except Exception:
        # Best effort — proceed with handoff if version detection fails
        return DesktopInstallStatus(status="ready", version="unknown")

    if version is None:
        # Can't determine version — assume it's ready
        return DesktopInstallStatus(status="ready", version="unknown")

    # Simple version comparison (major.minor.patch)
    def parse_version(v: str) -> tuple[int, ...]:
        return tuple(int(p) for p in v.split(".")[:3] if p.isdigit())

    min_ver = parse_version(MIN_DESKTOP_VERSION)
    cur_ver = parse_version(version)

    if cur_ver < min_ver:
        return DesktopInstallStatus(status="version-too-old", version=version)

    return DesktopInstallStatus(status="ready", version=version)


def get_desktop_install_status() -> DesktopInstallStatus:
    """Synchronous version of get_desktop_install_status_async."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # Fallback for when we can't run async
        return DesktopInstallStatus(status="not-installed")
    except RuntimeError:
        return asyncio.run(get_desktop_install_status_async())


def _build_desktop_deep_link(session_id: str, cwd: str) -> str:
    """
    Build a deep link URL for Claude Desktop to resume a CLI session.

    Format: claude://resume?session={sessionId}&cwd={cwd}
    In dev mode: claude-dev://resume?session={sessionId}&cwd={cwd}
    """
    protocol = "claude-dev" if _is_dev_mode() else "claude"
    url = f"{protocol}://resume?session={session_id}&cwd={cwd}"
    return url


async def open_deep_link_async(deep_link_url: str) -> bool:
    """
    Open a deep link URL using the platform-specific mechanism.

    Returns True if the command succeeded, False otherwise.
    """
    sys_platform = _get_platform()

    if sys_platform == "darwin":
        if _is_dev_mode():
            # Use AppleScript to route the URL to the already-running Electron app
            script = f'tell application "Electron" to open location "{deep_link_url}"'
            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                )
                return result.returncode == 0
            except FileNotFoundError:
                return False
        else:
            try:
                result = subprocess.run(["open", deep_link_url], capture_output=True)
                return result.returncode == 0
            except FileNotFoundError:
                return False
    elif sys_platform == "linux":
        try:
            result = subprocess.run(["xdg-open", deep_link_url], capture_output=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    elif sys_platform == "win32":
        try:
            result = subprocess.run(
                ["cmd", "/c", "start", "", deep_link_url],
                capture_output=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    return False


async def open_current_session_in_desktop_async(
    session_id: str,
    cwd: str,
) -> dict[str, str | bool]:
    """
    Build and open a deep link to resume the current session in Claude Desktop.

    Returns a dict with success status and any error message.
    """
    # Check if Desktop is installed
    installed = await is_desktop_installed_async()
    if not installed:
        return {
            "success": False,
            "error": "Claude Desktop is not installed. Install it from https://claude.ai/download",
        }

    # Build and open the deep link
    deep_link_url = _build_desktop_deep_link(session_id, cwd)
    opened = await open_deep_link_async(deep_link_url)

    if not opened:
        return {
            "success": False,
            "error": "Failed to open Claude Desktop. Please try opening it manually.",
            "deepLinkUrl": deep_link_url,
        }

    return {"success": True, "deepLinkUrl": deep_link_url}


def get_download_url() -> str:
    """Get the download URL for Claude Desktop."""
    sys_platform = _get_platform()

    if sys_platform == "win32":
        return "https://claude.ai/api/desktop/win32/x64/exe/latest/redirect"
    else:
        return "https://claude.ai/api/desktop/darwin/universal/dmg/latest/redirect"
