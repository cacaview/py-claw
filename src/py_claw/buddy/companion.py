"""Companion deterministic roll and generation.

Uses mulberry32 PRNG seeded with user ID hash + salt for
deterministic companion appearance generation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from py_claw.buddy.types import (
    EYES,
    HATS,
    RARITIES,
    RARITY_FLOOR,
    RARITY_WEIGHTS,
    SPECIES,
    STAT_NAMES,
    Companion,
    CompanionBones,
    CompanionSoul,
    Rarity,
    Species,
    StatName,
)

# Fixed salt for deterministic generation
COMPANION_SALT = "friend-2026-401"


def mulberry32(seed: int) -> callable:
    """Create a mulberry32 PRNG with the given seed.

    Mulberry32 is a fast, high-quality PRNG suitable for games.

    Args:
        seed: 32-bit unsigned seed value

    Returns:
        Function that returns random floats in [0, 1)
    """
    def prng() -> float:
        nonlocal seed
        seed = (seed + 0x6D2B79F5) & 0xFFFFFFFF
        t = (seed ^ (seed >> 15)) * (1 | seed)
        t = (t + (t ^ (t >> 7))) & 0xFFFFFFFF
        result = ((t + (t ^ (t >> 14))) & 0xFFFFFFFF) >> 0
        return result / 0xFFFFFFFF

    return prng


def hash_string(s: str) -> int:
    """Hash a string to a 32-bit unsigned integer.

    Uses FNV-1a inspired hash for good distribution.

    Args:
        s: String to hash

    Returns:
        32-bit unsigned hash value
    """
    h = 2166136261
    for byte in s.encode("utf-8"):
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def pick[T](rng: callable, arr: tuple[T, ...]) -> T:
    """Pick a random element from an array using the given RNG.

    Args:
        rng: Random number generator function returning [0, 1)
        arr: Tuple of values to pick from

    Returns:
        Randomly selected element
    """
    return arr[int(rng() * len(arr))]


def roll_rarity(rng: callable) -> Rarity:
    """Roll for companion rarity using weighted probabilities.

    Args:
        rng: Random number generator

    Returns:
        Rolled rarity tier
    """
    total = sum(RARITY_WEIGHTS.values())
    roll = rng() * total

    cumulative = 0.0
    for rarity in RARITIES:
        cumulative += RARITY_WEIGHTS[rarity]
        if roll < cumulative:
            return rarity

    return "common"


def roll_companion(user_id: str | None = None) -> CompanionBones:
    """Roll a new companion's physical appearance.

    Uses deterministic RNG seeded from user_id + salt.

    Args:
        user_id: User identifier for seeding (uses salt if None)

    Returns:
        CompanionBones with generated appearance
    """
    # Create deterministic seed
    seed_str = f"{user_id or 'anonymous'}:{COMPANION_SALT}"
    base_seed = hash_string(seed_str)
    rng = mulberry32(base_seed)

    # Roll rarity first
    rarity = roll_rarity(rng)

    # Generate appearance components
    species = pick(rng, SPECIES)
    eyes = pick(rng, EYES)
    hat = pick(rng, HATS)

    # Color palette based on species
    species_colors = {
        "duck": (("yellow", "orange"), ("white", "grey")),
        "cat": (("orange", "black"), ("white", "grey")),
        "dog": (("brown", "black"), ("white", "tan")),
        "fox": (("orange", "red"), ("white", "black")),
        "owl": (("brown", "grey"), ("white", "beige")),
        "bunny": (("white", "grey"), ("pink", "brown")),
    }

    primary_options, secondary_options = species_colors.get(species, (("grey", "black"), ("white", "grey")))
    primary_color = pick(rng, primary_options)
    secondary_color = pick(rng, secondary_options)

    return CompanionBones(
        species=species,
        rarity=rarity,
        eyes=eyes,
        hat=hat,
        primary_color=primary_color,
        secondary_color=secondary_color,
        seed=base_seed,
    )


def roll_stats(rng: callable, rarity: Rarity) -> dict[StatName, int]:
    """Roll companion stats based on rarity.

    Stats are weighted toward higher values for rarer companions.

    Args:
        rng: Random number generator
        rarity: Companion rarity tier

    Returns:
        Dictionary of stat names to values
    """
    floor = RARITY_FLOOR.get(rarity, 5)
    max_bonus = 100 - floor

    stats: dict[StatName, int] = {}
    for stat in STAT_NAMES:
        # Higher rarity = higher potential, but still somewhat random
        roll = rng()
        value = int(floor + roll * max_bonus * 0.7 + max_bonus * 0.3)
        stats[stat] = min(100, max(1, value))

    return stats


def companion_user_id(
    account_uuid: str | None = None,
    user_id: str | None = None,
) -> str:
    """Determine the user identifier for companion generation.

    Priority: account_uuid > user_id > 'anon'

    Args:
        account_uuid: OAuth account UUID if available
        user_id: User ID if available

    Returns:
        User identifier string
    """
    if account_uuid:
        return account_uuid
    if user_id:
        return user_id
    return "anon"


def get_companion(
    stored_soul: CompanionSoul | None = None,
    account_uuid: str | None = None,
    user_id: str | None = None,
) -> Companion:
    """Get or generate a complete companion.

    If a stored soul exists, merges it with newly rolled bones.
    Otherwise generates a completely new companion.

    Args:
        stored_soul: Previously saved companion soul (can be None)
        account_uuid: OAuth account UUID for identification
        user_id: User ID for identification

    Returns:
        Complete Companion with bones and soul
    """
    uid = companion_user_id(account_uuid, user_id)
    bones = roll_companion(uid)

    soul = stored_soul or CompanionSoul()

    # If soul has no stats, generate them based on bones rarity
    if soul.stats is None:
        seed = bones.seed
        rng = mulberry32(seed + 1)  # Slightly different seed for stats
        soul.stats = roll_stats(rng, bones.rarity)

    return Companion(bones=bones, soul=soul)
