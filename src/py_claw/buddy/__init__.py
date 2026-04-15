"""Buddy companion module for Claude Code.

Provides a deterministic companion system that generates stable companion
appearances based on user ID. Includes ASCII sprite rendering and
prompt integration.
"""

from __future__ import annotations

from py_claw.buddy.companion import (
    COMPANION_SALT,
    Companion,
    CompanionBones,
    CompanionSoul,
    RARITIES,
    Rarity,
    Species,
    StatName,
    companion_user_id,
    get_companion,
    roll_companion,
)
from py_claw.buddy.types import RARITY_COLORS
from py_claw.buddy.prompt import (
    build_companion_prompt_addendum,
    find_buddy_trigger_positions,
    get_buddy_command,
    get_companion_intro_attachment,
)
from py_claw.buddy.sprites import (
    render_face,
    render_sprite,
    sprite_frame_count,
)

__all__ = [
    # Types
    "Rarity",
    "Species",
    "StatName",
    "CompanionBones",
    "CompanionSoul",
    "Companion",
    "RARITIES",
    "RARITY_COLORS",
    # Constants
    "COMPANION_SALT",
    # Functions
    "companion_user_id",
    "roll_companion",
    "get_companion",
    "get_companion_intro_attachment",
    "render_sprite",
    "render_face",
    "sprite_frame_count",
    "find_buddy_trigger_positions",
    "get_buddy_command",
    "build_companion_prompt_addendum",
]
