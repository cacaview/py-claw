"""
Tests for the skill discovery service.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from py_claw.services.skill_discovery import (
    SkillDiscoveryState,
    get_skill_discovery_state,
    reset_skill_discovery_state,
    SkillDiscoveryService,
    get_skill_discovery_service,
    reset_skill_discovery_service,
    discover_skill_dirs_for_paths,
    activate_conditional_skills_for_paths,
)
from py_claw.services.skill_discovery.types import (
    SkillActivationType,
    SkillCondition,
    DiscoveredSkillState,
)
from py_claw.skills import (
    DiscoveredSkill,
    discover_local_skills,
    parse_skill_document,
    render_skill_prompt,
    get_policy_skills_path,
    is_bare_mode,
    execute_shell_in_prompt,
    estimate_skill_tokens,
)


class TestSkillCondition:
    """Tests for SkillCondition."""

    def test_from_paths_list_strips_suffix(self) -> None:
        paths = ["src/**/*.py", "tests/**/*.py", "docs/**"]
        condition = SkillCondition.from_paths_list(paths)
        assert condition.glob_patterns == ["src/**/*.py", "tests/**/*.py"]

    def test_from_paths_list_removes_match_all(self) -> None:
        paths = ["**", "src/**/*.py"]
        condition = SkillCondition.from_paths_list(paths)
        assert condition.glob_patterns == ["src/**/*.py"]

    def test_from_paths_list_empty(self) -> None:
        condition = SkillCondition.from_paths_list([])
        assert condition.glob_patterns is None

    def test_from_paths_list_strips_trailing_slashes(self) -> None:
        paths = ["src//", "tests/"]
        condition = SkillCondition.from_paths_list(paths)
        assert condition.glob_patterns == ["src", "tests"]


class TestSkillDiscoveryState:
    """Tests for SkillDiscoveryState."""

    def setup_method(self) -> None:
        reset_skill_discovery_state()

    def teardown_method(self) -> None:
        reset_skill_discovery_state()

    def test_singleton(self) -> None:
        state1 = get_skill_discovery_state()
        state2 = get_skill_discovery_state()
        assert state1 is state2

    def test_add_conditional_skill(self) -> None:
        state = get_skill_discovery_state()
        skill = DiscoveredSkill(
            name="test-conditional",
            description="A test conditional skill",
            content="Some content",
            skill_path="/path/to/SKILL.md",
            skill_root="/path/to",
            source="userSettings",
        )
        condition = SkillCondition(glob_patterns=["*.py"])
        state.add_conditional_skill("test-conditional", skill, condition)

        assert "test-conditional" in state.conditional_skills
        assert "test-conditional" in state.skill_conditions
        assert state.get_condition("test-conditional") == condition
        assert state.all_skills["test-conditional"].is_active is False
        assert state.all_skills["test-conditional"].activation_type == SkillActivationType.CONDITIONAL

    def test_activate_skill(self) -> None:
        state = get_skill_discovery_state()
        skill = DiscoveredSkill(
            name="test-conditional",
            description="A test conditional skill",
            content="Some content",
            skill_path="/path/to/SKILL.md",
            skill_root="/path/to",
            source="userSettings",
        )
        condition = SkillCondition(glob_patterns=["*.py"])
        state.add_conditional_skill("test-conditional", skill, condition)

        activated = state.activate_skill("test-conditional")
        assert activated is not None
        assert activated.name == "test-conditional"
        assert "test-conditional" not in state.conditional_skills
        assert "test-conditional" in state.dynamic_skills
        assert state.all_skills["test-conditional"].is_active is True

    def test_add_always_skill(self) -> None:
        state = get_skill_discovery_state()
        skill = DiscoveredSkill(
            name="test-always",
            description="An always-on skill",
            content="Some content",
            skill_path="/path/to/SKILL.md",
            skill_root="/path/to",
            source="userSettings",
        )
        state.add_always_skill("test-always", skill)

        assert state.all_skills["test-always"].is_active is True
        assert state.all_skills["test-always"].activation_type == SkillActivationType.ALWAYS

    def test_add_dynamic_skill(self) -> None:
        state = get_skill_discovery_state()
        skill = DiscoveredSkill(
            name="test-dynamic",
            description="A dynamic skill",
            content="Some content",
            skill_path="/path/to/SKILL.md",
            skill_root="/path/to",
            source="dynamic",
        )
        state.add_dynamic_skill("test-dynamic", skill)

        assert state.all_skills["test-dynamic"].is_active is True
        assert state.all_skills["test-dynamic"].activation_type == SkillActivationType.DYNAMIC
        assert "test-dynamic" in state.dynamic_skills

    def test_get_active_skills(self) -> None:
        state = get_skill_discovery_state()
        always = DiscoveredSkill(
            name="always-skill",
            description="Always on",
            content="content",
            skill_path="/p1/SKILL.md",
            skill_root="/p1",
            source="userSettings",
        )
        dynamic = DiscoveredSkill(
            name="dynamic-skill",
            description="Dynamic",
            content="content",
            skill_path="/p2/SKILL.md",
            skill_root="/p2",
            source="dynamic",
        )
        state.add_always_skill("always-skill", always)
        state.add_dynamic_skill("dynamic-skill", dynamic)

        active = state.get_active_skills()
        assert "always-skill" in active
        assert "dynamic-skill" in active

    def test_directory_tracking(self) -> None:
        state = get_skill_discovery_state()
        state.add_discovered_dir("/some/path")
        assert state.is_dir_discovered("/some/path")
        assert not state.is_dir_discovered("/other/path")

    def test_clear(self) -> None:
        state = get_skill_discovery_state()
        skill = DiscoveredSkill(
            name="test",
            description="test",
            content="content",
            skill_path="/p/SKILL.md",
            skill_root="/p",
            source="userSettings",
        )
        state.add_always_skill("test", skill)
        state.add_discovered_dir("/some/path")
        state.clear()

        assert len(state.all_skills) == 0
        assert len(state.discovered_dirs) == 0


class TestSkillDiscoveryService:
    """Tests for SkillDiscoveryService."""

    def setup_method(self) -> None:
        reset_skill_discovery_service()

    def teardown_method(self) -> None:
        reset_skill_discovery_service()

    def test_service_singleton(self) -> None:
        svc1 = get_skill_discovery_service()
        svc2 = get_skill_discovery_service()
        assert svc1 is svc2

    def test_initialize_empty(self) -> None:
        svc = get_skill_discovery_service()
        svc.initialize(cwd="/nonexistent")
        assert svc.initialized

    def test_get_active_skills_empty(self) -> None:
        svc = get_skill_discovery_service()
        svc.initialize(cwd="/nonexistent")
        active = svc.get_active_skills()
        assert isinstance(active, dict)


class TestParseSkillDocument:
    """Tests for skill document parsing."""

    def test_parse_with_frontmatter(self) -> None:
        text = """---
