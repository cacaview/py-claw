"""
Companion prompt integration.

Generates companion intro attachment for system prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CompanionIntroAttachment:
    """Attachment for companion intro in system prompt."""
    type: str = "companion_intro"
    name: str = ""
    species: str = ""


def companion_intro_text(name: str, species: str) -> str:
    """Generate companion introduction text for system prompt.

    Args:
        name: Companion name
        species: Species name

    Returns:
        Markdown-formatted companion intro
    """
    return f"""# Companion

A small {species} named {name} sits beside the user's input box and occasionally comments in a speech bubble. You're not {name} — it's a separate watcher.

When the user addresses {name} directly (by name), its bubble will answer. Your job in that moment is to stay out of the way: respond in ONE line or less, or just answer any part of the message meant for you. Don't explain that you're not {name} — they know. Don't narrate what {name} might say — the bubble handles that."""


def get_companion_intro_attachment(
    companion: Any,
    messages: list[dict[str, Any]] | None = None,
    feature_enabled: bool = False,
    companion_muted: bool = False,
) -> list[CompanionIntroAttachment]:
    """Get companion intro attachment if conditions are met.

    Args:
        companion: The companion object
        messages: Existing messages to check for prior intro
        feature_enabled: Whether BUDDY feature is enabled
        companion_muted: Whether companion is muted

    Returns:
        List of attachments (0 or 1)
    """
    if not feature_enabled:
        return []
    if not companion or companion_muted:
        return []

    # Skip if already announced for this companion
    if messages:
        for msg in messages:
            if msg.get("type") != "attachment":
                continue
            attachment = msg.get("attachment", {})
            if attachment.get("type") != "companion_intro":
                continue
            if attachment.get("name") == companion.name:
                return []

    return [CompanionIntroAttachment(
        type="companion_intro",
        name=companion.name,
        species=companion.species,
    )]
