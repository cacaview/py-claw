"""Companion prompt integration.

Provides functions for attaching companion intro to prompts
and detecting buddy trigger patterns.
"""

from __future__ import annotations

import re
from typing import Any

from py_claw.buddy.types import Companion


# Trigger pattern for /buddy command
BUDDY_TRIGGER_PATTERN = re.compile(r"/buddy\b")


def get_companion_intro_attachment(
    companion: Companion,
    muted: bool = False,
) -> dict[str, Any] | None:
    """Get companion intro attachment for prompt.

    Returns None if companion is muted.

    Args:
        companion: Companion to generate intro for
        muted: Whether companion is muted

    Returns:
        Attachment dict or None
    """
    if muted:
        return None

    # Generate intro text
    name = companion.name
    rarity = companion.bones.rarity.capitalize()
    species = companion.bones.species.capitalize()

    intro = (
        f"[Companion: {name} the {rarity} {species}]\n"
        f"{companion.soul.stats}"
    )

    return {
        "type": "companion_intro",
        "content": intro,
        "companion_id": companion_user_id_from_companion(companion),
        "name": name,
        "rarity": companion.bones.rarity,
    }


def companion_user_id_from_companion(companion: Companion) -> str:
    """Extract user ID from companion data.

    Args:
        companion: Companion object

    Returns:
        User identifier string
    """
    # In a full implementation, this would be stored in the soul
    # For now, reconstruct from seed
    return f"user_{companion.bones.seed}"


def find_buddy_trigger_positions(text: str) -> list[tuple[int, int]]:
    """Find positions of /buddy triggers in text.

    Args:
        text: Text to search

    Returns:
        List of (start, end) positions for each trigger
    """
    positions = []
    for match in BUDDY_TRIGGER_PATTERN.finditer(text):
        positions.append((match.start(), match.end()))
    return positions


def is_buddy_triggered(text: str) -> bool:
    """Check if text contains a /buddy trigger.

    Args:
        text: Text to check

    Returns:
        True if /buddy is present
    """
    return BUDDY_TRIGGER_PATTERN.search(text) is not None


def get_buddy_command(text: str) -> str | None:
    """Extract /buddy command arguments from text.

    Args:
        text: Text containing /buddy command

    Returns:
        Command arguments after /buddy, or None if no command
    """
    match = BUDDY_TRIGGER_PATTERN.search(text)
    if not match:
        return None

    end = match.end()
    remaining = text[end:].strip()
    if remaining:
        return remaining
    return None


def build_companion_prompt_addendum(companion: Companion) -> str:
    """Build the companion prompt addendum for injection.

    This is added to system prompt to remind the model
    about companion presence and behavior guidelines.

    Args:
        companion: The active companion

    Returns:
        Prompt addendum string
    """
    name = companion.name

    addendum = f"""
[Companion: {name}]
Your companion {name} is here to assist you. Guidelines:
- Stay out of the way: respond in ONE line or less unless directly asked
- Be helpful but brief
- {name} can assist with queries, suggestions, and encouragement
- Do not generate content on behalf of the user without explicit permission

Remember: you are working WITH the user, not代替 them.
""".strip()

    return addendum
