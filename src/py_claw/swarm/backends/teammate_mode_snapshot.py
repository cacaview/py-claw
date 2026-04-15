"""
Teammate mode snapshot module.

Captures the teammate mode at session startup. This ensures that runtime
config changes don't affect the teammate mode for the current session.

Based on ClaudeCode-main/src/utils/swarm/backends/teammateModeSnapshot.ts
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Teammate mode type
TeammateMode = str  # 'auto' | 'tmux' | 'in-process'

# Module-level variable to hold the captured mode at startup
_initial_teammate_mode: Optional[TeammateMode] = None

# CLI override (set before capture if --teammate-mode is provided)
_cli_teammate_mode_override: Optional[TeammateMode] = None


def set_cli_teammate_mode_override(mode: TeammateMode) -> None:
    """
    Set the CLI override for teammate mode.

    Must be called before capture_teammate_mode_snapshot().

    Args:
        mode: The mode to set ('auto', 'tmux', or 'in-process')
    """
    global _cli_teammate_mode_override
    _cli_teammate_mode_override = mode


def get_cli_teammate_mode_override() -> Optional[TeammateMode]:
    """
    Get the current CLI override, if any.

    Returns:
        The CLI override mode, or None if not set
    """
    return _cli_teammate_mode_override


def clear_cli_teammate_mode_override(new_mode: TeammateMode) -> None:
    """
    Clear the CLI override and update the snapshot to the new mode.

    Called when user changes the setting in the UI, allowing their change
    to take effect.

    Args:
        new_mode: The new mode the user selected
    """
    global _cli_teammate_mode_override, _initial_teammate_mode
    _cli_teammate_mode_override = None
    _initial_teammate_mode = new_mode
    logger.debug(f"[TeammateModeSnapshot] CLI override cleared, new mode: {new_mode}")


def capture_teammate_mode_snapshot() -> None:
    """
    Capture the teammate mode at session startup.

    Called early in startup, after CLI args are parsed.
    CLI override takes precedence over config.
    """
    global _initial_teammate_mode

    if _cli_teammate_mode_override:
        _initial_teammate_mode = _cli_teammate_mode_override
        logger.debug(f"[TeammateModeSnapshot] Captured from CLI override: {_initial_teammate_mode}")
    else:
        # Try to get from global config
        config = _get_global_config()
        _initial_teammate_mode = config.get("teammate_mode", "auto")
        logger.debug(f"[TeammateModeSnapshot] Captured from config: {_initial_teammate_mode}")


def get_teammate_mode_from_snapshot() -> TeammateMode:
    """
    Get the teammate mode for this session.

    Returns the snapshot captured at startup, ignoring any runtime config changes.

    Returns:
        The captured teammate mode
    """
    global _initial_teammate_mode

    if _initial_teammate_mode is None:
        # This indicates an initialization bug - capture should happen in setup()
        logger.error(
            "[TeammateModeSnapshot] getTeammateModeFromSnapshot called before capture - "
            "this indicates an initialization bug"
        )
        capture_teammate_mode_snapshot()

    # Fallback to 'auto' if somehow still null (shouldn't happen, but safe)
    return _initial_teammate_mode or "auto"


def _get_global_config() -> dict:
    """
    Get the global config.

    This is a placeholder - in a full implementation, this would read
    from the global config store.

    Returns:
        Config dict
    """
    # In Python implementation, we'd get this from settings or config
    # For now, check environment variable as fallback
    return {
        "teammate_mode": os.environ.get("CLAUDE_TEAMMATE_MODE", "auto"),
    }


__all__ = [
    "TeammateMode",
    "set_cli_teammate_mode_override",
    "get_cli_teammate_mode_override",
    "clear_cli_teammate_mode_override",
    "capture_teammate_mode_snapshot",
    "get_teammate_mode_from_snapshot",
]
