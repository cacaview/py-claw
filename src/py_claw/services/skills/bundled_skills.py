"""
Bundled skills registry and management.

Provides registration and retrieval of bundled skills that are
compiled into the application. These skills are typically
reference skills, verification skills, and other built-in
functionality.

Reference: ClaudeCode-main/src/skills/bundledSkills.ts
           ClaudeCode-main/src/skills/bundled/index.ts
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .types import SkillInfo


@dataclass
class BundledSkillDefinition:
    """Definition of a bundled skill."""
    name: str
    description: str
    content: str
    source: str = "bundled"
    argument_hint: str | None = None
    when_to_use: str | None = None
    allowed_tools: list[str] | None = None
    model: str | None = None
    user_invocable: bool = True


# Bundled skill registry
_bundled_skills: dict[str, BundledSkillDefinition] = {}
_bundled_root: str | None = None


def get_bundled_root() -> str:
    """
    Get the root directory for bundled skills.

    Returns:
        Path to the bundled skills root directory
    """
    global _bundled_root
    if _bundled_root is None:
        # Default bundled root - can be overridden by environment
        _bundled_root = os.environ.get(
            "CLAUDE_BUNDLED_SKILLS_ROOT",
            str(Path(__file__).parent / "bundled")
        )
    return _bundled_root


def set_bundled_root(root: str) -> None:
    """Set the bundled skills root directory."""
    global _bundled_root
    _bundled_root = root


def register_bundled_skill(skill: BundledSkillDefinition) -> None:
    """
    Register a bundled skill.

    Args:
        skill: The bundled skill definition to register
    """
    _bundled_skills[skill.name] = skill


def get_bundled_skill(name: str) -> BundledSkillDefinition | None:
    """
    Get a bundled skill by name.

    Args:
        name: Skill name

    Returns:
        BundledSkillDefinition if found, None otherwise
    """
    return _bundled_skills.get(name)


def list_bundled_skills() -> list[BundledSkillDefinition]:
    """
    List all registered bundled skills.

    Returns:
        List of bundled skill definitions
    """
    return sorted(_bundled_skills.values(), key=lambda s: s.name)


def get_bundled_skill_content(name: str) -> str | None:
    """
    Get the content of a bundled skill.

    Args:
        name: Skill name

    Returns:
        Skill content as string, or None if not found
    """
    skill = get_bundled_skill(name)
    return skill.content if skill else None


def resolve_skill_file_path(skill_name: str, filename: str) -> Path | None:
    """
    Resolve a file path within a bundled skill directory.

    This function prevents path traversal attacks by validating
    that the resolved path stays within the bundled skills root.

    Args:
        skill_name: Name of the skill
        filename: Requested filename within the skill

    Returns:
        Resolved Path if valid, None if path would escape root
    """
    import re

    skill_root = Path(get_bundled_root()) / skill_name

    # Block absolute paths and path traversal
    if os.path.isabs(filename) or filename.startswith(".."):
        return None

    # Resolve and verify the path stays within skill root
    try:
        resolved = (skill_root / filename).resolve()
        if resolved.is_relative_to(skill_root):
            return resolved
    except (ValueError, OSError):
        pass

    return None


def clear_bundled_skills() -> None:
    """Clear all registered bundled skills. Used for testing."""
    global _bundled_skills
    _bundled_skills.clear()


# Built-in bundled skills registry
_builtin_skill_factories: dict[str, Callable[[], BundledSkillDefinition | None]] = {}


def register_builtin_skill_factory(
    name: str,
    factory: Callable[[], BundledSkillDefinition | None]
) -> None:
    """
    Register a factory function for creating a builtin skill.

    The factory is called lazily when the skill is first requested.

    Args:
        name: Skill name
        factory: Factory function that creates the skill definition
    """
    _builtin_skill_factories[name] = factory


def get_builtin_skill(name: str) -> BundledSkillDefinition | None:
    """
    Get a builtin skill by name.

    Args:
        name: Skill name

    Returns:
        BundledSkillDefinition if found and factory succeeds, None otherwise
    """
    # Check if already loaded
    if name in _bundled_skills:
        return _bundled_skills[name]

    # Check if we have a factory
    factory = _builtin_skill_factories.get(name)
    if factory is None:
        return None

    # Call factory and register result
    try:
        skill = factory()
        if skill:
            _bundled_skills[name] = skill
            return skill
    except Exception:
        pass

    return None


def initialize_builtin_skills() -> None:
    """Initialize all builtin skills by calling their factories."""
    for name in list(_builtin_skill_factories.keys()):
        get_builtin_skill(name)


def to_skill_info(skill: BundledSkillDefinition) -> SkillInfo:
    """
    Convert a BundledSkillDefinition to a SkillInfo.

    Args:
        skill: The bundled skill definition

    Returns:
        SkillInfo suitable for the skills catalog
    """
    return SkillInfo(
        name=skill.name,
        description=skill.description,
        source=skill.source,
        content=skill.content,
        argument_hint=skill.argument_hint,
        when_to_use=skill.when_to_use,
        allowed_tools=skill.allowed_tools,
        model=skill.model,
    )
