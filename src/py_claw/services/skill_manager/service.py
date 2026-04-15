"""
SkillManager service.

Manages built-in and custom skills.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from py_claw.services.skill_manager.config import (
    BUILTIN_SKILL_DEFINITIONS,
    SkillDefinition,
    get_skill_manager_config,
)

from .types import (
    SkillExecution,
    SkillManagerState,
    SkillMetadata,
    get_skill_manager_state,
)

if TYPE_CHECKING:
    from py_claw.services.api import AnthropicAPIClient


def _load_custom_skill(name: str, skills_dir: str) -> SkillMetadata | None:
    """Load a custom skill from the skills directory.

    Args:
        name: Skill name
        skills_dir: Directory containing skills

    Returns:
        SkillMetadata if skill exists and is valid, None otherwise
    """
    skill_path = Path(skills_dir) / name / "SKILL.md"
    if not skill_path.exists():
        return None

    try:
        content = skill_path.read_text(encoding="utf-8")
        description = ""
        argument_hint = None
        when_to_use = None
        version = None

        for line in content.split("\n"):
            if line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
            elif line.startswith("argument-hint:"):
                argument_hint = line.split(":", 1)[1].strip()
            elif line.startswith("when-to-use:"):
                when_to_use = line.split(":", 1)[1].strip()
            elif line.startswith("version:"):
                version = line.split(":", 1)[1].strip()

        return SkillMetadata(
            name=name,
            description=description or f"Custom skill: {name}",
            argument_hint=argument_hint,
            when_to_use=when_to_use,
            source="custom",
            version=version,
        )
    except Exception:
        return None


def initialize_skills() -> None:
    """Initialize all available skills.

    Registers built-in skills and loads custom skills from the skills directory.
    """
    config = get_skill_manager_config()
    state = get_skill_manager_state()

    # Register built-in skills
    if config.enable_builtin:
        for name, info in BUILTIN_SKILL_DEFINITIONS.items():
            metadata = SkillMetadata(
                name=name,
                description=info.get("description", ""),
                argument_hint=info.get("argument_hint"),
                when_to_use=info.get("when_to_use"),
                source=info.get("source", "builtin"),
                version=info.get("version"),
            )
            state.register_skill(metadata)

    # Load custom skills
    if config.enable_custom:
        skills_dir = Path(config.skills_dir)
        if skills_dir.exists():
            for skill_path in skills_dir.iterdir():
                if skill_path.is_dir():
                    name = skill_path.name
                    # Don't override built-in skills
                    if name not in BUILTIN_SKILL_DEFINITIONS:
                        metadata = _load_custom_skill(name, config.skills_dir)
                        if metadata is not None:
                            state.register_skill(metadata)


def get_skill(name: str) -> SkillMetadata | None:
    """Get a skill by name.

    Args:
        name: Skill name

    Returns:
        SkillMetadata if found, None otherwise
    """
    state = get_skill_manager_state()
    return state.get_skill(name)


def list_skills(source: str | None = None) -> list[SkillMetadata]:
    """List all available skills.

    Args:
        source: Optional filter by source ("builtin", "custom", "installed")

    Returns:
        List of SkillMetadata objects
    """
    state = get_skill_manager_state()
    skills = state.list_skills()

    if source:
        skills = [s for s in skills if s.source == source]

    return sorted(skills, key=lambda s: s.name)


def search_skills(query: str) -> list[SkillMetadata]:
    """Search skills by name or description.

    Args:
        query: Search query

    Returns:
        List of matching SkillMetadata objects
    """
    state = get_skill_manager_state()
    query_lower = query.lower()
    results = []

    for skill in state.list_skills():
        if query_lower in skill.name.lower():
            results.append(skill)
        elif query_lower in skill.description.lower():
            results.append(skill)

    return sorted(results, key=lambda s: s.name)


def execute_skill(
    name: str,
    arguments: str | None = None,
    mode: str = "inline",
    api_client: AnthropicAPIClient | None = None,
) -> SkillExecution:
    """Execute a skill.

    Args:
        name: Skill name
        arguments: Optional arguments to pass to the skill
        mode: Execution mode ("inline", "fork", "remote")
        api_client: Optional API client for skill execution

    Returns:
        SkillExecution with results
    """
    state = get_skill_manager_state()
    config = get_skill_manager_config()
    start_time = time.time()

    # Get skill metadata
    skill = state.get_skill(name)
    if skill is None:
        return SkillExecution(
            skill_name=name,
            success=False,
            error=f"Skill not found: {name}",
            duration_seconds=time.time() - start_time,
            execution_mode=mode,
        )

    try:
        if mode == "inline":
            # Inline execution - build prompt and run
            prompt = _build_skill_prompt(name, arguments)
            if api_client is not None:
                from py_claw.services.api import MessageCreateParams, MessageParam
                response = api_client.create_message(
                    MessageCreateParams(
                        model="claude-sonnet-4-20250514",
                        messages=[MessageParam(role="user", content=prompt)],
                        max_tokens=4096,
                    )
                )
                output = str(response) if response else "Skill executed"
            else:
                output = f"Skill '{name}' executed with arguments: {arguments}"

        elif mode == "fork":
            # Fork execution - would spawn subprocess
            output = f"Skill '{name}' would be executed in forked mode"

        else:  # remote
            output = f"Skill '{name}' would be executed in remote mode"

        duration = time.time() - start_time
        execution = SkillExecution(
            skill_name=name,
            success=True,
            output=output,
            duration_seconds=duration,
            execution_mode=mode,
        )
        state.record_execution(execution)
        return execution

    except Exception as e:
        duration = time.time() - start_time
        execution = SkillExecution(
            skill_name=name,
            success=False,
            error=str(e),
            duration_seconds=duration,
            execution_mode=mode,
        )
        state.record_execution(execution)
        return execution


def _build_skill_prompt(name: str, arguments: str | None) -> str:
    """Build the prompt for a skill execution."""
    state = get_skill_manager_state()
    skill = state.get_skill(name)

    if skill is None:
        return f"Execute skill: {name}"

    prompt_parts = [f"# Skill: {name}\n"]
    prompt_parts.append(f"{skill.description}\n")

    if skill.argument_hint:
        prompt_parts.append(f"\nArgument hint: {skill.argument_hint}")

    if skill.when_to_use:
        prompt_parts.append(f"\nWhen to use: {skill.when_to_use}")

    if arguments:
        prompt_parts.append(f"\n\nArguments: {arguments}")

    return "".join(prompt_parts)


def register_custom_skill(
    name: str,
    description: str,
    prompt_template: str,
    argument_hint: str | None = None,
    when_to_use: str | None = None,
) -> bool:
    """Register a custom skill.

    Args:
        name: Skill name
        description: Skill description
        prompt_template: The prompt template for this skill
        argument_hint: Optional argument hint
        when_to_use: Optional when-to-use guidance

    Returns:
        True if registered successfully
    """
    state = get_skill_manager_state()
    metadata = SkillMetadata(
        name=name,
        description=description,
        argument_hint=argument_hint,
        when_to_use=when_to_use,
        source="custom",
    )
    state.register_skill(metadata)
    return True


def unregister_skill(name: str) -> bool:
    """Unregister a skill.

    Args:
        name: Skill name

    Returns:
        True if unregistered successfully
    """
    state = get_skill_manager_state()
    return state.unregister_skill(name)


def get_skill_stats() -> dict:
    """Get skill manager statistics.

    Returns:
        Dictionary with skill statistics
    """
    config = get_skill_manager_config()
    state = get_skill_manager_state()

    skills = state.list_skills()
    builtin_count = sum(1 for s in skills if s.source == "builtin")
    custom_count = sum(1 for s in skills if s.source == "custom")

    return {
        "enabled": config.enabled,
        "total_skills": len(skills),
        "builtin_skills": builtin_count,
        "custom_skills": custom_count,
        "total_executions": state.total_executions,
        "failed_executions": state.failed_executions,
        "execution_history_size": len(state.execution_history),
    }
