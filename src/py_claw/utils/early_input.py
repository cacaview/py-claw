"""
Early input capture.

Captures terminal input typed before the REPL is fully initialized.
Users often type 'claude' and immediately start typing their prompt,
but those early keystrokes would otherwise be lost during startup.

Mirrors TS earlyInput.ts behavior.

Note: This is a simplified implementation. Full implementation would
require terminal-specific raw mode handling.
"""
from __future__ import annotations

import os
import select
import sys
from threading import Lock


# Buffer for early input characters
_early_input_buffer = ""
_is_capturing = False
_capture_lock = Lock()


def start_capturing_early_input() -> bool:
    """
    Start capturing stdin data early, before the REPL is initialized.

    Should be called as early as possible in the startup sequence.

    Returns:
        True if capture was started, False otherwise
    """
    global _early_input_buffer, _is_capturing

    if not sys.stdin.isatty():
        return False

    if _is_capturing:
        return True

    # Skip in print mode
    if "-p" in sys.argv or "--print" in sys.argv:
        return False

    _is_capturing = True
    _early_input_buffer = ""

    return True


def _process_chunk(s: str) -> None:
    """Process a chunk of input data."""
    global _early_input_buffer

    i = 0
    while i < len(s):
        char = s[i]
        code = ord(char)

        # Ctrl+C (code 3) - stop capturing and exit
        if code == 3:
            stop_capturing_early_input()
            # Note: In real implementation, would call sys.exit(130)
            return

        # Ctrl+D (code 4) - EOF, stop capturing
        if code == 4:
            stop_capturing_early_input()
            return

        # Backspace (code 127 or 8) - remove last character
        if code == 127 or code == 8:
            if len(_early_input_buffer) > 0:
                _early_input_buffer = _early_input_buffer[:-1]
            i += 1
            continue

        # Skip escape sequences (arrow keys, function keys, etc.)
        if code == 27:
            i += 1  # Skip ESC
            # Skip until terminating byte
            while i < len(s) and not (64 <= ord(s[i]) <= 126):
                i += 1
            if i < len(s):
                i += 1  # Skip terminator
            continue

        # Skip other control characters (except tab and newline)
        if code < 32 and code != 9 and code != 10 and code != 13:
            i += 1
            continue

        # Convert carriage return to newline
        if code == 13:
            _early_input_buffer += "\n"
            i += 1
            continue

        # Add printable characters to buffer
        _early_input_buffer += char
        i += 1


def stop_capturing_early_input() -> None:
    """Stop capturing early input."""
    global _is_capturing

    with _capture_lock:
        _is_capturing = False


def consume_early_input() -> str:
    """
    Consume any early input that was captured.

    Returns the captured input and clears the buffer.
    Automatically stops capturing when called.

    Returns:
        The captured early input (may be empty)
    """
    global _early_input_buffer, _is_capturing

    stop_capturing_early_input()
    input_text = _early_input_buffer.strip()
    _early_input_buffer = ""

    return input_text


def has_early_input() -> bool:
    """
    Check if there is any early input available without consuming it.

    Returns:
        True if early input is available
    """
    return len(_early_input_buffer.strip()) > 0


def seed_early_input(text: str) -> None:
    """
    Seed the early input buffer with text.

    This text will appear pre-filled when the REPL renders.

    Args:
        text: Text to seed the buffer with
    """
    global _early_input_buffer
    _early_input_buffer = text


def is_capturing_early_input() -> bool:
    """Check if early input capture is currently active."""
    return _is_capturing


def try_read_early_input() -> None:
    """
    Try to read any available early input from stdin.

    Non-blocking - only reads if data is available.
    """
    if not _is_capturing or not sys.stdin.isatty():
        return

    try:
        # Use select to check if input is available (Unix only)
        if sys.platform != "win32":
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                chunk = os.read(sys.stdin.fileno(), 4096)
                if chunk:
                    _process_chunk(chunk.decode("utf-8", errors="replace"))
    except Exception:
        pass  # Ignore errors in early input capture
