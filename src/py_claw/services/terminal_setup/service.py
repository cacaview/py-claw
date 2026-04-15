"""
Terminal setup service for configuring terminal keybindings.

Supports VSCode, Cursor, Windsurf, Zed, Alacritty, and native CSI-u
terminals (Kitty, Ghostty, iTerm, WezTerm, Warp).
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess

from .types import TerminalSetupResult, TerminalType

logger = logging.getLogger(__name__)

# Terminals that natively support CSI-u (no setup needed)
NATIVE_CSIU_TERMINALS = {
    "ghostty",
    "kitty",
    "iTerm.app",
    "WezTerm",
    "WarpTerminal",
}

# Keybinding for Shift+Enter newline
CSI_U_KEYBINDS = "\x1b[13;2u"  # Shift+Enter
CSI_U_BINDING_NAME = "shift+enter"


def get_terminal_type() -> TerminalType | None:
    """Detect the current terminal type.

    Returns:
        TerminalType or None if unknown
    """
    system = platform.system()

    # Check environment variables
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()

    # VSCode Remote SSH detection
    vscode_remote = os.environ.get("VSCODE_REMOTE_CONAINER_NAME") or os.environ.get("SSH_CONNECTION")

    if "vscode" in term_program or "vscode" in term:
        if vscode_remote:
            # VSCode Remote SSH - CSI-u not supported
            return TerminalType.VSCODE
        # VSCode local - CSI-u supported in newer versions
        return TerminalType.VSCODE

    if "cursor" in term_program:
        return TerminalType.CURSOR

    if "windsurf" in term_program:
        return TerminalType.WINDSURF

    if "alacritty" in term.lower():
        return TerminalType.ALACRITTY

    if "zed" in term_program or "zed" in term.lower():
        return TerminalType.ZED

    # Check for native CSI-u terminals
    if term in NATIVE_CSIU_TERMINALS:
        return TerminalType.NATIVE_CSIU

    # Check if we can detect other terminals
    if system == "Darwin":
        # Check for iTerm
        iterm = subprocess.run(
            ["defaults", "read", "com.googlecode.iterm2"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if iterm.returncode == 0:
            return TerminalType.NATIVE_CSIU

    return None


def is_vscode_remote_ssh() -> bool:
    """Detect if running in VSCode Remote SSH session.

    Returns:
        True if in VSCode Remote SSH
    """
    return bool(
        os.environ.get("SSH_CONNECTION")
        or os.environ.get("SSH_TTY")
        or os.environ.get("VSCODE_REMOTE_CONAINER_NAME")
    )


def should_offer_setup() -> bool:
    """Check if terminal setup should be offered.

    Returns:
        True if setup is needed for current terminal
    """
    term_type = get_terminal_type()
    if term_type is None:
        return False

    # Native CSI-u terminals don't need setup
    if term_type == TerminalType.NATIVE_CSIU:
        return False

    # VSCode Remote SSH also doesn't support CSI-u
    if term_type == TerminalType.VSCODE and is_vscode_remote_ssh():
        return False

    return True


def is_shift_enter_keybinding_installed() -> bool:
    """Check if Shift+Enter keybinding is installed.

    Returns:
        True if keybinding is installed
    """
    # This would check terminal-specific config files
    # Placeholder implementation
    return False


def has_used_backslash_return() -> bool:
    """Check if user has used backslash return before.

    Returns:
        True if user has used backslash return
    """
    # This would check user preferences
    # Placeholder implementation
    return False


def mark_backslash_return_used() -> None:
    """Mark that user has used backslash return."""
    # This would update user preferences
    pass


async def setup_terminal() -> TerminalSetupResult:
    """Setup terminal for Shift+Enter newline support.

    Returns:
        TerminalSetupResult with setup status
    """
    term_type = get_terminal_type()

    if term_type is None:
        return TerminalSetupResult(
            success=False,
            message="Unknown terminal type. Cannot setup keybindings.",
        )

    if term_type == TerminalType.NATIVE_CSIU:
        return TerminalSetupResult(
            success=True,
            message="Your terminal natively supports Shift+Enter for newlines. No setup needed.",
            terminal_type=term_type,
        )

    # Terminal-specific setup
    results = []

    if term_type == TerminalType.VSCODE:
        results.append("VSCode: Add to keybindings.json:")
        results.append('{ "key": "shift+enter", "command": "type", "args": { "text": "\\n" } }')
        results.append("Or enable: Terminal > Integrated: Allow Shift+Enter")

    elif term_type == TerminalType.CURSOR:
        results.append("Cursor: Add to keybindings.json:")
        results.append('{ "key": "shift+enter", "command": "type", "args": { "text": "\\n" } }')

    elif term_type == TerminalType.ALACRITTY:
        results.append("Alacritty: Add to alacritty.toml:")
        results.append('[hints]')
        results.append('binding = [ "Shift+Enter" ]')

    elif term_type == TerminalType.ZED:
        results.append("Zed: Add to settings.json:")
        results.append('{ "bindings": { "shift-enter": "type", "text": "\\n" } }')

    else:
        return TerminalSetupResult(
            success=False,
            message=f"Terminal type {term_type.value} setup not yet supported.",
            terminal_type=term_type,
        )

    return TerminalSetupResult(
        success=True,
        message="\n".join(results),
        terminal_type=term_type,
    )


def get_terminal_setup_info() -> TerminalSetupResult:
    """Get terminal setup information.

    Returns:
        TerminalSetupResult with status
    """
    term_type = get_terminal_type()

    if term_type is None:
        return TerminalSetupResult(
            success=False,
            message="Could not detect terminal type.",
        )

    if term_type == TerminalType.NATIVE_CSIU:
        return TerminalSetupResult(
            success=True,
            message="Your terminal natively supports CSI-u. Shift+Enter should work.",
            terminal_type=term_type,
        )

    needs_setup = should_offer_setup()

    return TerminalSetupResult(
        success=True,
        message=f"Detected terminal: {term_type.value}. "
        + ("Setup may be needed." if needs_setup else "No setup needed."),
        terminal_type=term_type,
    )
