"""
Agent registry service.

Provides access to built-in agents and manages agent definitions.
"""
from __future__ import annotations

from typing import Any

from .built_in import get_builtin_agents, get_builtin_agent
from .types import BuiltInAgentDefinition


class AgentRegistryService:
    """
    Service for managing agent definitions.

    Built-in agents are always available. Custom agents can be
    registered via settings or plugins.
    """

    def __init__(self) -> None:
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the agent registry."""
        self._initialized = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    def list_builtin_agents(self) -> list[dict[str, Any]]:
        """List all available built-in agents."""
        agents = []
        for agent_type, agent in get_builtin_agents().items():
            if agent.enabled:
                agents.append({
                    "agent_type": agent.agent_type,
                    "description": agent.description,
                    "when_to_use": agent.when_to_use,
                    "model": agent.model,
                    "source": "built-in",
                    "tools": agent.tools,
                    "disallowed_tools": agent.disallowed_tools,
                })
        return agents

    def get_builtin_agent(self, agent_type: str) -> dict[str, Any] | None:
        """Get a built-in agent definition by type."""
        agent = get_builtin_agent(agent_type)
        if agent is None or not agent.enabled:
            return None
        return {
            "agent_type": agent.agent_type,
            "description": agent.description,
            "prompt": agent.prompt,
            "when_to_use": agent.when_to_use,
            "model": agent.model,
            "source": "built-in",
            "tools": agent.tools,
            "disallowed_tools": agent.disallowed_tools,
            "omit_claude_md": agent.omit_claude_md,
        }

    def resolve_agent(
        self,
        agent_type: str,
        default_description: str,
        default_prompt: str,
    ) -> dict[str, Any] | None:
        """
        Resolve an agent by type.

        If the type matches a built-in agent, returns that definition.
        Otherwise returns None (caller should use ephemeral agent).
        """
        agent_def = self.get_builtin_agent(agent_type)
        if agent_def is not None:
            return agent_def

        # Check if it's a known built-in type even if disabled
        builtin = get_builtin_agent(agent_type)
        if builtin is not None and not builtin.enabled:
            return None

        return None


# ============================================================================
# Global singleton
# ============================================================================

_service: AgentRegistryService | None = None


def get_agent_registry_service() -> AgentRegistryService:
    """Get the global agent registry service instance."""
    global _service
    if _service is None:
        _service = AgentRegistryService()
    return _service


def reset_agent_registry_service() -> None:
    """Reset the global agent registry service (for testing)."""
    global _service
    _service = None
