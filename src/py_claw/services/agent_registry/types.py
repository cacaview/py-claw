"""
Agent registry types.

Types for built-in agent definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BuiltInAgentDefinition:
    """A built-in agent definition with metadata."""

    # Agent type identifier (e.g., "general-purpose", "Explore", "Plan")
    agent_type: str

    # Human-readable description
    description: str

    # System prompt
    prompt: str

    # When to use this agent (for UX display)
    when_to_use: str | None = None

    # Tools this agent can use (None = all tools)
    tools: list[str] | None = None

    # Tools this agent cannot use
    disallowed_tools: list[str] | None = None

    # Model to use (None = default)
    model: str | None = None

    # Whether this agent is enabled
    enabled: bool = True

    # Whether to omit CLAUDE.md from context
    omit_claude_md: bool = False

    # Additional agent config
    extra: dict[str, Any] = field(default_factory=dict)

    def to_agent_definition(self) -> dict[str, Any]:
        """Convert to dict compatible with AgentDefinition schema."""
        result = {
            "name": self.agent_type,
            "description": self.description,
            "prompt": self.prompt,
            "model": self.model,
            "tools": self.tools,
            "disallowedTools": self.disallowed_tools,
        }
        result.update(self.extra)
        return result
