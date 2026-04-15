"""Chrome extension setup and detection.

Re-implements ClaudeCode-main/src/utils/claudeInChrome/setup.ts
"""

from __future__ import annotations

import os
from pathlib import Path

from py_claw.services.chrome.common import (
    CHROME_EXTENSION_URL,
    CHROME_PERMISSIONS_URL,
    CHROME_RECONNECT_URL,
    BROWSER_DETECTION_ORDER,
    CHROMIUM_BROWSERS,
    ChromiumBrowser,
    detect_available_browser,
    get_all_browser_data_paths,
    get_platform,
)


def _is_chrome_extension_installed_in_path(extensions_path: Path) -> bool:
    """Check if the Claude in Chrome extension is installed in a given path.

    The extension ID for production is: fcoeoabgfenejglbffodgkkbkcdhcgfn
    """
    prod_extension_id = "fcoeoabgfenejglbffodgkkbkcdhcgfn"

    # Check for the production extension
    prod_path = extensions_path / prod_extension_id
    if prod_path.exists() and prod_path.is_dir():
        return True

    # Also check in Manifest V3 format (with Version file)
    manifest_path = prod_path / "Manifest.json"
    if manifest_path.exists():
        return True

    return False


def is_chrome_extension_installed() -> bool:
    """Detects if the Claude in Chrome extension is installed.

    Checks the Extensions directory across all supported Chromium-based browsers
    and their profiles.

    Returns True if the extension is installed, False otherwise.
    """
    browser_paths = get_all_browser_data_paths()

    if not browser_paths:
        return False

    for browser_id, data_path in browser_paths:
        # Check default Extensions directory
        extensions_path = data_path / "Extensions"

        if not extensions_path.exists():
            continue

        if _is_chrome_extension_installed_in_path(extensions_path):
            return True

        # Also check profile-specific Extensions directories
        # Chrome stores extensions in profile-specific folders like "Default", "Profile 1", etc.
        try:
            for entry in extensions_path.iterdir():
                if entry.is_dir() and _is_chrome_extension_installed_in_path(entry):
                    return True
        except PermissionError:
            # Skip directories we can't access
            continue

    return False


def should_enable_claude_in_chrome(chrome_flag: bool | None = None) -> bool:
    """Determine if Claude in Chrome should be enabled.

    Args:
        chrome_flag: Explicit CLI flag value (True=enable, False=disable, None=check env/config)

    Returns:
        True if Claude in Chrome should be enabled
    """
    # Check for non-interactive session (e.g., SDK, CI)
    # In Python, we don't have the exact same check, but we can check env vars
    if os.environ.get("CLAUDE_CODE_NON_INTERACTIVE") and chrome_flag is None:
        return False

    # Check CLI flags
    if chrome_flag is True:
        return True
    if chrome_flag is False:
        return False

    # Check environment variable
    enable_cfc = os.environ.get("CLAUDE_CODE_ENABLE_CFC", "").lower()
    if enable_cfc in ("1", "true", "yes"):
        return True
    if enable_cfc in ("0", "false", "no", ""):
        pass  # Fall through to config check
    else:
        # Value is set but not recognized as truthy, disable
        if enable_cfc:
            return False

    # Check default config settings (would need config access in real impl)
    # For now, default to False
    return False


def get_chrome_extension_urls() -> dict[str, str]:
    """Get the URLs used for Chrome extension management."""
    return {
        "install": CHROME_EXTENSION_URL,
        "permissions": CHROME_PERMISSIONS_URL,
        "reconnect": CHROME_RECONNECT_URL,
    }
