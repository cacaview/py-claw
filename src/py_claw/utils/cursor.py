"""
Cursor utility for text editing operations.

Provides kill ring management for storing killed (cut) text that can be
yanked (pasted). This implements the Emacs-style kill ring with yank-pop support.

Reference: ClaudeCode-main/src/utils/Cursor.ts (kill ring portion)
"""
from __future__ import annotations

# Maximum size of the kill ring
KILL_RING_MAX_SIZE = 10

# Kill ring storage
_kill_ring: list[str] = []
_kill_ring_index = 0
_last_action_was_kill = False

# Yank tracking for yank-pop (alt-y)
_last_yank_start = 0
_last_yank_length = 0
_last_action_was_yank = False


def push_to_kill_ring(text: str, direction: str = "append") -> None:
    """
    Add text to the kill ring.

    Consecutive kills accumulate in the kill ring until other keys are typed.
    Alt+Y cycles through previous kills after a yank.

    Args:
        text: The text to add to the kill ring
        direction: 'append' to add to end of most recent entry, 'prepend' to add to start
    """
    global _kill_ring, _kill_ring_index, _last_action_was_kill, _last_action_was_yank

    if len(text) == 0:
        return

    if _last_action_was_kill and len(_kill_ring) > 0:
        # Accumulate with the most recent kill
        if direction == "prepend":
            _kill_ring[0] = text + _kill_ring[0]
        else:
            _kill_ring[0] = _kill_ring[0] + text
    else:
        # Add new entry to front of ring
        _kill_ring.insert(0, text)
        if len(_kill_ring) > KILL_RING_MAX_SIZE:
            _kill_ring.pop()

    _last_action_was_kill = True
    # Reset yank state when killing new text
    _last_action_was_yank = False


def get_last_kill() -> str:
    """
    Get the most recently killed text.

    Returns:
        The most recent kill, or empty string if kill ring is empty
    """
    if not _kill_ring:
        return ""
    return _kill_ring[0]


def get_kill_ring_item(index: int) -> str:
    """
    Get an item from the kill ring by index.

    Args:
        index: Index into the kill ring (can be negative)

    Returns:
        The kill ring item at the given index, or empty string if out of range
    """
    if len(_kill_ring) == 0:
        return ""

    # Normalize index to handle negative values and wrapping
    normalized_index = ((index % len(_kill_ring)) + len(_kill_ring)) % len(_kill_ring)
    return _kill_ring[normalized_index]


def get_kill_ring_size() -> int:
    """
    Get the number of items in the kill ring.

    Returns:
        Number of items in the kill ring
    """
    return len(_kill_ring)


def clear_kill_ring() -> None:
    """Clear all items from the kill ring and reset state."""
    global _kill_ring, _kill_ring_index, _last_action_was_kill, _last_action_was_yank
    global _last_yank_start, _last_yank_length

    _kill_ring.clear()
    _kill_ring_index = 0
    _last_action_was_kill = False
    _last_action_was_yank = False
    _last_yank_start = 0
    _last_yank_length = 0


def reset_kill_accumulation() -> None:
    """Reset the kill accumulation flag. Called when non-kill keys are pressed."""
    global _last_action_was_kill
    _last_action_was_kill = False


def record_yank(start: int, length: int) -> None:
    """
    Record the position of a yank for potential yank-pop.

    Args:
        start: Starting position of the yanked text
        length: Length of the yanked text
    """
    global _last_yank_start, _last_yank_length, _last_action_was_yank, _kill_ring_index

    _last_yank_start = start
    _last_yank_length = length
    _last_action_was_yank = True
    _kill_ring_index = 0


def can_yank_pop() -> bool:
    """
    Check if yank-pop is available.

    Yank-pop is available if:
    - The last action was a yank
    - There is more than one item in the kill ring

    Returns:
        True if yank-pop can be performed
    """
    return _last_action_was_yank and len(_kill_ring) > 1


def yank_pop() -> dict | None:
    """
    Perform a yank-pop operation.

    Cycles to the next item in the kill ring and returns it.
    Must be called immediately after a yank.

    Returns:
        Dict with 'text', 'start', 'length' keys, or None if yank-pop not available
    """
    global _kill_ring_index, _last_action_was_yank

    if not _last_action_was_yank or len(_kill_ring) <= 1:
        return None

    # Cycle to next item in kill ring
    _kill_ring_index = (_kill_ring_index + 1) % len(_kill_ring)
    text = _kill_ring[_kill_ring_index]

    return {
        "text": text,
        "start": _last_yank_start,
        "length": _last_yank_length,
    }


def update_yank_length(length: int) -> None:
    """
    Update the recorded yank length.

    Args:
        length: New length of the yanked text
    """
    global _last_yank_length
    _last_yank_length = length


def reset_yank_state() -> None:
    """Reset the yank state. Called when non-yank keys are pressed."""
    global _last_action_was_yank
    _last_action_was_yank = False


def get_yank_position() -> tuple[int, int]:
    """
    Get the recorded yank position.

    Returns:
        Tuple of (start, length) for the last yank
    """
    return (_last_yank_start, _last_yank_length)


# Exported for testing
def _reset_for_testing() -> None:
    """Reset all cursor state for testing."""
    clear_kill_ring()
    reset_kill_accumulation()
    reset_yank_state()
