"""
Thinkback play service - hidden command to play thinkback animation.

Called by the thinkback skill after generation is complete.
Based on ClaudeCode-main/src/commands/thinkback-play/
"""
from __future__ import annotations

import logging

from py_claw.services.thinkback import find_thinkback_skill_dir, play_animation

from .types import ThinkbackPlayResult

logger = logging.getLogger(__name__)


async def play() -> ThinkbackPlayResult:
    """Play the thinkback animation.

    Returns:
        ThinkbackPlayResult with playback status
    """
    skill_dir = find_thinkback_skill_dir()

    if not skill_dir:
        return ThinkbackPlayResult(
            success=False,
            message="Thinkback plugin not installed. Use /think-back to install it first.",
        )

    result = await play_animation(skill_dir)

    return ThinkbackPlayResult(
        success=result.success,
        message=result.message,
    )
