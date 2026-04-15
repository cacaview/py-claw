"""
Buddy/Companion types — ASCII sprite companion system.

Based on Claude Code's buddy companion feature with deterministic roll,
species, rarities, and ASCII sprite rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Rarities with weights
RARITIES = ("common", "uncommon", "rare", "epic", "legendary")
Rarity = Literal["common", "uncommon", "rare", "epic", "legendary"]

RARITY_WEIGHTS = {
    "common": 60,
    "uncommon": 25,
    "rare": 10,
    "epic": 4,
    "legendary": 1,
}

RARITY_FLOOR: dict[Rarity, int] = {
    "common": 5,
    "uncommon": 15,
    "rare": 25,
    "epic": 35,
    "legendary": 50,
}

RARITY_STARS = {
    "common": "★",
    "uncommon": "★★",
    "rare": "★★★",
    "epic": "★★★★",
    "legendary": "★★★★★",
}

# Rarity colors for UI (matching Claude Code terminal color palette)
RARITY_COLORS: dict[Rarity, str] = {
    "common": "white",
    "uncommon": "green",
    "rare": "cyan",
    "epic": "magenta",
    "legendary": "yellow",
}

# Species
SPECIES = (
    "duck",
    "goose",
    "blob",
    "cat",
    "dragon",
    "octopus",
    "owl",
    "penguin",
    "turtle",
    "snail",
    "ghost",
    "axolotl",
    "capybara",
    "cactus",
    "robot",
    "rabbit",
    "mushroom",
    "chonk",
)
Species = Literal[
    "duck",
    "goose",
    "blob",
    "cat",
    "dragon",
    "octopus",
    "owl",
    "penguin",
    "turtle",
    "snail",
    "ghost",
    "axolotl",
    "capybara",
    "cactus",
    "robot",
    "rabbit",
    "mushroom",
    "chonk",
]

# Eyes
EYES = ("·", "✦", "×", "◉", "@", "°")
Eye = Literal["·", "✦", "×", "◉", "@", "°"]

# Hats
HATS = (
    "none",
    "crown",
    "tophat",
    "propeller",
    "halo",
    "wizard",
    "beanie",
    "tinyduck",
)
Hat = Literal[
    "none",
    "crown",
    "tophat",
    "propeller",
    "halo",
    "wizard",
    "beanie",
    "tinyduck",
]

# Stat names
STAT_NAMES = ("DEBUGGING", "PATIENCE", "CHAOS", "WISDOM", "SNARK")
StatName = Literal["DEBUGGING", "PATIENCE", "CHAOS", "WISDOM", "SNARK"]


@dataclass
class CompanionBones:
    """Deterministic companion parts derived from hash(userId)."""
    rarity: Rarity
    species: Species
    eye: Eye
    hat: Hat
    shiny: bool
    stats: dict[StatName, int]


@dataclass
class CompanionSoul:
    """Model-generated soul — stored in config after first hatch."""
    name: str
    personality: str


@dataclass
class Companion:
    """Complete companion combining bones and soul."""
    name: str
    personality: str
    rarity: Rarity
    species: Species
    eye: Eye
    hat: Hat
    shiny: bool
    stats: dict[StatName, int]
    hatched_at: int  # Unix timestamp


@dataclass
class StoredCompanion:
    """What actually persists in config.

    Bones are regenerated from hash(userId) on every read
    so species renames don't break stored companions.
    """
    name: str
    personality: str
    hatched_at: int


@dataclass
class Roll:
    """Result of a companion roll."""
    bones: CompanionBones
    inspiration_seed: int
