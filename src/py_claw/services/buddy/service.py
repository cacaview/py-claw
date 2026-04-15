"""
Buddy/Companion service.

Main service for companion management and rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from py_claw.services.buddy.companion import (
    clear_roll_cache,
    companion_user_id,
    get_companion as _get_companion,
    roll,
    roll_with_seed,
)
from py_claw.services.buddy.notification import (
    is_buddy_live,
)
from py_claw.services.buddy.prompt import (
    companion_intro_text,
    get_companion_intro_attachment,
)
from py_claw.services.buddy.sprites import (
    render_face,
    render_sprite,
    sprite_frame_count,
)
from py_claw.services.buddy.types import (
    Companion,
    CompanionBones,
    Roll,
)


@dataclass
class BuddyConfig:
    """Configuration for buddy service."""
    enabled: bool = True
    companion_muted: bool = False


# Module-level config
_buddy_config: BuddyConfig | None = None


def get_buddy_config() -> BuddyConfig:
    """Get buddy configuration."""
    global _buddy_config
    if _buddy_config is None:
        _buddy_config = BuddyConfig()
    return _buddy_config


def set_buddy_config(config: BuddyConfig) -> None:
    """Set buddy configuration."""
    global _buddy_config
    _buddy_config = config


def get_companion(config: dict[str, Any]) -> Companion | None:
    """Get companion from config.

    Args:
        config: Global config dict

    Returns:
        Companion if found in config
    """
    return _get_companion(config)


def render_companion_sprite(
    companion: Companion,
    frame: int = 0,
) -> list[str]:
    """Render companion sprite frames.

    Args:
        companion: The companion
        frame: Animation frame

    Returns:
        List of lines for sprite
    """
    bones = CompanionBones(
        rarity=companion.rarity,
        species=companion.species,
        eye=companion.eye,
        hat=companion.hat,
        shiny=companion.shiny,
        stats=companion.stats,
    )
    return render_sprite(bones, frame)


def render_companion_face(companion: Companion) -> str:
    """Render companion face for narrow terminals.

    Args:
        companion: The companion

    Returns:
        Single-line face string
    """
    bones = CompanionBones(
        rarity=companion.rarity,
        species=companion.species,
        eye=companion.eye,
        hat=companion.hat,
        shiny=companion.shiny,
        stats=companion.stats,
    )
    return render_face(bones)


def get_companion_stats(companion: Companion) -> dict[str, int]:
    """Get companion stats formatted for display.

    Args:
        companion: The companion

    Returns:
        Dict of stat name to value
    """
    return dict(companion.stats)


# Constants for layout calculation
MIN_COLS_FOR_FULL_SPRITE = 100
SPRITE_BODY_WIDTH = 12
NAME_ROW_PAD = 2  # focused state wraps name in spaces: ` name `
SPRITE_PADDING_X = 2
BUBBLE_WIDTH = 36  # SpeechBubble box (34) + tail column


def _string_width(s: str) -> int:
    """Get visual string width (simple approximation)."""
    # Approximate: full-width chars count as 2, ASCII as 1
    width = 0
    for c in s:
        if ord(c) > 127:
            width += 2
        else:
            width += 1
    return width


def companion_reserved_columns(
    terminal_columns: int,
    speaking: bool,
    config: dict[str, Any] | None = None,
) -> int:
    """
    Calculate how many columns the companion sprite reserves.

    In fullscreen the bubble floats over scrollback (no extra width);
    in non-fullscreen it sits inline and needs BUBBLE_WIDTH more.
    Narrow terminals: 0 — REPL stacks the one-liner on its own row.

    Args:
        terminal_columns: Current terminal width
        speaking: Whether companion is currently speaking
        config: Global config dict (optional)

    Returns:
        Number of columns reserved for companion display
    """
    if not is_buddy_live():
        return 0

    companion = get_companion(config or {})
    if not companion or get_buddy_config().companion_muted:
        return 0

    if terminal_columns < MIN_COLS_FOR_FULL_SPRITE:
        return 0

    name_width = _string_width(companion.name)
    bubble = speaking and not _is_fullscreen_active() if speaking else 0
    return max(SPRITE_BODY_WIDTH, name_width + NAME_ROW_PAD) + SPRITE_PADDING_X + bubble


def _is_fullscreen_active() -> bool:
    """Check if fullscreen mode is active (placeholder for now)."""
    # In py-claw context, this would check the UI state
    return False


__all__ = [
    "BuddyConfig",
    "Companion",
    "CompanionBones",
    "Roll",
    "clear_roll_cache",
    "companion_intro_text",
    "companion_reserved_columns",
    "companion_user_id",
    "get_buddy_config",
    "get_companion",
    "get_companion_intro_attachment",
    "render_companion_face",
    "render_companion_sprite",
    "roll",
    "roll_with_seed",
    "set_buddy_config",
    "sprite_frame_count",
]
