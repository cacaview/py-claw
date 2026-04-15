"""Tests for agent skill preloading service."""

import pytest

from py_claw.services.agent.skill_preload import (
    PreloadedSkill,
    SkillPreloadResult,
    SkillPreloadService,
    preload_agent_skills,
    resolve_skill_name,
)
from py_claw.skills import DiscoveredSkill


# Sample skills for testing
@pytest.fixture
def sample_skills():
    return [
        DiscoveredSkill(
            name="code-review",
            description="Review code changes",
            content="You are a code reviewer...",
            skill_path="/path/to/code-review.md",
            skill_root="/path/to",
            source="userSettings",
        ),
        DiscoveredSkill(
            name="my-plugin:explainer",
            description="Explain things",
            content="I will explain...",
            skill_path="/path/to/explainer.md",
            skill_root="/path/to",
            source="projectSettings",
        ),
        DiscoveredSkill(
            name="anthropic:code-guide",
            description="Claude Code guide",
            content="Guide to Claude Code...",
            skill_path="/path/to/code-guide.md",
            skill_root="/path/to",
            source="policy",
        ),
        DiscoveredSkill(
            name="api-design",
            description="Design APIs",
            content="API design best practices...",
            skill_path="/path/to/api-design.md",
            skill_root="/path/to",
            source="userSettings",
        ),
    ]


class TestResolveSkillName:
    """Test skill name resolution."""

    def test_exact_match(self, sample_skills):
        result = resolve_skill_name("code-review", sample_skills, "Explore")
        assert result == "code-review"

    def test_plugin_prefix_match(self, sample_skills):
        # Agent type is "my-plugin:SomeAgent"
        result = resolve_skill_name(
            "explainer",
            sample_skills,
            "my-plugin:SomeAgent",
        )
        assert result == "my-plugin:explainer"

    def test_suffix_match(self, sample_skills):
        result = resolve_skill_name(
            "code-guide",
            sample_skills,
            "anthropic:Agent",
        )
        assert result == "anthropic:code-guide"

    def test_not_found(self, sample_skills):
        result = resolve_skill_name(
            "nonexistent-skill",
            sample_skills,
            "Explore",
        )
        assert result is None

    def test_empty_skills_list(self):
        result = resolve_skill_name("code-review", [], "Explore")
        assert result is None

    def test_simple_agent_type(self, sample_skills):
        # Agent type without plugin prefix
        result = resolve_skill_name("api-design", sample_skills, "PlanAgent")
        assert result == "api-design"


class TestPreloadedSkill:
    """Test PreloadedSkill dataclass."""

    def test_creation(self):
        skill = PreloadedSkill(
            skill_name="test-skill",
            content="Skill content here",
            progress_message="Loading skill: test-skill",
        )
        assert skill.skill_name == "test-skill"
        assert skill.content == "Skill content here"
        assert skill.progress_message == "Loading skill: test-skill"

    def test_defaults(self):
        skill = PreloadedSkill(skill_name="simple")
        assert skill.skill_name == "simple"
        assert skill.content == ""
        assert skill.progress_message is None


class TestSkillPreloadResult:
    """Test SkillPreloadResult dataclass."""

    def test_empty_result(self):
        result = SkillPreloadResult()
        assert result.skills == []
        assert result.messages == []
        assert result.warnings == []

    def test_with_content(self):
        result = SkillPreloadResult(
            skills=[PreloadedSkill(skill_name="test")],
            messages=[{"type": "user", "content": "test"}],
            warnings=["Some warning"],
        )
        assert len(result.skills) == 1
        assert len(result.messages) == 1
        assert len(result.warnings) == 1


class TestSkillPreloadService:
    """Test SkillPreloadService class."""

    def test_service_initialization(self):
        service = SkillPreloadService(cwd="/tmp")
        assert service._cwd == "/tmp"
        assert service._all_skills == []

    def test_service_with_skills(self, sample_skills):
        service = SkillPreloadService(cwd="/tmp", all_skills=sample_skills)
        assert len(service._all_skills) == 4

    def test_preload_single_skill(self, sample_skills):
        service = SkillPreloadService(cwd="/tmp", all_skills=sample_skills)
        result = service.preload_skills(["code-review"], "Explore")

        assert len(result.skills) == 1
        assert result.skills[0].skill_name == "code-review"
        assert len(result.messages) == 1
        assert len(result.warnings) == 0

    def test_preload_multiple_skills(self, sample_skills):
        service = SkillPreloadService(cwd="/tmp", all_skills=sample_skills)
        result = service.preload_skills(
            ["code-review", "api-design"],
            "PlanAgent",
        )

        assert len(result.skills) == 2
        assert len(result.messages) == 2
        assert len(result.warnings) == 0

    def test_preload_nonexistent_skill(self, sample_skills):
        service = SkillPreloadService(cwd="/tmp", all_skills=sample_skills)
        result = service.preload_skills(
            ["nonexistent", "code-review"],
            "Explore",
        )

        # One warning for nonexistent, one skill loaded
        assert len(result.skills) == 1
        assert len(result.warnings) == 1
        assert "not found" in result.warnings[0]

    def test_preload_skill_with_plugin_resolution(self, sample_skills):
        service = SkillPreloadService(cwd="/tmp", all_skills=sample_skills)
        result = service.preload_skills(
            ["explainer"],
            "my-plugin:SomeAgent",
        )

        assert len(result.skills) == 1
        assert result.skills[0].skill_name == "explainer"

    def test_preload_skill_with_suffix_resolution(self, sample_skills):
        service = SkillPreloadService(cwd="/tmp", all_skills=sample_skills)
        result = service.preload_skills(
            ["code-guide"],
            "anthropic:Agent",
        )

        assert len(result.skills) == 1
        assert result.skills[0].skill_name == "code-guide"

    def test_preload_empty_skill_list(self, sample_skills):
        service = SkillPreloadService(cwd="/tmp", all_skills=sample_skills)
        result = service.preload_skills([], "Explore")

        assert len(result.skills) == 0
        assert len(result.messages) == 0
        assert len(result.warnings) == 0

    def test_preload_skill_no_content(self, sample_skills):
        # Create a skill with empty content
        empty_skills = [
            DiscoveredSkill(
                name="empty-skill",
                description="Empty",
                content="",
                skill_path="/path",
                skill_root="/path",
                source="test",
            ),
        ]
        service = SkillPreloadService(cwd="/tmp", all_skills=empty_skills)
        result = service.preload_skills(["empty-skill"], "Explore")

        # Should report warning about empty content
        assert len(result.warnings) == 1
        assert "no content" in result.warnings[0]

    def test_message_format(self, sample_skills):
        service = SkillPreloadService(cwd="/tmp", all_skills=sample_skills)
        result = service.preload_skills(["code-review"], "Explore")

        assert len(result.messages) == 1
        msg = result.messages[0]
        assert msg["type"] == "user"
        assert msg["role"] == "user"
        assert msg["is_meta"] is True
        assert isinstance(msg["content"], list)


class TestPreloadAgentSkills:
    """Test preload_agent_skills convenience function."""

    def test_convenience_function(self, sample_skills):
        result = preload_agent_skills(
            skill_names=["code-review"],
            agent_type="Explore",
            cwd="/tmp",
            all_skills=sample_skills,
        )

        assert len(result.skills) == 1
        assert result.skills[0].skill_name == "code-review"

    def test_convenience_function_no_skills(self):
        result = preload_agent_skills(
            skill_names=["nonexistent"],
            agent_type="Explore",
            cwd="/tmp",
            all_skills=[],
        )

        assert len(result.skills) == 0
        assert len(result.warnings) == 1
