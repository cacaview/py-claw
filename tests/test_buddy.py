"""
Tests for Buddy/Companion service.
"""
from __future__ import annotations

import pytest

from py_claw.services.buddy.types import (
    RARITIES,
    SPECIES,
    EYES,
    HATS,
    RARITY_WEIGHTS,
    RARITY_STARS,
    Companion,
    CompanionBones,
    CompanionSoul,
)
from py_claw.services.buddy.companion import (
    clear_roll_cache,
    roll,
    roll_with_seed,
    companion_user_id,
    get_companion,
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


class TestTypes:
    """Tests for buddy types."""

    def test_rarities(self) -> None:
        assert "common" in RARITIES
        assert "legendary" in RARITIES
        assert len(RARITIES) == 5

    def test_species(self) -> None:
        assert "duck" in SPECIES
        assert "cat" in SPECIES
        assert "dragon" in SPECIES
        assert len(SPECIES) == 18

    def test_eyes(self) -> None:
        assert "·" in EYES
        assert "@" in EYES
        assert len(EYES) == 6

    def test_hats(self) -> None:
        assert "none" in HATS
        assert "crown" in HATS
        assert "wizard" in HATS

    def test_rarity_weights(self) -> None:
        assert RARITY_WEIGHTS["common"] == 60
        assert RARITY_WEIGHTS["legendary"] == 1
        assert sum(RARITY_WEIGHTS.values()) == 100

    def test_rarity_stars(self) -> None:
        assert RARITY_STARS["common"] == "★"
        assert RARITY_STARS["legendary"] == "★★★★★"


class TestCompanionRoll:
    """Tests for companion roll."""

    def test_roll_deterministic(self) -> None:
        """Same user_id should produce same roll."""
        clear_roll_cache()
        result1 = roll("user123")
        result2 = roll("user123")
        assert result1.bones.species == result2.bones.species
        assert result1.bones.rarity == result2.bones.rarity
        assert result1.inspiration_seed == result2.inspiration_seed

    def test_roll_different_users_different(self) -> None:
        """Different users should likely get different results."""
        clear_roll_cache()
        result1 = roll("user1")
        result2 = roll("user2")
        # Not guaranteed different, but very likely
        # At minimum, inspiration seeds should differ
        assert result1.inspiration_seed != result2.inspiration_seed

    def test_roll_with_seed(self) -> None:
        """Same seed should produce same roll."""
        clear_roll_cache()
        result1 = roll_with_seed("test-seed")
        result2 = roll_with_seed("test-seed")
        assert result1.bones.species == result2.bones.species
        assert result1.bones.rarity == result2.bones.rarity

    def test_roll_rarity_distribution(self) -> None:
        """Roll should respect rarity weights."""
        clear_roll_cache()
        # Roll many times and check we get all rarities
        rarities = set()
        for i in range(100):
            r = roll(f"user_{i}")
            rarities.add(r.bones.rarity)
        # Should get at least common most of the time
        assert "common" in rarities


class TestCompanionUserId:
    """Tests for companion user ID extraction."""

    def test_oauth_account_uuid_priority(self) -> None:
        config = {
            "oauthAccount": {"accountUuid": "uuid-123"},
            "userID": "user-456",
        }
        assert companion_user_id(config) == "uuid-123"

    def test_user_id_fallback(self) -> None:
        config = {"userID": "user-456"}
        assert companion_user_id(config) == "user-456"

    def test_anon_fallback(self) -> None:
        config = {}
        assert companion_user_id(config) == "anon"


class TestGetCompanion:
    """Tests for get_companion."""

    def test_no_companion_in_config(self) -> None:
        clear_roll_cache()
        config = {}
        result = get_companion(config)
        assert result is None

    def test_companion_from_config(self) -> None:
        clear_roll_cache()
        config = {
            "companion": {
                "name": "Buddy",
                "personality": "cheerful",
                "hatchedAt": 1234567890,
            },
            "userID": "test-user",
        }
        result = get_companion(config)
        assert result is not None
        assert result.name == "Buddy"
        assert result.personality == "cheerful"
        assert result.hatched_at == 1234567890


class TestRenderSprite:
    """Tests for sprite rendering."""

    def test_render_duck_sprite(self) -> None:
        bones = CompanionBones(
            rarity="common",
            species="duck",
            eye="·",
            hat="none",
            shiny=False,
            stats={"DEBUGGING": 10, "PATIENCE": 20, "CHAOS": 30, "WISDOM": 40, "SNARK": 50},
        )
        frames = render_sprite(bones, frame=0)
        assert len(frames) > 0
        assert all(isinstance(line, str) for line in frames)

    def test_render_sprite_frames(self) -> None:
        bones = CompanionBones(
            rarity="rare",
            species="cat",
            eye="@",
            hat="crown",
            shiny=False,
            stats={"DEBUGGING": 10, "PATIENCE": 20, "CHAOS": 30, "WISDOM": 40, "SNARK": 50},
        )
        frame0 = render_sprite(bones, frame=0)
        frame1 = render_sprite(bones, frame=1)
        # Different frames should potentially be different
        assert len(frame0) == len(frame1)

    def test_sprite_eye_replacement(self) -> None:
        bones = CompanionBones(
            rarity="common",
            species="duck",
            eye="@",
            hat="none",
            shiny=False,
            stats={"DEBUGGING": 10, "PATIENCE": 20, "CHAOS": 30, "WISDOM": 40, "SNARK": 50},
        )
        frames = render_sprite(bones, frame=0)
        # Should contain the eye character
        eye_char = bones.eye
        assert any(eye_char in line for line in frames)


class TestRenderFace:
    """Tests for face rendering."""

    def test_render_face_duck(self) -> None:
        bones = CompanionBones(
            rarity="common",
            species="duck",
            eye="·",
            hat="none",
            shiny=False,
            stats={"DEBUGGING": 10, "PATIENCE": 20, "CHAOS": 30, "WISDOM": 40, "SNARK": 50},
        )
        face = render_face(bones)
        assert "(" in face
        assert ">" in face

    def test_render_face_cat(self) -> None:
        bones = CompanionBones(
            rarity="common",
            species="cat",
            eye="·",
            hat="none",
            shiny=False,
            stats={"DEBUGGING": 10, "PATIENCE": 20, "CHAOS": 30, "WISDOM": 40, "SNARK": 50},
        )
        face = render_face(bones)
        assert "ω" in face


class TestSpriteFrameCount:
    """Tests for sprite frame count."""

    def test_frame_count_duck(self) -> None:
        count = sprite_frame_count("duck")
        assert count == 3

    def test_frame_count_cat(self) -> None:
        count = sprite_frame_count("cat")
        assert count == 3


class TestCompanionIntro:
    """Tests for companion intro."""

    def test_intro_text(self) -> None:
        text = companion_intro_text("Buddy", "duck")
        assert "Buddy" in text
        assert "duck" in text
        assert "Companion" in text

    def test_intro_attachment_disabled(self) -> None:
        companion = Companion(
            name="Buddy",
            personality="cheerful",
            rarity="common",
            species="duck",
            eye="·",
            hat="none",
            shiny=False,
            stats={"DEBUGGING": 10, "PATIENCE": 20, "CHAOS": 30, "WISDOM": 40, "SNARK": 50},
            hatched_at=1234567890,
        )
        result = get_companion_intro_attachment(
            companion=companion,
            feature_enabled=False,
            companion_muted=False,
        )
        assert len(result) == 0

    def test_intro_attachment_muted(self) -> None:
        companion = Companion(
            name="Buddy",
            personality="cheerful",
            rarity="common",
            species="duck",
            eye="·",
            hat="none",
            shiny=False,
            stats={"DEBUGGING": 10, "PATIENCE": 20, "CHAOS": 30, "WISDOM": 40, "SNARK": 50},
            hatched_at=1234567890,
        )
        result = get_companion_intro_attachment(
            companion=companion,
            feature_enabled=True,
            companion_muted=True,
        )
        assert len(result) == 0

    def test_intro_attachment_enabled(self) -> None:
        companion = Companion(
            name="Buddy",
            personality="cheerful",
            rarity="common",
            species="duck",
            eye="·",
            hat="none",
            shiny=False,
            stats={"DEBUGGING": 10, "PATIENCE": 20, "CHAOS": 30, "WISDOM": 40, "SNARK": 50},
            hatched_at=1234567890,
        )
        result = get_companion_intro_attachment(
            companion=companion,
            feature_enabled=True,
            companion_muted=False,
        )
        assert len(result) == 1
        assert result[0].name == "Buddy"
        assert result[0].species == "duck"
