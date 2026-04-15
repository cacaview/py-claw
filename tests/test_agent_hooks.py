"""Tests for agent hooks service."""

import pytest

from py_claw.services.agent.hooks import (
    AgentHook,
    AgentHooksService,
    _agent_hooks_registry,
    clear_agent_hooks,
    register_agent_hooks,
)


class TestAgentHook:
    """Test AgentHook dataclass."""

    def test_hook_defaults(self):
        hook = AgentHook(event="SubagentStart")
        assert hook.event == "SubagentStart"
        assert hook.prompt == ""
        assert hook.tool_name is None
        assert hook.blocking is False

    def test_hook_with_prompt(self):
        hook = AgentHook(
            event="SubagentStart",
            prompt="Additional context from hook",
        )
        assert hook.prompt == "Additional context from hook"

    def test_hook_with_tool_name(self):
        hook = AgentHook(
            event="ToolUse",
            tool_name="Bash",
            blocking=True,
        )
        assert hook.tool_name == "Bash"
        assert hook.blocking is True


class TestAgentHooksRegistry:
    """Test the hooks registry."""

    def setup_method(self):
        """Clear registry before each test."""
        _agent_hooks_registry._hooks.clear()

    def test_register_and_get(self):
        hooks = [
            AgentHook(event="SubagentStart", prompt="context1"),
            AgentHook(event="SubagentStop"),
        ]
        _agent_hooks_registry.register("agent-123", hooks)

        hook_set = _agent_hooks_registry.get("agent-123")
        assert hook_set is not None
        assert len(hook_set.hooks) == 2
        assert hook_set.hooks[0].event == "SubagentStart"

    def test_unregister(self):
        hooks = [AgentHook(event="SubagentStart")]
        _agent_hooks_registry.register("agent-123", hooks)

        _agent_hooks_registry.unregister("agent-123")
        assert _agent_hooks_registry.get("agent-123") is None

    def test_get_nonexistent(self):
        result = _agent_hooks_registry.get("nonexistent-agent")
        assert result is None

    def test_get_all(self):
        hooks1 = [AgentHook(event="SubagentStart")]
        hooks2 = [AgentHook(event="SubagentStop")]
        _agent_hooks_registry.register("agent-1", hooks1)
        _agent_hooks_registry.register("agent-2", hooks2)

        all_hooks = _agent_hooks_registry.get_all()
        assert len(all_hooks) == 2
        assert "agent-1" in all_hooks
        assert "agent-2" in all_hooks


class TestAgentHooksService:
    """Test AgentHooksService class."""

    def setup_method(self):
        """Clear registry before each test."""
        _agent_hooks_registry._hooks.clear()

    def test_service_initialization(self):
        service = AgentHooksService(cwd="/tmp")
        assert service._cwd == "/tmp"

    def test_register_frontmatter_hooks(self):
        service = AgentHooksService(cwd="/tmp")
        hooks = [
            AgentHook(event="SubagentStart", prompt="extra context"),
            AgentHook(event="SubagentStop"),
        ]
        service.register_frontmatter_hooks("agent-abc", hooks)

        registered = service.get_registered_hooks("agent-abc")
        assert registered is not None
        assert len(registered) == 2

    def test_clear_session_hooks(self):
        service = AgentHooksService(cwd="/tmp")
        hooks = [AgentHook(event="SubagentStart")]
        service.register_frontmatter_hooks("agent-xyz", hooks)

        service.clear_session_hooks("agent-xyz")

        registered = service.get_registered_hooks("agent-xyz")
        assert registered is None

    def test_get_registered_hooks_nonexistent(self):
        service = AgentHooksService(cwd="/tmp")
        result = service.get_registered_hooks("nonexistent")
        assert result is None

    def test_execute_subagent_start_hooks_no_hooks(self):
        service = AgentHooksService(cwd="/tmp")

        # No hooks registered - should yield nothing
        results = list(service.execute_subagent_start_hooks(
            agent_id="agent-123",
            agent_type="Explore",
        ))
        assert results == []


class TestConvenienceFunctions:
    """Test convenience functions."""

    def setup_method(self):
        """Clear registry before each test."""
        _agent_hooks_registry._hooks.clear()

    def test_register_agent_hooks(self):
        hooks = [AgentHook(event="SubagentStart", prompt="context")]
        register_agent_hooks("agent-789", hooks, cwd="/tmp")

        hook_set = _agent_hooks_registry.get("agent-789")
        assert hook_set is not None
        assert len(hook_set.hooks) == 1

    def test_clear_agent_hooks(self):
        hooks = [AgentHook(event="SubagentStart")]
        register_agent_hooks("agent-789", hooks, cwd="/tmp")

        clear_agent_hooks("agent-789")

        assert _agent_hooks_registry.get("agent-789") is None

    def test_clear_nonexistent_agent_hooks(self):
        # Should not raise
        clear_agent_hooks("nonexistent-agent")
