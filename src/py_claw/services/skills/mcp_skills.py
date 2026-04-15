"""
MCP Skills integration.

Provides skill discovery from MCP (Model Context Protocol) servers.
This module fetches skills exposed by MCP servers and integrates
them into the unified skills catalog.

Reference: ClaudeCode-main/src/skills/mcpSkills.ts
           ClaudeCode-main/src/skills/mcpSkillBuilders.ts
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.services.skills.types import SkillInfo


# MCP skill builders registry - for lazy loading without circular dependencies
_mcp_skill_builders: dict[str, object] = {}


def register_mcp_skill_builder(name: str, builder: object) -> None:
    """
    Register an MCP skill builder.

    This allows MCP server integrations to provide custom skill
    creation functions without creating circular import dependencies.

    Args:
        name: Name of the builder (e.g., 'create_skill_command', 'parse_frontmatter')
        builder: The builder object/function to register
    """
    _mcp_skill_builders[name] = builder


def get_mcp_skill_builder(name: str) -> object | None:
    """
    Get a registered MCP skill builder.

    Args:
        name: Name of the builder

    Returns:
        The registered builder or None if not found
    """
    return _mcp_skill_builders.get(name)


def get_registered_builder_names() -> list[str]:
    """Get list of registered builder names."""
    return list(_mcp_skill_builders.keys())


async def fetch_mcp_skills_for_client() -> list[SkillInfo]:
    """
    Fetch skills available from connected MCP servers.

    This function queries all registered MCP servers for their
    available skills and returns them as SkillInfo objects.

    Returns:
        List of SkillInfo objects from MCP servers

    Note:
        This function returns an empty list if no MCP servers are connected
        or if no MCP servers expose skills. MCP skill discovery happens
        lazily when MCP servers connect and register their skill builders.
    """
    from .service import get_skill, list_skills

    # Get all skills and filter to MCP source
    all_skills = list_skills(source="mcp")

    # If we have MCP skills in the catalog, return them
    if all_skills:
        return all_skills

    # Otherwise, return empty list (no MCP servers connected)
    return []


def is_mcp_skill(name: str) -> bool:
    """
    Check if a skill is from an MCP source.

    Args:
        name: Skill name

    Returns:
        True if the skill is from an MCP source
    """
    skill = get_skill(name)
    return skill is not None and skill.source == "mcp"


def get_mcp_skill_tools(skill_name: str) -> list[str] | None:
    """
    Get the tools available for an MCP skill.

    Args:
        skill_name: Name of the MCP skill

    Returns:
        List of tool names provided by the skill, or None if not an MCP skill
    """
    skill = get_skill(skill_name)
    if skill is None or skill.source != "mcp":
        return None

    # MCP skills may specify allowed tools in their metadata
    return skill.allowed_tools
