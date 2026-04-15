"""
Tests for the agent registry service.
"""
from __future__ import annotations

import pytest

from py_claw.services.agent_registry import (
    BuiltInAgentDefinition,
    GENERAL_PURPOSE_AGENT,
    EXPLORE_AGENT,
    PLAN_AGENT,
    BUILTIN_AGENTS,
    get_builtin_agents,
    get_builtin_agent,
    AgentRegistryService,
    get_agent_registry_service,
    reset_agent_registry_service,
)


class TestBuiltInAgents:
    """Tests for built-in agent definitions."""

    def test_general_purpose_agent(self) -> None:
        assert GENERAL_PURPOSE_AGENT.agent_type == "general-purpose"
        assert GENERAL_PURPOSE_AGENT.description
        assert GENERAL_PURPOSE_AGENT.prompt
        assert GENERAL_PURPOSE_AGENT.tools == ["*"]
        assert GENERAL_PURPOSE_AGENT.enabled is True

    def test_explore_agent(self) -> None:
        assert EXPLORE_AGENT.agent_type == "Explore"
        assert EXPLORE_AGENT.description
        assert EXPLORE_AGENT.prompt
        assert "Glob" in EXPLORE_AGENT.tools
        assert "Grep" in EXPLORE_AGENT.tools
        assert "Write" in EXPLORE_AGENT.disallowed_tools
        assert "Edit" in EXPLORE_AGENT.disallowed_tools
        assert EXPLORE_AGENT.model == "haiku"
        assert EXPLORE_AGENT.omit_claude_md is True

    def test_plan_agent(self) -> None:
        assert PLAN_AGENT.agent_type == "Plan"
        assert PLAN_AGENT.description
        assert PLAN_AGENT.prompt
        assert "Glob" in PLAN_AGENT.tools
        assert "Grep" in PLAN_AGENT.tools
        assert "Write" in PLAN_AGENT.disallowed_tools
        assert PLAN_AGENT.model == "inherit"
        assert PLAN_AGENT.omit_claude_md is True

    def test_builtin_agents_dict(self) -> None:
        assert "general-purpose" in BUILTIN_AGENTS
        assert "Explore" in BUILTIN_AGENTS
        assert "Plan" in BUILTIN_AGENTS
        assert "statusline-setup" in BUILTIN_AGENTS
        assert len(BUILTIN_AGENTS) == 4


class TestGetBuiltinAgent:
    """Tests for get_builtin_agent function."""

    def test_get_existing_agent(self) -> None:
        agent = get_builtin_agent("Explore")
        assert agent is not None
        assert agent.agent_type == "Explore"

    def test_get_nonexistent_agent(self) -> None:
        agent = get_builtin_agent("NonExistent")
        assert agent is None

    def test_get_all_agents(self) -> None:
        agents = get_builtin_agents()
        assert len(agents) == 4
        assert "general-purpose" in agents
        assert "Explore" in agents
        assert "Plan" in agents
        assert "statusline-setup" in agents


class TestAgentRegistryService:
    """Tests for AgentRegistryService."""

    def setup_method(self) -> None:
        reset_agent_registry_service()

    def test_singleton(self) -> None:
        svc1 = get_agent_registry_service()
        svc2 = get_agent_registry_service()
        assert svc1 is svc2

    def test_initialize(self) -> None:
        svc = get_agent_registry_service()
        assert not svc.initialized
        svc.initialize()
        assert svc.initialized

    def test_list_builtin_agents(self) -> None:
        svc = get_agent_registry_service()
        svc.initialize()
        agents = svc.list_builtin_agents()
        assert len(agents) == 4
        agent_types = {a["agent_type"] for a in agents}
        assert "general-purpose" in agent_types
        assert "Explore" in agent_types
        assert "Plan" in agent_types
        assert "statusline-setup" in agent_types

    def test_get_builtin_agent(self) -> None:
        svc = get_agent_registry_service()
        svc.initialize()
        agent = svc.get_builtin_agent("Explore")
        assert agent is not None
        assert agent["agent_type"] == "Explore"
        assert agent["model"] == "haiku"
        assert agent["when_to_use"] is not None

    def test_get_nonexistent_agent(self) -> None:
        svc = get_agent_registry_service()
        svc.initialize()
        agent = svc.get_builtin_agent("NonExistent")
        assert agent is None

    def test_resolve_builtin_agent(self) -> None:
        svc = get_agent_registry_service()
        svc.initialize()
        resolved = svc.resolve_agent("general-purpose", "desc", "prompt")
        assert resolved is not None
        assert resolved["agent_type"] == "general-purpose"
        assert resolved["prompt"] == GENERAL_PURPOSE_AGENT.prompt

    def test_resolve_unknown_returns_none(self) -> None:
        svc = get_agent_registry_service()
        svc.initialize()
        resolved = svc.resolve_agent("UnknownAgent", "desc", "prompt")
        assert resolved is None


class TestBuiltInAgentDefinition:
    """Tests for BuiltInAgentDefinition dataclass."""

    def test_to_agent_definition(self) -> None:
        agent = BuiltInAgentDefinition(
            agent_type="Test",
            description="A test agent",
            prompt="You are a test agent",
            tools=["Read", "Write"],
            disallowed_tools=["Bash"],
            model="haiku",
            omit_claude_md=True,
        )
        result = agent.to_agent_definition()
        assert result["name"] == "Test"
        assert result["description"] == "A test agent"
        assert result["prompt"] == "You are a test agent"
        assert result["tools"] == ["Read", "Write"]
        assert result["disallowedTools"] == ["Bash"]
        assert result["model"] == "haiku"

    def test_extra_fields(self) -> None:
        agent = BuiltInAgentDefinition(
            agent_type="Test",
            description="A test agent",
            prompt="You are a test agent",
            extra={"custom_field": "value"},
        )
        result = agent.to_agent_definition()
        assert result["custom_field"] == "value"
