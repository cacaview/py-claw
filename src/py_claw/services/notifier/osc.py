"""OSC (Operating System Command) escape sequence constants and helpers.

These sequences are used to send terminal-native notifications via:
- iTerm2: OSC 9 (or OSC 9;4 for progress)
- Kitty: OSC 99
- Ghostty: OSC 133
"""

from __future__ import annotations

# ─── Character Constants ─────────────────────────────────────────────────────────

# ESC is the escape character (0x1b)
ESC = "\x1b"
# BEL is the bell character (0x07)
BEL = "\x07"
# ST (String Terminator) is used by some OSC sequences
ST = ESC + "\\"
# SEP separates OSC parameters
SEP = ";"

# ─── OSC Command Numbers ───────────────────────────────────────────────────────

OSC = {
    "SET_TITLE_AND_ICON": 0,
    "SET_ICON": 1,
    "SET_TITLE": 2,
    "HYPERLINK": 8,
    "ITERM2": 9,
    "ITerm2_BADGE": 0,
    "ITerm2_PROGRESS": 4,
    "KITTY": 99,
    "GHOSTTY": 777,
    "CLIPBOARD": 52,
}

# iTerm2 notification subcommands
ITERM2_NOTIFY = 0
ITERM2_BADGE = 2
ITERM2_PROGRESS = 4

# Progress states for iTerm2
PROGRESS_CLEAR = 0
PROGRESS_SET = 1
PROGRESS_ERROR = 2
PROGRESS_INDETERMINATE = 3


# ─── OSC Sequence Builders ──────────────────────────────────────────────────────


def osc(*parts: str | int, terminator: str = BEL) -> str:
    """Build an OSC escape sequence.

    Args:
        *parts: OSC command number followed by parameters
        terminator: String terminator (default BEL)

    Returns:
        Complete OSC escape sequence, e.g. '\\x1b]9;message\\x07'
    """
    return f"{ESC}{SEP.join(str(p) for p in parts)}{terminator}"


def osc_st(*parts: str | int) -> str:
    """Build an OSC sequence with String Terminator (ST) instead of BEL.

    Used by Kitty for sequences that need ST termination.
    """
    return osc(*parts, terminator=ST)


def wrap_for_multiplexer(sequence: str) -> str:
    """Wrap a sequence for tmux/screen DCS passthrough.

    In tmux/screen, DCS sequences must be double-escaped:
    - ESC becomes ESC + P (tmux) or ESC + > (screen) prefix
    - ESC at end becomes ESC + \\
    """
    # For tmux: prefix with ESC + P + sequence + ESC + \\
    # This is the standard DCS passthrough sequence
    return f"{ESC}P{sequence}{ESC}\\"


def iterm2_notification(message: str, title: str | None = None) -> str:
    """Build iTerm2 notification OSC 9 sequence.

    Args:
        message: The notification message body
        title: Optional title prepended to message

    Returns:
        OSC 9 sequence for iTerm2
    """
    display = f"{title}\n\n{message}" if title else message
    return osc(OSC["ITERM2"], f"\n\n{display}")


def iterm2_progress(state: int, percentage: int | None = None) -> str:
    """Build iTerm2 progress OSC 9;4 sequence.

    Args:
        state: Progress state (0=clear, 1=set, 2=error, 3=indeterminate)
        percentage: Optional percentage (0-100)

    Returns:
        OSC 9;4 sequence for iTerm2 progress
    """
    if percentage is not None:
        return osc(OSC["ITERM2"], OSC["ITerm2_PROGRESS"], f"{state}:{percentage}")
    return osc(OSC["ITERM2"], OSC["ITerm2_PROGRESS"], str(state))


def kitty_notification(message: str, title: str, notification_id: int) -> list[str]:
    """Build Kitty notification OSC 99 sequences.

    Returns a list of sequences to send:
    1. Set title (transient)
    2. Set body
    3. Request focus/dismiss

    Args:
        message: Notification body
        title: Notification title
        notification_id: Unique ID for this notification

    Returns:
        List of OSC sequences to write in order
    """
    seqs = [
        # Set title (transient, dismiss after 1s)
        osc_st(OSC["KITTY"], f"i={notification_id}:d=0:p=title", title),
        # Set body
        osc_st(OSC["KITTY"], f"i={notification_id}:p=body", message),
        # Dismiss after 1 second
        osc_st(OSC["KITTY"], f"i={notification_id}:d=1:a=focus", ""),
    ]
    return seqs


def ghostty_notification(message: str, title: str) -> str:
    """Build Ghostty notification OSC 133 sequence.

    Args:
        message: Notification body
        title: Notification title

    Returns:
        OSC 133 notify sequence
    """
    return osc(OSC["GHOSTTY"], "notify", title, message)


def terminal_bell() -> str:
    """Return the terminal bell character."""
    return BEL
