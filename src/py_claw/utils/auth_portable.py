"""
Portable auth helpers.

Platform-independent authentication helpers for API key storage
and retrieval across different platforms.

Mirrors TS authPortable.ts behavior.
"""
from __future__ import annotations

import os
import subprocess
import sys


def get_mac_os_keychain_storage_service_name() -> str:
    """
    Get the macOS Keychain service name for API key storage.

    Returns:
        Service name for keychain storage
    """
    return "com.anthropic.claude-code"


def maybe_remove_api_key_from_mac_os_keychain() -> bool:
    """
    Remove API key from macOS Keychain if present.

    Returns:
        True if successfully removed or not present, False on error
    """
    if sys.platform != "darwin":
        return True

    try:
        service_name = get_mac_os_keychain_storage_service_name()
        user = os.environ.get("USER", "")

        result = subprocess.run(
            ["security", "delete-generic-password", "-a", user, "-s", service_name],
            shell=True,
            capture_output=True,
            text=True,
        )

        # Exit code 0 = success, 44 = item not found (also OK)
        return result.returncode == 0 or result.returncode == 44

    except Exception:
        return False


def normalize_api_key_for_config(api_key: str) -> str:
    """
    Normalize an API key for config display.

    Shows only the last 20 characters for security.

    Args:
        api_key: Full API key

    Returns:
        Truncated key for display
    """
    if len(api_key) <= 20:
        return api_key
    return api_key[-20:]
