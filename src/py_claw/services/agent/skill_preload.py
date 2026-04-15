"""
Agent skill preloading service.

Preloads prompt-based skills into agent context before first turn,
resolving skill names from agent frontmatter and loading their content.

This follows the pattern from runAgent.ts where skills from
`agentDefinition.skills` are resolved, loaded, and prepended
as user messages to the agent's initial context.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from py_claw.skills import DiscoveredSkill

logger = logging.getLogger(__name__)


# ─── Skill Resolution ───────────────────────────────────────────────────────────


def resolve_skill_name(
    skill_name: str,
    all_skills: list[DiscoveredSkill],
    agent_type: str,
) -> str | None:
    """Resolve a skill name from agent frontmatter to a registered skill.

    Tries multiple resolution strategies:
    1. Exact match on skill name
    2. Prefix with agent's plugin name (e.g., "my-skill" → "plugin:my-skill")
    3. Suffix match — find any skill whose name ends with ":skillName"

    Args:
        skill_name: Skill name from agent frontmatter
        all_skills: All available skills
        agent_type: Agent type (e.g., "pluginName:agentName")

    Returns:
        Resolved skill name, or None if not found
    """
    # 1. Direct match
    for skill in all_skills:
        if skill.name == skill_name:
            return skill_name

    # 2. Try prefixing with the agent's plugin name
    # Plugin agents have agentType like "pluginName:agentName"
    plugin_prefix = agent_type.split(":")[0] if ":" in agent_type else None
    if plugin_prefix:
        qualified_name = f"{plugin_prefix}:{skill_name}"
        for skill in all_skills:
            if skill.name == qualified_name:
                return qualified_name

    # 3. Suffix match — find a skill whose name ends with ":skillName"
    suffix = f":{skill_name}"
    for skill in all_skills:
        if skill.name.endswith(suffix):
            return skill.name

    return None


# ─── Skill Preload Types ────────────────────────────────────────────────────────


@dataclass
class PreloadedSkill:
    """A preloaded skill for an agent."""

    skill_name: str
    content: str = ""
    progress_message: str | None = None


@dataclass
class SkillPreloadResult:
    """Result from skill preloading."""

    skills: list[PreloadedSkill] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── Skill Preload Service ─────────────────────────────────────────────────────


class SkillPreloadService:
    """Service for preloading skills into agent context.

    Provides:
    - preload_skills(): Load skills and return formatted messages
    """

    def __init__(self, cwd: str, all_skills: list[DiscoveredSkill] | None = None):
        """Initialize the skill preload service.

        Args:
            cwd: Current working directory
            all_skills: Optional pre-loaded skill catalog
        """
        self._cwd = cwd
        self._all_skills = all_skills or []

    def preload_skills(
        self,
        skill_names: list[str],
        agent_type: str,
    ) -> SkillPreloadResult:
        """Preload skills from agent frontmatter.

        Resolves skill names using multiple strategies, loads skill content,
        and returns formatted messages that can be prepended to the agent's
        initial context.

        Args:
            skill_names: List of skill names from agent frontmatter
            agent_type: Agent type for name resolution

        Returns:
            SkillPreloadResult with loaded skills, messages, and warnings
        """
        result = SkillPreloadResult()

        for skill_name in skill_names:
            resolved_name = resolve_skill_name(
                skill_name,
                self._all_skills,
                agent_type,
            )

            if resolved_name is None:
                result.warnings.append(
                    f"Skill '{skill_name}' specified in frontmatter was not found"
                )
                logger.debug("Skill '%s' not found for agent type '%s'", skill_name, agent_type)
                continue

            # Find the skill
            skill = next(
                (s for s in self._all_skills if s.name == resolved_name),
                None,
            )
            if skill is None:
                result.warnings.append(
                    f"Skill '{resolved_name}' could not be loaded"
                )
                continue

            # Get skill content
            skill_content = skill.content or ""
            if not skill_content:
                result.warnings.append(
                    f"Skill '{skill_name}' has no content"
                )
                continue

            # Create progress message metadata
            progress_message = f"[Loading skill: {skill_name}]"

            # Format as user message
            message = {
                "type": "user",
                "role": "user",
                "content": [
                    {"type": "text", "text": f"[Skill: {skill_name}]"},
                    {"type": "text", "text": skill_content},
                ],
                "is_meta": True,
            }

            result.messages.append(message)
            result.skills.append(
                PreloadedSkill(
                    skill_name=skill_name,
                    content=skill_content,
                    progress_message=progress_message,
                )
            )

            logger.debug(
                "Preloaded skill '%s' for agent type '%s'",
                skill_name,
                agent_type,
            )

        return result


# ─── Convenience Functions ──────────────────────────────────────────────────────


def preload_agent_skills(
    skill_names: list[str],
    agent_type: str,
    cwd: str,
    all_skills: list[DiscoveredSkill] | None = None,
) -> SkillPreloadResult:
    """Preload skills for an agent.

    Convenience function that creates a SkillPreloadService and
    preloads the skills.

    Args:
        skill_names: List of skill names from agent frontmatter
        agent_type: Agent type for name resolution
        cwd: Current working directory
        all_skills: Optional pre-loaded skill catalog

    Returns:
        SkillPreloadResult with loaded skills, messages, and warnings
    """
    service = SkillPreloadService(cwd=cwd, all_skills=all_skills)
    return service.preload_skills(skill_names, agent_type)
