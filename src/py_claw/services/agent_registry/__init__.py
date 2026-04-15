"""
Agent registry service.

Provides built-in agent definitions and agent resolution.

Basic usage:

    from py_claw.services.agent_registry import get_agent_registry_service

    svc = get_agent_registry_service()
    svc.initialize()

    # List available built-in agents
    agents = svc.list_builtin_agents()

    # Get a specific built-in agent
    agent = svc.get_builtin_agent("Explore")

    # Resolve an agent type
    resolved = svc.resolve_agent("general-purpose", "desc", "prompt")
"""
from __future__ import annotations

from .types import BuiltInAgentDefinition
from .built_in import (
    GENERAL_PURPOSE_AGENT,
    EXPLORE_AGENT,
    PLAN_AGENT,
    BUILTIN_AGENTS,
    get_builtin_agents,
    get_builtin_agent,
)
from .service import (
    AgentRegistryService,
    get_agent_registry_service,
    reset_agent_registry_service,
)

__all__ = [
    # Types
    "BuiltInAgentDefinition",
    # Built-in agents
    "GENERAL_PURPOSE_AGENT",
    "EXPLORE_AGENT",
    "PLAN_AGENT",
    "BUILTIN_AGENTS",
    "get_builtin_agents",
    "get_builtin_agent",
    # Service
    "AgentRegistryService",
    "get_agent_registry_service",
    "reset_agent_registry_service",
]
