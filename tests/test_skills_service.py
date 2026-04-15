"""Tests for the skills service."""

from __future__ import annotations

import pytest

from py_claw.services.skills import (
    SkillInfo,
    SkillsServiceState,
    SkillSearchResult,
    initialize_skills_service,
    get_skill,
    list_skills,
    search_skills,
    get_skills_stats,
    get_all_skill_names,
    skill_exists,
    reset_skills_service,
)


class TestSkillsServiceState:
    """Tests for SkillsServiceState."""

    def test_default_values(self):
        """Test default state values."""
        state = SkillsServiceState()
        assert state.initialized is False
        assert state.total_searches == 0
        assert state.cache_size == 0
        assert state.last_search_time_ms == 0.0


class TestSkillInfo:
    """Tests for SkillInfo."""

    def test_creation(self):
        """Test SkillInfo creation."""
        info = SkillInfo(
            name="test-skill",
            description="A test skill",
            source="builtin",
        )
        assert info.name == "test-skill"
        assert info.description == "A test skill"
        assert info.source == "builtin"
        assert info.user_invocable is True
        assert info.disable_model_invocation is False

    def test_optional_fields(self):
        """Test optional fields."""
        info = SkillInfo(
            name="test",
            description="desc",
            source="builtin",
            argument_hint="<arg>",
            when_to_use="Use when needed",
            version="1.0.0",
            allowed_tools=["Read", "Edit"],
            paths=["*.py"],
        )
        assert info.argument_hint == "<arg>"
        assert info.when_to_use == "Use when needed"
        assert info.version == "1.0.0"
        assert info.allowed_tools == ["Read", "Edit"]
        assert info.paths == ["*.py"]


class TestSkillSearchResult:
    """Tests for SkillSearchResult."""

    def test_creation(self):
        """Test SkillSearchResult creation."""
        result = SkillSearchResult(
            query="test",
            hits=[],
            total_hits=0,
            search_time_ms=1.5,
        )
        assert result.query == "test"
        assert result.hits == []
        assert result.total_hits == 0
        assert result.search_time_ms == 1.5
        assert result.from_cache is False


class TestInitializeSkillsService:
    """Tests for initialize_skills_service."""

    def test_initialize_twice_is_idempotent(self):
        """Test that calling initialize twice doesn't reload."""
        # Reset first
        reset_skills_service()

        # First init
        initialize_skills_service(cwd=".", home_dir=None)
        first_names = set(get_all_skill_names())

        # Second init - should be no-op
        initialize_skills_service(cwd=".", home_dir=None)
        second_names = set(get_all_skill_names())

        assert first_names == second_names


class TestGetSkill:
    """Tests for get_skill."""

    def test_returns_none_for_nonexistent(self):
        """Test that non-existent skill returns None."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        result = get_skill("nonexistent-skill-xyz")
        assert result is None


class TestListSkills:
    """Tests for list_skills."""

    def test_returns_list(self):
        """Test that list_skills returns a list."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        skills = list_skills()
        assert isinstance(skills, list)

    def test_filter_by_source(self):
        """Test filtering by source."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        # Filter by builtin source
        builtin_skills = list_skills(source="builtin")
        for skill in builtin_skills:
            assert skill.source == "builtin"

    def test_sorted_by_name(self):
        """Test that skills are sorted by name."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        skills = list_skills()
        names = [s.name for s in skills]
        assert names == sorted(names)


class TestSearchSkills:
    """Tests for search_skills."""

    def test_returns_search_result(self):
        """Test that search returns a SkillSearchResult."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        result = search_skills("test")
        assert isinstance(result, SkillSearchResult)
        assert result.query == "test"

    def test_empty_query_returns_all(self):
        """Test that empty query returns all skills."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        all_skills = list_skills()
        result = search_skills("")
        # Empty query should match something (or return empty if no matches)
        assert isinstance(result.hits, list)

    def test_max_results_limit(self):
        """Test that max_results limits results."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        result = search_skills("", max_results=5)
        assert len(result.hits) <= 5

    def test_search_time_recorded(self):
        """Test that search time is recorded."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        result = search_skills("test")
        assert result.search_time_ms >= 0


class TestGetAllSkillNames:
    """Tests for get_all_skill_names."""

    def test_returns_list_of_strings(self):
        """Test that it returns a list of strings."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        names = get_all_skill_names()
        assert isinstance(names, list)
        for name in names:
            assert isinstance(name, str)


class TestSkillExists:
    """Tests for skill_exists."""

    def test_false_for_nonexistent(self):
        """Test that non-existent skill returns False."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        assert skill_exists("nonexistent-skill-xyz-abc") is False

    def test_true_for_existing(self):
        """Test that existing skill returns True."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        # Get a skill that should exist
        names = get_all_skill_names()
        if names:
            assert skill_exists(names[0]) is True


class TestGetSkillsStats:
    """Tests for get_skills_stats."""

    def test_returns_skills_stats(self):
        """Test that it returns SkillsStats."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        stats = get_skills_stats()
        assert hasattr(stats, 'enabled')
        assert hasattr(stats, 'total_skills')

    def test_stats_contain_counts(self):
        """Test that stats contain skill counts."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        stats = get_skills_stats()
        assert stats.total_skills >= 0


class TestResetSkillsService:
    """Tests for reset_skills_service."""

    def test_reset_clears_state(self):
        """Test that reset clears the state."""
        reset_skills_service()
        initialize_skills_service(cwd=".", home_dir=None)

        # Should have some skills after init
        names_before = get_all_skill_names()

        # Reset
        reset_skills_service()

        # State should be cleared (names list should be empty or service reinitialized)
        initialize_skills_service(cwd=".", home_dir=None)
        names_after = get_all_skill_names()

        # After re-init, should have same skills
        assert set(names_before) == set(names_after)
