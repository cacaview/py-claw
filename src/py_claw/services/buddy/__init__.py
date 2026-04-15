"""
Buddy/Companion ASCII sprite service.

Deterministic companion generation with species, rarities, and ASCII rendering.
"""
from __future__ import annotations

from py_claw.services.buddy.types import (
    RARITIES,
    RARITY_STARS,
    RARITY_WEIGHTS,
    SPECIES,
    EYES,
    HATS,
    STAT_NAMES,
    Companion,
    CompanionBones,
    CompanionSoul,
    StoredCompanion,
    Roll,
    Rarity,
    Species,
    Eye,
    Hat,
    StatName,
)

from py_claw.services.buddy.companion import (
    clear_roll_cache,
    companion_user_id,
    get_companion,
    roll,
    roll_with_seed,
)

from py_claw.services.buddy.sprites import (
    render_sprite,
    render_face,
    sprite_frame_count,
)

from py_claw.services.buddy.prompt import (
    companion_intro_text,
    get_companion_intro_attachment,
)

from py_claw.services.buddy.service import (
    BuddyConfig,
    get_buddy_config,
    set_buddy_config,
    render_companion_sprite,
    render_companion_face,
    get_companion_stats,
    companion_reserved_columns,
)

from py_claw.services.buddy.notification import (
    is_buddy_teaser_window,
    is_buddy_live,
    find_buddy_trigger_positions,
    BuddyNotification,
    NotificationTrigger,
    BuddyNotificationManager,
    get_notification_manager,
    reset_notification_manager,
)

from py_claw.services.buddy.sprite_widget import (
    CompanionSpriteWidget,
    CompanionFloatingBubble,
    SpeechBubble,
    get_companion_display_width,
)

__all__ = [
    # types
    "RARITIES",
    "RARITY_STARS",
    "RARITY_WEIGHTS",
    "SPECIES",
    "EYES",
    "HATS",
    "STAT_NAMES",
    "Companion",
    "CompanionBones",
    "CompanionSoul",
    "StoredCompanion",
    "Roll",
    "Rarity",
    "Species",
    "Eye",
    "Hat",
    "StatName",
    # companion
    "clear_roll_cache",
    "companion_user_id",
    "get_companion",
    "roll",
    "roll_with_seed",
    # sprites
    "render_sprite",
    "render_face",
    "sprite_frame_count",
    # prompt
    "companion_intro_text",
    "get_companion_intro_attachment",
    # service
    "BuddyConfig",
    "get_buddy_config",
    "set_buddy_config",
    "render_companion_sprite",
    "render_companion_face",
    "get_companion_stats",
    "companion_reserved_columns",
    # notification
    "is_buddy_teaser_window",
    "is_buddy_live",
    "find_buddy_trigger_positions",
    "BuddyNotification",
    "NotificationTrigger",
    "BuddyNotificationManager",
    "get_notification_manager",
    "reset_notification_manager",
    # sprite widget
    "CompanionSpriteWidget",
    "CompanionFloatingBubble",
    "SpeechBubble",
    "get_companion_display_width",
]