description: A test skill
paths:
  - "*.py"
  - "src/**/*.js"
---
This is the skill content."""
        result = parse_skill_document(text)
        assert result.frontmatter["description"] == "A test skill"
        assert result.content == "This is the skill content."

    def test_parse_without_frontmatter(self) -> None:
        text = "Just plain content without frontmatter"
        result = parse_skill_document(text)
        assert result.frontmatter == {}
        assert result.content == text

    def test_parse_with_multiline_paths(self) -> None:
        text = """---
paths:
  - "*.py"
  - "src/**/*.js"
---
Content"""
        result = parse_skill_document(text)
        assert "*.py" in result.frontmatter["paths"]
        assert "src/**/*.js" in result.frontmatter["paths"]


class TestRenderSkillPrompt:
    """Tests for skill prompt rendering."""

    def test_render_with_skill_root(self) -> None:
        skill = DiscoveredSkill(
            name="test",
            description="test",
            content="Do something",
            skill_path="/path/to/test/SKILL.md",
            skill_root="/path/to/test",
            source="userSettings",
        )
        result = render_skill_prompt(skill)
        assert "Base directory for this skill" in result
        assert "Do something" in result

    def test_render_with_args(self) -> None:
        skill = DiscoveredSkill(
            name="test",
            description="test",
            content="Hello $ARGUMENTS",
            skill_path="/path/to/test/SKILL.md",
            skill_root="/path/to/test",
            source="userSettings",
        )
        result = render_skill_prompt(skill, args="world")
        assert "Hello world" in result

    def test_render_substitutes_claude_vars(self) -> None:
        skill = DiscoveredSkill(
            name="test",
            description="test",
            content="${CLAUDE_SKILL_DIR} and ${CLAUDE_SESSION_ID}",
            skill_path="/path/to/test/SKILL.md",
            skill_root="/path/to/test",
            source="userSettings",
        )
        result = render_skill_prompt(skill)
        assert "path/to/test" in result
        assert "${CLAUDE_SESSION_ID}" not in result


class TestExecuteShellInPrompt:
    """Tests for shell inline execution."""

    def test_no_shell_blocks(self) -> None:
        content = "This is plain content without shell blocks"
        result = execute_shell_in_prompt(content)
        assert result == content

    def test_shell_block_execution(self) -> None:
        content = "Result: !echo hello!"
        result = execute_shell_in_prompt(content)
        assert result.strip() == "Result: hello"

    def test_multiple_shell_blocks(self) -> None:
        content = "First: !echo one! Second: !echo two!"
        result = execute_shell_in_prompt(content)
        assert "First: one" in result
        assert "Second: two" in result


class TestEstimateSkillTokens:
    """Tests for skill token estimation."""

    def test_estimate_tokens(self) -> None:
        skill = DiscoveredSkill(
            name="test",
            description="test",
            content="a" * 100,
            skill_path="/p/SKILL.md",
            skill_root="/p",
            source="userSettings",
        )
        # 100 chars / 4 = ~25 tokens
        assert estimate_skill_tokens(skill) == 25


class TestDiscoverSkillDirsForPaths:
    """Tests for dynamic skill directory discovery."""

    def setup_method(self) -> None:
        reset_skill_discovery_state()

    def teardown_method(self) -> None:
        reset_skill_discovery_state()

    def test_discover_empty_dir(self, tmp_path: Path) -> None:
        result = discover_skill_dirs_for_paths(tmp_path)
        assert result == []

    def test_discover_skips_already_discovered(self, tmp_path: Path) -> None:
        state = get_skill_discovery_state()
        state.add_discovered_dir(str(tmp_path.resolve()))
        result = discover_skill_dirs_for_paths(tmp_path)
        assert result == []

    def test_discover_nested_skill_dirs(self, tmp_path: Path) -> None:
        # Create nested structure with a skill
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\ndescription: Test skill\n---\nContent", encoding="utf-8")

        result = discover_skill_dirs_for_paths(tmp_path)
        assert len(result) == 1
        assert result[0].name == "my-skill"


class TestDiscoverLocalSkills:
    """Tests for discover_local_skills with policy and commands dirs."""

    def test_discover_with_settings_skills(self, tmp_path: Path) -> None:
        skills = discover_local_skills(
            cwd=str(tmp_path),
            settings_skills=["my-skill", "other-skill"],
        )
        names = [s.name for s in skills]
        assert "my-skill" in names
        assert "other-skill" in names

    def test_discover_skills_from_subdirs(self, tmp_path: Path) -> None:
        # Create a skill directory
        skill_dir = tmp_path / ".claude" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\ndescription: A test skill\n---\nSkill content", encoding="utf-8")

        skills = discover_local_skills(cwd=str(tmp_path))
        names = [s.name for s in skills]
        assert "test-skill" in names


class TestIsBareMode:
    """Tests for bare mode detection."""

    def test_bare_mode_false_by_default(self) -> None:
        import os
        orig = os.environ.get("CLAUDE_CODE_BARE_MODE")
        if orig is not None:
            del os.environ["CLAUDE_CODE_BARE_MODE"]
        try:
            assert is_bare_mode() is False
        finally:
            if orig is not None:
                os.environ["CLAUDE_CODE_BARE_MODE"] = orig

    def test_bare_mode_true_when_set(self) -> None:
        import os
        orig = os.environ.get("CLAUDE_CODE_BARE_MODE")
        os.environ["CLAUDE_CODE_BARE_MODE"] = "true"
        try:
            assert is_bare_mode() is True
        finally:
            if orig is not None:
                os.environ["CLAUDE_CODE_BARE_MODE"] = orig
            else:
                del os.environ["CLAUDE_CODE_BARE_MODE"]


class TestGetPolicySkillsPath:
    """Tests for policy skills path detection."""

    def test_policy_path_none_when_not_set(self) -> None:
        import os
        orig = os.environ.get("CLAUDE_CODE_POLICY_DIR")
        if orig is not None:
            del os.environ["CLAUDE_CODE_POLICY_DIR"]
        try:
            assert get_policy_skills_path() is None
        finally:
            if orig is not None:
                os.environ["CLAUDE_CODE_POLICY_DIR"] = orig

    def test_policy_path_when_set(self) -> None:
        import os
        orig = os.environ.get("CLAUDE_CODE_POLICY_DIR")
        os.environ["CLAUDE_CODE_POLICY_DIR"] = "/some/policy/path"
        try:
            result = get_policy_skills_path()
            assert result == Path("/some/policy/path")
        finally:
            if orig is not None:
                os.environ["CLAUDE_CODE_POLICY_DIR"] = orig
            else:
                del os.environ["CLAUDE_CODE_POLICY_DIR"]


class TestSkillActivationType:
    """Tests for SkillActivationType enum."""

    def test_activation_types(self) -> None:
        assert SkillActivationType.ALWAYS == "always"
        assert SkillActivationType.CONDITIONAL == "conditional"
        assert SkillActivationType.DYNAMIC == "dynamic"

    def test_activation_type_string_enum(self) -> None:
        assert SkillActivationType.ALWAYS.value == "always"
        assert isinstance(SkillActivationType.ALWAYS, str)


class TestDiscoveredSkillState:
    """Tests for DiscoveredSkillState dataclass."""

    def test_discovered_skill_state_default(self) -> None:
        skill = DiscoveredSkill(
            name="test",
            description="desc",
            content="content",
            skill_path="/p/SKILL.md",
            skill_root="/p",
            source="userSettings",
        )
        state = DiscoveredSkillState(
            skill=skill,
            activation_type=SkillActivationType.ALWAYS,
        )
        assert state.skill is skill
        assert state.activation_type == SkillActivationType.ALWAYS
        assert state.condition is None
        assert state.is_active is True
