"""Buddy companion type definitions.

Defines the data models for the companion system including
Rarity, Species, CompanionBones, CompanionSoul, and Companion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Companion species available
SPECIES: tuple[str, ...] = (
    "duck",
    "cat",
    "dog",
    "fox",
    "owl",
    "bunny",
)

# Ordered from common to legendary
RARITIES: tuple[str, ...] = ("common", "uncommon", "rare", "epic", "legendary")

# Rarity weights for deterministic roll
RARITY_WEIGHTS: dict[Rarity, float] = {
    "common": 50.0,
    "uncommon": 30.0,
    "rare": 12.0,
    "epic": 6.0,
    "legendary": 2.0,
}

# Rarity floor - minimum stat value for each rarity tier
RARITY_FLOOR: dict[Rarity, int] = {
    "common": 5,
    "uncommon": 15,
    "rare": 25,
    "epic": 35,
    "legendary": 50,
}

# Rarity display colors (ANSI)
RARITY_COLORS: dict[Rarity, str] = {
    "common": "\x1b[37m",      # White
    "uncommon": "\x1b[32m",     # Green
    "rare": "\x1b[34m",        # Blue
    "epic": "\x1b[35m",        # Magenta
    "legendary": "\x1b[33m",   # Yellow/Gold
}

RARITY_COLOR_RESET = "\x1b[0m"

# Stat names
STAT_NAMES: tuple[str, ...] = (
    "friendliness",
    "playfulness",
    "wisdom",
    "courage",
    "appetite",
)

# Companion eye types
EYES: tuple[str, ...] = (
    "happy",
    "sleepy",
    "excited",
    "curious",
    "cool",
)

# Companion hat types
HATS: tuple[str, ...] = (
    "none",
    "party",
    "top",
    "crown",
    "wizard",
    "cap",
)


# Type aliases
Rarity = str  # One of RARITIES
Species = str  # One of SPECIES
StatName = str  # One of STAT_NAMES


@dataclass
class CompanionBones:
    """Deterministic physical appearance of a companion.

    Generated once per user via deterministic roll based on
    user ID + salt hash.
    """

    species: Species
    rarity: Rarity
    eyes: str  # One of EYES
    hat: str   # One of HATS
    primary_color: str
    secondary_color: str
    seed: int  # The seed used for generation


@dataclass
class CompanionSoul:
    """User-assigned or stored companion identity.

    Can be empty (new user) or loaded from storage.
    """

    name: str | None = None
    stats: dict[StatName, int] | None = None
    nickname: str | None = None


@dataclass
class Companion:
    """Complete companion entity.

    Combines bones (appearance) with soul (identity).
    """

    bones: CompanionBones
    soul: CompanionSoul

    # Computed properties
    @property
    def name(self) -> str:
        """Get companion name or default based on species."""
        if self.soul.name:
            return self.soul.name
        species_names = {
            "duck": "Quackers",
            "cat": "Mittens",
            "dog": "Buddy",
            "fox": "Rusty",
            "owl": "Hootie",
            "bunny": "Thumper",
        }
        return species_names.get(self.bones.species, "Companion")

    @property
    def rarity_color(self) -> str:
        """Get ANSI color code for rarity."""
        return RARITY_COLORS.get(self.bones.rarity, RARITY_COLORS["common"])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "bones": {
                "species": self.bones.species,
                "rarity": self.bones.rarity,
                "eyes": self.bones.eyes,
                "hat": self.bones.hat,
                "primary_color": self.bones.primary_color,
                "secondary_color": self.bones.secondary_color,
                "seed": self.bones.seed,
            },
            "soul": {
                "name": self.soul.name,
                "stats": self.soul.stats,
                "nickname": self.soul.nickname,
            },
            "name": self.name,
        }
