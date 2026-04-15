"""Chrome common utilities for browser detection and URL opening.

Re-implements ClaudeCode-main/src/utils/claudeInChrome/common.ts
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Constants
CLAUDE_IN_CHROME_MCP_SERVER_NAME = "claude-in-chrome"
CHROME_EXTENSION_URL = "https://claude.ai/chrome"
CHROME_PERMISSIONS_URL = "https://clau.de/chrome/permissions"
CHROME_RECONNECT_URL = "https://clau.de/chrome/reconnect"

# Type for Chromium-based browsers
ChromiumBrowser = Literal["chrome", "brave", "arc", "edge", "chromium", "vivaldi", "opera"]


@dataclass(frozen=True, slots=True)
class BrowserConfig:
    """Browser configuration."""

    name: str
    macos_app_name: str
    macos_data_path: list[str]
    macos_native_messaging_path: list[str]
    linux_binaries: list[str]
    linux_data_path: list[str]
    linux_native_messaging_path: list[str]
    windows_data_path: list[str]
    windows_registry_key: str
    windows_use_roaming: bool = False


# Browser configurations
CHROMIUM_BROWSERS: dict[ChromiumBrowser, BrowserConfig] = {
    "chrome": BrowserConfig(
        name="Google Chrome",
        macos_app_name="Google Chrome",
        macos_data_path=["Library", "Application Support", "Google", "Chrome"],
        macos_native_messaging_path=["Library", "Application Support", "Google", "Chrome", "NativeMessagingHosts"],
        linux_binaries=["google-chrome", "google-chrome-stable"],
        linux_data_path=[".config", "google-chrome"],
        linux_native_messaging_path=[".config", "google-chrome", "NativeMessagingHosts"],
        windows_data_path=["Google", "Chrome", "User Data"],
        windows_registry_key=r"HKCU\Software\Google\Chrome\NativeMessagingHosts",
    ),
    "brave": BrowserConfig(
        name="Brave",
        macos_app_name="Brave Browser",
        macos_data_path=["Library", "Application Support", "BraveSoftware", "Brave-Browser"],
        macos_native_messaging_path=["Library", "Application Support", "BraveSoftware", "Brave-Browser", "NativeMessagingHosts"],
        linux_binaries=["brave-browser", "brave"],
        linux_data_path=[".config", "BraveSoftware", "Brave-Browser"],
        linux_native_messaging_path=[".config", "BraveSoftware", "Brave-Browser", "NativeMessagingHosts"],
        windows_data_path=["BraveSoftware", "Brave-Browser", "User Data"],
        windows_registry_key=r"HKCU\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    ),
    "arc": BrowserConfig(
        name="Arc",
        macos_app_name="Arc",
        macos_data_path=["Library", "Application Support", "Arc", "User Data"],
        macos_native_messaging_path=["Library", "Application Support", "Arc", "User Data", "NativeMessagingHosts"],
        linux_binaries=[],
        linux_data_path=[],
        linux_native_messaging_path=[],
        windows_data_path=["Arc", "User Data"],
        windows_registry_key=r"HKCU\Software\ArcBrowser\Arc\NativeMessagingHosts",
    ),
    "edge": BrowserConfig(
        name="Microsoft Edge",
        macos_app_name="Microsoft Edge",
        macos_data_path=["Library", "Application Support", "Microsoft Edge"],
        macos_native_messaging_path=["Library", "Application Support", "Microsoft Edge", "NativeMessagingHosts"],
        linux_binaries=["microsoft-edge", "microsoft-edge-stable"],
        linux_data_path=[".config", "microsoft-edge"],
        linux_native_messaging_path=[".config", "microsoft-edge", "NativeMessagingHosts"],
        windows_data_path=["Microsoft", "Edge", "User Data"],
        windows_registry_key=r"HKCU\Software\Microsoft\Edge\NativeMessagingHosts",
    ),
    "chromium": BrowserConfig(
        name="Chromium",
        macos_app_name="Chromium",
        macos_data_path=["Library", "Application Support", "Chromium"],
        macos_native_messaging_path=["Library", "Application Support", "Chromium", "NativeMessagingHosts"],
        linux_binaries=["chromium", "chromium-browser"],
        linux_data_path=[".config", "chromium"],
        linux_native_messaging_path=[".config", "chromium", "NativeMessagingHosts"],
        windows_data_path=["Chromium", "User Data"],
        windows_registry_key=r"HKCU\Software\Chromium\NativeMessagingHosts",
    ),
    "vivaldi": BrowserConfig(
        name="Vivaldi",
        macos_app_name="Vivaldi",
        macos_data_path=["Library", "Application Support", "Vivaldi"],
        macos_native_messaging_path=["Library", "Application Support", "Vivaldi", "NativeMessagingHosts"],
        linux_binaries=["vivaldi", "vivaldi-stable"],
        linux_data_path=[".config", "vivaldi"],
        linux_native_messaging_path=[".config", "vivaldi", "NativeMessagingHosts"],
        windows_data_path=["Vivaldi", "User Data"],
        windows_registry_key=r"HKCU\Software\Vivaldi\NativeMessagingHosts",
    ),
    "opera": BrowserConfig(
        name="Opera",
        macos_app_name="Opera",
        macos_data_path=["Library", "Application Support", "com.operasoftware.Opera"],
        macos_native_messaging_path=["Library", "Application Support", "com.operasoftware.Opera", "NativeMessagingHosts"],
        linux_binaries=["opera"],
        linux_data_path=[".config", "opera"],
        linux_native_messaging_path=[".config", "opera", "NativeMessagingHosts"],
        windows_data_path=["Opera Software", "Opera Stable"],
        windows_registry_key=r"HKCU\Software\Opera Software\Opera Stable\NativeMessagingHosts",
        windows_use_roaming=True,
    ),
}

# Priority order for browser detection (most common first)
BROWSER_DETECTION_ORDER: list[ChromiumBrowser] = [
    "chrome",
    "brave",
    "arc",
    "edge",
    "chromium",
    "vivaldi",
    "opera",
]


def get_platform() -> Literal["macos", "linux", "windows", "wsl"]:
    """Get the current platform."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "linux":
        # Check if running in WSL
        if "microsoft" in platform.release().lower() or os.environ.get("WSL_DISTRO_NAME"):
            return "wsl"
        return "linux"
    elif system == "windows":
        return "windows"
    else:
        # Default to linux for unknown platforms
        return "linux"


