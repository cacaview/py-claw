"""Apple Terminal bell profile detection.

This module provides async detection of whether the Apple Terminal bell
is disabled for the current profile. It uses osascript to query the current
profile and defaults export to check the bell setting.

This is macOS-specific and returns False immediately on non-Darwin platforms.
"""

from __future__ import annotations

import subprocess
import sys


async def is_apple_terminal_bell_disabled() -> bool:
    """Check if Apple Terminal bell is disabled for the current profile.

    Returns:
        True if bell is disabled in the current profile, False otherwise.
        Always returns False on non-macOS or non-Apple_Terminal environments.
    """
    # Only works on macOS
    if sys.platform != "darwin":
        return False

    # Check if we're actually in Apple_Terminal
    term_program = subprocess.env.get("TERM_PROGRAM", "")
    if term_program != "Apple_Terminal":
        return False

    try:
        # Get the current profile name via osascript
        result = await _run_osascript(
            'tell application "Terminal" to name of current settings of front window'
        )
        if result is None:
            return False
        current_profile = result.strip()

        # Export the Terminal plist and parse for bell setting
        bell_disabled = await _check_profile_bell_disabled(current_profile)
        return bell_disabled
    except Exception:
        return False


async def _run_osascript(script: str) -> str | None:
    """Run osascript and return stdout."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


async def _check_profile_bell_disabled(profile_name: str) -> bool:
    """Check if a profile has bell disabled.

    Uses 'defaults export' to get the plist XML, then parses it.
    """
    try:
        # Export the com.apple.Terminal plist
        result = subprocess.run(
            ["defaults", "export", "com.apple.Terminal", "-"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return False

        # Parse the plist XML (lazy import to avoid pulling in heavy deps)
        plist_data = await _parse_plist(result.stdout)
        if plist_data is None:
            return False

        # Look up the profile's Bell setting
        window_settings = plist_data.get("Window Settings", {})
        profile_settings = window_settings.get(profile_name, {})
        return profile_settings.get("Bell") is False
    except Exception:
        return False


async def _parse_plist(xml_content: str) -> dict | None:
    """Parse plist XML content.

    Uses plistlib from the standard library.
    """
    import plistlib

    try:
        # plistlib can parse from bytes
        data = xml_content.encode("utf-8")
        return plistlib.loads(data)
    except Exception:
        return None
