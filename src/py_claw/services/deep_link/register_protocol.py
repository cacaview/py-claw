"""Protocol registration for deep links."""

from __future__ import annotations

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

DEEP_LINK_PROTOCOL = "claude-cli"


def register_deep_link_protocol() -> bool:
    """
    Register claude-cli:// as a protocol handler.

    Returns True if registration succeeded, False otherwise.
    """
    if sys.platform == "darwin":
        return _register_macos()
    elif sys.platform == "win32":
        return _register_windows()
    elif sys.platform == "linux":
        return _register_linux()
    return False


def unregister_deep_link_protocol() -> bool:
    """
    Unregister claude-cli:// protocol handler.

    Returns True if unregistration succeeded, False otherwise.
    """
    if sys.platform == "darwin":
        return _unregister_macos()
    elif sys.platform == "win32":
        return _unregister_windows()
    elif sys.platform == "linux":
        return _unregister_linux()
    return False


def _register_macos() -> bool:
    """Register protocol on macOS using Launch Services."""
    try:
        # Get the bundle identifier or executable path
        exec_path = sys.executable

        # Use macOS built-in mechanism
        result = subprocess.run(
            [
                "defaults",
                "write",
                "com.apple.LaunchServices",
                "LSHandlerURLScheme",
                "-dict-add",
                DEEP_LINK_PROTOCOL,
                {"LSHandlerURLScheme": {"CFBundleURLName": "com.claude.code", "CFBundleURLSchemes": [DEEP_LINK_PROTOCOL]}},
            ],
            capture_output=True,
        )
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"Failed to register deep link protocol on macOS: {e}")
        return False


def _unregister_macos() -> bool:
    """Unregister protocol on macOS."""
    try:
        subprocess.run(
            ["defaults", "delete", "com.apple.LaunchServices", "LSHandlerURLScheme"],
            capture_output=True,
        )
        return True
    except Exception:
        return False


def _register_windows() -> bool:
    """Register protocol on Windows via registry."""
    try:
        import winreg
    except ImportError:
        return False

    try:
        # Register in HKEY_CURRENT_USER\Software\Classes
        key_path = f"{DEEP_LINK_PROTOCOL}\\shell\\open\\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{DEEP_LINK_PROTOCOL}") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f"URL:{DEEP_LINK_PROTOCOL} Protocol")
            winreg.SetValue(key, "URL Protocol", winreg.REG_SZ, "")
            with winreg.CreateKey(key, "shell\\open\\command") as cmd_key:
                winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{sys.executable}" "%1"')
        return True
    except Exception as e:
        logger.warning(f"Failed to register deep link protocol on Windows: {e}")
        return False


def _unregister_windows() -> bool:
    """Unregister protocol on Windows."""
    try:
        import winreg
    except ImportError:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Classes", 0, winreg.KEY_WRITE):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{DEEP_LINK_PROTOCOL}", 0)
        return True
    except Exception:
        return False


def _register_linux() -> bool:
    """Register protocol on Linux via desktop file."""
    import os
    from pathlib import Path

    desktop_file = Path.home() / ".local" / "share" / "applications" / "claude-code.desktop"

    try:
        desktop_file.parent.mkdir(parents=True, exist_ok=True)

        content = f"""[Desktop Entry]
Type=Application
Name=Claude Code
Exec={sys.executable} --deep-link-origin %u
Terminal=false
MimeType=x-scheme-handler/{DEEP_LINK_PROTOCOL};
"""

        desktop_file.write_text(content)
        return True
    except Exception as e:
        logger.warning(f"Failed to register deep link protocol on Linux: {e}")
        return False


def _unregister_linux() -> bool:
    """Unregister protocol on Linux."""
    from pathlib import Path

    desktop_file = Path.home() / ".local" / "share" / "applications" / "claude-code.desktop"

    try:
        if desktop_file.exists():
            desktop_file.unlink()
        return True
    except Exception:
        return False