def get_home_dir() -> Path:
    """Get the user's home directory."""
    return Path.home()


def get_all_browser_data_paths() -> list[tuple[ChromiumBrowser, Path]]:
    """Get all browser data paths to check for extension installation."""
    current_platform = get_platform()
    home = get_home_dir()
    paths: list[tuple[ChromiumBrowser, Path]] = []

    for browser_id in BROWSER_DETECTION_ORDER:
        config = CHROMIUM_BROWSERS[browser_id]

        if current_platform == "macos":
            if config.macos_data_path:
                paths.append((browser_id, home.joinpath(*config.macos_data_path)))

        elif current_platform == "linux":
            if config.linux_data_path:
                paths.append((browser_id, home.joinpath(*config.linux_data_path)))

        elif current_platform == "wsl":
            if config.linux_data_path:
                paths.append((browser_id, home.joinpath(*config.linux_data_path)))

        elif current_platform == "windows":
            if config.windows_data_path:
                app_data_base = (
                    Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
                    if config.windows_use_roaming
                    else Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
                )
                paths.append((browser_id, app_data_base.joinpath(*config.windows_data_path)))

    return paths


def _which_binary(binary: str) -> bool:
    """Check if a binary exists in PATH."""
    return subprocess.run(
        ["which", binary],
        capture_output=True,
        check=False,
    ).returncode == 0


def detect_available_browser() -> ChromiumBrowser | None:
    """Detect which browser to use for opening URLs.

    Returns the first available browser, or None if none found.
    """
    current_platform = get_platform()

    for browser_id in BROWSER_DETECTION_ORDER:
        config = CHROMIUM_BROWSERS[browser_id]

        if current_platform == "macos":
            # Check if the .app bundle (a directory) exists
            app_path = Path(f"/Applications/{config.macos_app_name}.app")
            if app_path.exists() and app_path.is_dir():
                return browser_id

        elif current_platform in ("linux", "wsl"):
            # Check if any binary exists
            for binary in config.linux_binaries:
                if _which_binary(binary):
                    return browser_id

        elif current_platform == "windows":
            # Check if data path exists (indicates browser is installed)
            if config.windows_data_path:
                app_data_base = (
                    Path(os.environ.get("APPDATA", get_home_dir() / "AppData" / "Roaming"))
                    if config.windows_use_roaming
                    else Path(os.environ.get("LOCALAPPDATA", get_home_dir() / "AppData" / "Local"))
                )
                data_path = app_data_base.joinpath(*config.windows_data_path)
                if data_path.exists() and data_path.is_dir():
                    return browser_id

    return None


# Cache for username to avoid repeated calls
_username_cache: str | None = None


def _get_username() -> str:
    """Get the current username."""
    global _username_cache
    if _username_cache is not None:
        return _username_cache

    import os

    _username_cache = os.environ.get("USER") or os.environ.get("USERNAME") or "default"
    return _username_cache


def open_in_chrome(url: str) -> bool:
    """Open a URL in the detected Chromium browser.

    Returns True if successful, False otherwise.
    """
    current_platform = get_platform()
    browser = detect_available_browser()

    if not browser:
        return False

    config = CHROMIUM_BROWSERS[browser]

    if current_platform == "macos":
        result = subprocess.run(
            ["open", "-a", config.macos_app_name, url],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    elif current_platform == "windows":
        # Use rundll32 to avoid cmd.exe metacharacter issues
        result = subprocess.run(
            ["rundll32", "url,OpenURL", url],
            capture_output=True,
            check=False,
            shell=True,
        )
        return result.returncode == 0

    elif current_platform in ("linux", "wsl"):
        for binary in config.linux_binaries:
            result = subprocess.run(
                [binary, url],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                return True
        return False

    return False
