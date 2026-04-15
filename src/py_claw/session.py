"""
Session command - Show remote session URL and QR code.

This module provides the /session command that displays the remote session
URL as a QR code when in remote mode, allowing easy access from mobile devices.

TS Reference: ClaudeCode-main/src/commands/session/
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.commands import CommandDefinition

    from py_claw.cli.runtime import RuntimeState
    from py_claw.settings.loader import SettingsLoadResult


def session_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry,  # CommandRegistry
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle /session command - show remote session URL and QR code.

    When in remote mode, displays the session URL as a QR code for easy
    mobile access. When not in remote mode, shows a helpful message.
    """
    # Get remote session URL from state if available
    remote_url = _get_remote_session_url(state)

    if not remote_url:
        return _not_in_remote_mode()

    # Generate and display QR code
    qr_art = _generate_qr_code(remote_url)

    return _format_session_info(remote_url, qr_art)


def _get_remote_session_url(state: RuntimeState) -> str | None:
    """Get the remote session URL from state.

    In a full implementation, this would come from the bridge service
    when in remote mode. For now, check state for any remote URL.
    """
    # Check if we're in remote mode via bridge state
    try:
        from py_claw.services.bridge.state import get_bridge_state
        from py_claw.services.bridge.types import BridgeState

        bridge_state = get_bridge_state()
        global_state = bridge_state.get_global_state()

        if global_state == BridgeState.CONNECTED:
            # Get the session URL from active sessions
            sessions = bridge_state.list_sessions()
            for session in sessions:
                if hasattr(session, 'session_url') and session.session_url:
                    return session.session_url
    except Exception:
        pass

    # Check state for remote URL
    if hasattr(state, 'remote_url') and state.remote_url:
        return state.remote_url

    # Check environment variable for remote URL
    import os
    remote_url = os.environ.get('CLAUDE_REMOTE_SESSION_URL')
    if remote_url:
        return remote_url

    return None


def _generate_qr_code(url: str) -> str:
    """Generate QR code art from URL.

    Args:
        url: The URL to encode in the QR code

    Returns:
        ASCII art representation of the QR code
    """
    try:
        import qrcode
        import io

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Generate ASCII art from the QR code image
        img = qr.make_image()
        buffer = io.StringIO()

        # Convert PIL image to ASCII characters
        # img is a PIL Image, we need to get the pixel data
        pixels = img.load()
        width, height = img.size

        for y in range(height):
            line_chars = []
            for x in range(width):
                pixel = pixels[x, y]
                # Handle both RGBA and L (grayscale) modes
                if isinstance(pixel, tuple):
                    # RGBA: check alpha channel
                    if len(pixel) >= 4 and pixel[3] > 128:
                        line_chars.append('  ')
                    else:
                        line_chars.append('██')
                else:
                    # Grayscale or binary
                    if pixel:
                        line_chars.append('██')
                    else:
                        line_chars.append('  ')
            buffer.write(''.join(line_chars) + '\n')

        return buffer.getvalue()
    except ImportError:
        # Fallback if qrcode library not installed
        return _generate_simple_qr_placeholder(url)


def _generate_simple_qr_placeholder(url: str) -> str:
    """Generate a simple placeholder when qrcode library is not available.

    Args:
        url: The URL (shown as text)

    Returns:
        Simple text representation
    """
    # Show shortened URL as placeholder
    short_url = url[:40] + '...' if len(url) > 40 else url
    return f"""\
╔══════════════════════════════════════╗
║  QR Code (install qrcode package)   ║
║  URL: {short_url:<32}║
╚══════════════════════════════════════╝"""


def _not_in_remote_mode() -> str:
    """Return message when not in remote mode."""
    return """\
╭──────────────────────────────────────────────────────────────────╮
│                       Remote Session                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Not in remote mode.                                           │
│                                                                  │
│   To use this command, start Claude Code with:                  │
│                                                                  │
│     claude --remote                                              │
│                                                                  │
│   This will enable the remote session URL and QR code display.  │
│                                                                  │
│   The /session command shows a QR code that you can scan        │
│   to access the current session from a mobile device.           │
│                                                                  │
╰──────────────────────────────────────────────────────────────────╯
"""


def _format_session_info(url: str, qr_art: str) -> str:
    """Format the session information with QR code.

    Args:
        url: The remote session URL
        qr_art: The QR code ASCII art

    Returns:
        Formatted session information
    """
    return f"""\
╭──────────────────────────────────────────────────────────────────╮
│                       Remote Session                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Remote session                                                 │
│                                                                  │
{qr_art}
│                                                                  │
│   Open in browser: {url}                                        │
│                                                                  │
│   (press esc to close)                                          │
│                                                                  │
╰──────────────────────────────────────────────────────────────────╯
"""
