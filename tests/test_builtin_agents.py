"""
Tests for built-in agent definitions.
"""
from __future__ import annotations

import pytest

from py_claw.services.agent_registry.built_in import (
    BUILTIN_AGENTS,
    CLAUDE_CODE_GUIDE_AGENT,
    EXPLORE_AGENT,
    GENERAL_PURPOSE_AGENT,
    PLAN_AGENT,
    STATUSLINE_SETUP_AGENT,
    VERIFICATION_AGENT,
    get_builtin_agent,
    get_builtin_agents,
)


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


class TestBuiltinAgentsRegistry:
    """All 6 built-in agents must be present in the registry."""

    EXPECTED_KEYS = [
        "general-purpose",
        "Explore",
        "Plan",
        "verification",
        "claude-code-guide",
        "statusline-setup",
    ]

    def test_registry_has_all_six_agents(self):
        assert len(BUILTIN_AGENTS) == 6
        for key in self.EXPECTED_KEYS:
            assert key in BUILTIN_AGENTS, f"Missing agent: {key}"

    def test_get_builtin_agents_returns_copy(self):
        agents = get_builtin_agents()
        assert agents == BUILTIN_AGENTS
        # Should be a copy, not the original
        agents["extra"] = None
        assert "extra" not in BUILTIN_AGENTS

    def test_get_builtin_agent_returns_correct_agent(self):
        for key in self.EXPECTED_KEYS:
            agent = get_builtin_agent(key)
            assert agent is not None, f"get_builtin_agent({key!r}) returned None"
            assert agent.agent_type == key

    def test_get_builtin_agent_nonexistent_returns_none(self):
        assert get_builtin_agent("nonexistent") is None
        assert get_builtin_agent("") is None


# ---------------------------------------------------------------------------
# Required fields on every agent
# ---------------------------------------------------------------------------


class TestAgentRequiredFields:
    """Every agent must have agent_type, description, prompt."""

    @pytest.mark.parametrize("key", TestBuiltinAgentsRegistry.EXPECTED_KEYS)
    def test_agent_has_required_fields(self, key: str):
        agent = get_builtin_agent(key)
        assert agent is not None
        assert isinstance(agent.agent_type, str) and len(agent.agent_type) > 0
        assert isinstance(agent.description, str) and len(agent.description) > 0
        assert isinstance(agent.prompt, str) and len(agent.prompt) > 0


# ---------------------------------------------------------------------------
# Verification agent specifics
# ---------------------------------------------------------------------------


class TestVerificationAgent:
    def test_exists(self):
        assert VERIFICATION_AGENT.agent_type == "verification"

    def test_disallowed_tools(self):
        expected = {"Write", "Edit", "NotebookEdit", "Agent", "EnterPlanMode"}
        assert set(VERIFICATION_AGENT.disallowed_tools) == expected

    def test_model_is_inherit(self):
        assert VERIFICATION_AGENT.model == "inherit"

    def test_background_is_true(self):
        assert VERIFICATION_AGENT.background is True

    def test_tools(self):
        assert set(VERIFICATION_AGENT.tools) == {"Glob", "Grep", "Read", "Bash"}


# ---------------------------------------------------------------------------
# Claude Code Guide agent specifics
# ---------------------------------------------------------------------------


class TestClaudeCodeGuideAgent:
    def test_exists(self):
        assert CLAUDE_CODE_GUIDE_AGENT.agent_type == "claude-code-guide"

    def test_permission_mode_is_dont_ask(self):
        assert CLAUDE_CODE_GUIDE_AGENT.permission_mode == "dontAsk"

    def test_model_is_haiku(self):
        assert CLAUDE_CODE_GUIDE_AGENT.model == "haiku"

    def test_tools(self):
        expected = {"Glob", "Grep", "Read", "WebFetch", "WebSearch"}
        assert set(CLAUDE_CODE_GUIDE_AGENT.tools) == expected


# ---------------------------------------------------------------------------
# to_agent_definition() output
# ---------------------------------------------------------------------------


class TestToAgentDefinition:
    def test_general_purpose_serialization(self):
        d = GENERAL_PURPOSE_AGENT.to_agent_definition()
        assert d["name"] == "general-purpose"
        assert d["description"]
        assert d["prompt"]
        assert d["model"] is None  # default
        assert d["tools"] == ["*"]

    def test_verification_serialization_includes_background(self):
        d = VERIFICATION_AGENT.to_agent_definition()
        assert d["background"] is True
        assert d["disallowedTools"] == ["Write", "Edit", "NotebookEdit", "Agent", "EnterPlanMode"]

    def test_claude_code_guide_serialization_includes_permission_mode(self):
        d = CLAUDE_CODE_GUIDE_AGENT.to_agent_definition()
        assert d["permissionMode"] == "dontAsk"
        assert "background" not in d  # not set, should not appear

    def test_explore_serialization_excludes_optional_fields(self):
        d = EXPLORE_AGENT.to_agent_definition()
        assert "permissionMode" not in d
        assert "background" not in d

    def test_plan_serialization(self):
        d = PLAN_AGENT.to_agent_definition()
        assert d["name"] == "Plan"
        assert d["model"] == "inherit"
