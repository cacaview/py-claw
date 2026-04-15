"""DiscoverSkillsTool - Tool for discovering available skills.

Based on ClaudeCode-main/src/tools/DiscoverSkillsTool/
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.skills import discover_local_skills, DiscoveredSkill
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


class DiscoverSkillsToolInput(PyClawBaseModel):
    """Input for the DiscoverSkillsTool."""

    query: str | None = Field(
        default=None,
        description="Optional search query to filter skills by name or description",
    )
    context: str | None = Field(
        default=None,
        description="Optional context to help narrow down relevant skills (e.g., 'git', 'docker', 'testing')",
    )
    include_disabled: bool = Field(
        default=False,
        description="Whether to include skills that are disabled for model invocation",
    )


class DiscoveredSkillInfo(PyClawBaseModel):
    """Information about a discovered skill."""

    name: str
    description: str
    source: str
    argument_hint: str | None = None
    when_to_use: str | None = None
    version: str | None = None
    model: str | None = None
    allowed_tools: list[str] | None = None
    effort: str | None = None
    is_available: bool = True
    paths: list[str] | None = None


class DiscoverSkillsToolResult(PyClawBaseModel):
    """Result from the DiscoverSkillsTool."""

    skills: list[DiscoveredSkillInfo]
    total_count: int
    query: str | None = None
    context: str | None = None


class DiscoverSkillsTool:
    """Tool for discovering available skills.

    Allows the model to discover skills in the project based on context,
    similar to the TypeScript DiscoverSkillsTool.
    """

    definition = ToolDefinition(
        name="DiscoverSkills",
        input_model=DiscoverSkillsToolInput,
    )

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        """Get the permission target for this tool call."""
        query = payload.get("query")
        context = payload.get("context")
        content = context if context else query
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(content) if content else None,
        )

    def execute(
        self,
        arguments: DiscoverSkillsToolInput,
        *,
        cwd: str,
    ) -> dict[str, object]:
        """Execute the skill discovery.

        Args:
            arguments: The tool input arguments
            cwd: Current working directory

        Returns:
            Dictionary with discovered skills information
        """
        # Get all local skills
        skills = discover_local_skills(cwd=cwd)

        # Filter by query if provided
        if arguments.query:
            query_lower = arguments.query.lower()
            skills = [
                s for s in skills
                if query_lower in s.name.lower()
                or query_lower in s.description.lower()
            ]

        # Filter by context if provided
        if arguments.context:
            context_lower = arguments.context.lower()
            skills = [
                s for s in skills
                if self._skill_matches_context(s, context_lower)
            ]

        # Filter out disabled skills unless requested
        if not arguments.include_disabled:
            skills = [s for s in skills if not s.disable_model_invocation]

        # Convert to output format
        skill_infos = [
            DiscoveredSkillInfo(
                name=s.name,
                description=s.description,
                source=s.source,
                argument_hint=s.argument_hint or None,
                when_to_use=s.when_to_use,
                version=s.version,
                model=s.model,
                allowed_tools=s.allowed_tools,
                effort=s.effort.value if s.effort else None,
                is_available=not s.disable_model_invocation,
                paths=s.paths,
            )
            for s in skills
        ]

        result = DiscoverSkillsToolResult(
            skills=skill_infos,
            total_count=len(skill_infos),
            query=arguments.query,
            context=arguments.context,
        )

        return result.model_dump(by_alias=True, exclude_none=True)

    def _skill_matches_context(self, skill: DiscoveredSkill, context: str) -> bool:
        """Check if a skill matches the given context.

        Args:
            skill: The skill to check
            context: The context string to match against

        Returns:
            True if the skill matches the context
        """
        # Check skill name and description
        if context in skill.name.lower():
            return True
        if context in skill.description.lower():
            return True

        # Check when_to_use hint
        if skill.when_to_use and context in skill.when_to_use.lower():
            return True

        # Check paths if available
        if skill.paths:
            for path in skill.paths:
                if context in path.lower():
                    return True

        # Check aliases
        if skill.aliases:
            for alias in skill.aliases:
                if context in alias.lower():
                    return True

        return False


class GetSkillDetailsToolInput(PyClawBaseModel):
    """Input for getting detailed information about a specific skill."""

    skill_name: str = Field(description="The name of the skill to get details for")


class SkillDetailsResult(PyClawBaseModel):
    """Detailed information about a skill."""

    name: str
    description: str
    content: str
    source: str
    skill_path: str | None = None
    skill_root: str | None = None
    argument_hint: str | None = None
    when_to_use: str | None = None
    version: str | None = None
    model: str | None = None
    allowed_tools: list[str] | None = None
    effort: str | None = None
    is_available: bool = True
    paths: list[str] | None = None
    hooks: dict[str, Any] | None = None


class GetSkillDetailsTool:
    """Tool for getting detailed information about a specific skill."""

    definition = ToolDefinition(
        name="GetSkillDetails",
        input_model=GetSkillDetailsToolInput,
    )

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        """Get the permission target for this tool call."""
        skill_name = payload.get("skill_name")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(skill_name) if skill_name else None,
        )

    def execute(
        self,
        arguments: GetSkillDetailsToolInput,
        *,
        cwd: str,
    ) -> dict[str, object]:
        """Execute getting skill details.

        Args:
            arguments: The tool input arguments
            cwd: Current working directory

        Returns:
            Dictionary with skill details
        """
        skill = None
        for s in discover_local_skills(cwd=cwd):
            if s.name == arguments.skill_name:
                skill = s
                break

        if skill is None:
            raise ToolError(f"Skill not found: {arguments.skill_name}")

        result = SkillDetailsResult(
            name=skill.name,
            description=skill.description,
            content=skill.content,
            source=skill.source,
            skill_path=skill.skill_path,
            skill_root=skill.skill_root,
            argument_hint=skill.argument_hint or None,
            when_to_use=skill.when_to_use,
            version=skill.version,
            model=skill.model,
            allowed_tools=skill.allowed_tools,
            effort=skill.effort.value if skill.effort else None,
            is_available=not skill.disable_model_invocation,
            paths=skill.paths,
            hooks=skill.hooks,
        )

        return result.model_dump(by_alias=True, exclude_none=True)
