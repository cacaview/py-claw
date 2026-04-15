"""
Companion generation with deterministic roll.

Based on userId + salt, generates stable companion bones.
"""
from __future__ import annotations

import time
from typing import Any

from py_claw.services.buddy.types import (
    Companion,
    CompanionBones,
    CompanionSoul,
    EYES,
    Eye,
    HATS,
    Hat,
    RARITIES,
    Rarity,
    RARITY_FLOOR,
    RARITY_WEIGHTS,
    Roll,
    SPECIES,
    Species,
    STAT_NAMES,
    StatName,
)

# Fixed salt for deterministic roll
SALT = "friend-2026-401"

# Module-level cache
_roll_cache: dict[str, Roll] = {}


def _mulberry32(seed: int) -> callable:
    """Mulberry32 seeded PRNG."""
    state = [seed & 0xFFFFFFFF]

    def next_random() -> float:
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = (state[0] ^ (state[0] >> 15)) * (1 | state[0])
        t = (t + (t ^ (t >> 7))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return next_random


def _hash_string(s: str) -> int:
    """FNV-1a hash returning uint32."""
    h = 2166136261
    for c in s:
        h ^= ord(c)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _pick(rng: callable, arr: tuple) -> Any:
    """Pick random element from array using rng."""
    return arr[int(rng() * len(arr))]


def _roll_rarity(rng: callable) -> Rarity:
    """Roll for rarity based on weights."""
    total = sum(RARITY_WEIGHTS.values())
    roll = rng() * total
    for rarity in RARITIES:
        roll -= RARITY_WEIGHTS[rarity]
        if roll < 0:
            return rarity
    return "common"


def _roll_stats(rng: callable, rarity: Rarity) -> dict[StatName, int]:
    """Roll companion stats based on rarity."""
    floor = RARITY_FLOOR[rarity]
    all_stats = list(STAT_NAMES)

    # Pick peak stat
    peak = _pick(rng, all_stats)

    # Pick dump stat (different from peak)
    dump = _pick(rng, all_stats)
    while dump == peak:
        dump = _pick(rng, all_stats)

    stats: dict[StatName, int] = {}
    for name in STAT_NAMES:
        if name == peak:
            stats[name] = min(100, floor + 50 + int(rng() * 30))
        elif name == dump:
            stats[name] = max(1, floor - 10 + int(rng() * 15))
        else:
            stats[name] = floor + int(rng() * 40)

    return stats


def _roll_from(rng: callable) -> Roll:
    """Generate a complete roll from RNG."""
    rarity = _roll_rarity(rng)
    shiny = rng() < 0.01

    bones = CompanionBones(
        rarity=rarity,
        species=_pick(rng, SPECIES),
        eye=_pick(rng, EYES),
        hat="none" if rarity == "common" else _pick(rng, HATS),
        shiny=shiny,
        stats=_roll_stats(rng, rarity),
    )
    return Roll(bones=bones, inspiration_seed=int(rng() * 1e9))


def roll(user_id: str) -> Roll:
    """Roll companion for user (deterministic based on userId + salt)."""
    global _roll_cache
    key = user_id + SALT

    if key in _roll_cache:
        return _roll_cache[key]

    seed = _hash_string(key)
    rng = _mulberry32(seed)
    result = _roll_from(rng)
    _roll_cache[key] = result
    return result


def roll_with_seed(seed_str: str) -> Roll:
    """Roll companion with explicit seed string."""
    seed = _hash_string(seed_str)
    rng = _mulberry32(seed)
    return _roll_from(rng)


def companion_user_id(config: dict[str, Any]) -> str:
    """Get the user ID for companion from config.

    Priority: oauthAccount.accountUuid > userID > 'anon'
    """
    oauth_account = config.get("oauthAccount")
    if oauth_account and oauth_account.get("accountUuid"):
        return oauth_account["accountUuid"]
    user_id = config.get("userID")
    if user_id:
        return user_id
    return "anon"


def get_companion(config: dict[str, Any]) -> Companion | None:
    """Get full companion by merging stored soul with fresh bones."""
    stored = config.get("companion")
    if not stored:
        return None

    uid = companion_user_id(config)
    result = roll(uid)

    return Companion(
        name=stored.get("name", "Buddy"),
        personality=stored.get("personality", ""),
        rarity=result.bones.rarity,
        species=result.bones.species,
        eye=result.bones.eye,
        hat=result.bones.hat,
        shiny=result.bones.shiny,
        stats=result.bones.stats,
        hatched_at=stored.get("hatchedAt", int(time.time())),
    )


def clear_roll_cache() -> None:
    """Clear the roll cache (for testing)."""
    global _roll_cache
    _roll_cache = {}
