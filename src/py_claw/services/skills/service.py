"""Skills service - unified skill management facade.

This service coordinates skill discovery, skill management, and skill search
to provide a unified interface for skill operations.

Reference: ClaudeCode-main/src/services/skills/ (stub implementation)
           ClaudeCode-main/src/skills/loadSkillsDir.ts (actual skill loading)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from .types import (
    SkillInfo,
    SkillsServiceState,
    SkillSearchResult,
    SkillsStats,
)

if TYPE_CHECKING:
    from py_claw.skills import DiscoveredSkill

# Global state
_skills_service_state = SkillsServiceState()
_skill_catalog: dict[str, SkillInfo] = {}


def _get_skills_service_state() -> SkillsServiceState:
    """Get the global skills service state."""
    return _skills_service_state


def _discovered_skill_to_info(skill: DiscoveredSkill) -> SkillInfo:
    """Convert a DiscoveredSkill to SkillInfo."""
    return SkillInfo(
        name=skill.name,
        description=skill.description,
        source=skill.source,
        skill_path=skill.skill_path,
        skill_root=skill.skill_root,
        content=skill.content,
        argument_hint=skill.argument_hint,
        when_to_use=skill.when_to_use,
        version=skill.version,
        model=skill.model,
        allowed_tools=skill.allowed_tools,
        effort=skill.effort.value if hasattr(skill.effort, 'value') else skill.effort,
        user_invocable=skill.user_invocable,
        disable_model_invocation=skill.disable_model_invocation,
        paths=skill.paths,
        hooks=skill.hooks,
        execution_context=skill.execution_context,
        agent=skill.agent,
        display_name=skill.display_name,
        argument_names=skill.argument_names,
        shell=skill.shell,
        aliases=skill.aliases,
    )


def initialize_skills_service(
    *,
    cwd: str | None = None,
    home_dir: str | None = None,
    settings_skills: list[str] | None = None,
) -> None:
    """
    Initialize the skills service.

    Loads all available skills from standard locations:
    - User skills (~/.claude/skills)
    - Project skills (<cwd>/.claude/skills)
    - Policy skills (CLAUDE_CODE_POLICY_DIR)
    - Bundled skills

    Args:
        cwd: Current working directory (project root)
        home_dir: User home directory
        settings_skills: Skills explicitly listed in settings
    """
    global _skill_catalog, _skills_service_state

    if _skills_service_state.initialized:
        return

    # Import here to avoid circular dependencies
    from py_claw.skills import discover_local_skills

    # Discover all local skills
    cwd_value = cwd or str(Path.cwd())
    home_value = home_dir or str(Path.home())

    discovered = discover_local_skills(
        cwd=cwd_value,
        home_dir=home_value,
        settings_skills=settings_skills,
    )

    # Build catalog
    _skill_catalog.clear()
    for skill in discovered:
        info = _discovered_skill_to_info(skill)
        _skill_catalog[skill.name] = info

    # Load bundled skills (from bundled_skills module)
    try:
        from py_claw.services.skills.bundled_skills import (
            list_bundled_skills,
            to_skill_info,
        )
        from py_claw.services.skills.bundled import init_bundled_skills

        # Initialize bundled skills first
        init_bundled_skills()

        for bundled in list_bundled_skills():
            if bundled.name not in _skill_catalog:
                _skill_catalog[bundled.name] = to_skill_info(bundled)
    except Exception:
        pass  # Bundled skills may not be fully initialized

    # Also load skill manager's built-in skills
    try:
        from py_claw.services.skill_manager import list_skills as list_manager_skills

        for metadata in list_manager_skills():
            if metadata.name not in _skill_catalog:
                _skill_catalog[metadata.name] = SkillInfo(
                    name=metadata.name,
                    description=metadata.description,
                    source=metadata.source,
                    argument_hint=metadata.argument_hint,
                    when_to_use=metadata.when_to_use,
                )
    except Exception:
        pass  # Skill manager may not be fully initialized

    _skills_service_state.initialized = True


def get_skill(name: str) -> SkillInfo | None:
    """
    Get a skill by name.

    Args:
        name: Skill name

    Returns:
        SkillInfo if found, None otherwise
    """
    return _skill_catalog.get(name)


def list_skills(source: str | None = None) -> list[SkillInfo]:
    """
    List all available skills.

    Args:
        source: Optional filter by source

    Returns:
        List of SkillInfo objects
    """
    skills = list(_skill_catalog.values())

    if source:
        skills = [s for s in skills if s.source == source]

    return sorted(skills, key=lambda s: s.name)


def search_skills(query: str, max_results: int = 20) -> SkillSearchResult:
    """
    Search skills by name or description.

    Args:
        query: Search query
        max_results: Maximum number of results to return

    Returns:
        SkillSearchResult with matching skills
    """
    global _skills_service_state

    start_time = time.time()
    _skills_service_state.total_searches += 1

    query_lower = query.lower()
    hits: list[SkillInfo] = []

    # Search by name and description
    for skill in _skill_catalog.values():
        score = 0.0

        # Exact name match
        if skill.name.lower() == query_lower:
            score = 1.0
        # Name starts with query
        elif skill.name.lower().startswith(query_lower):
            score = 0.8
        # Name contains query
        elif query_lower in skill.name.lower():
            score = 0.6
        # Description contains query
        elif query_lower in skill.description.lower():
            score = 0.4
        # Query words in name or description
        else:
            query_words = set(query_lower.split())
            name_words = set(skill.name.lower().split())
            desc_words = set(skill.description.lower().split())

            word_overlap = len(query_words & name_words) / max(len(query_words), 1)
            desc_overlap = len(query_words & desc_words) / max(len(query_words), 1)

            score = max(word_overlap * 0.5, desc_overlap * 0.3)

        if score > 0.1:
            hits.append(skill)

    # Sort by relevance
    hits.sort(key=lambda s: (
        # Sort by score first (descending), then by name
        (
            1.0 if s.name.lower() == query_lower else
            0.8 if s.name.lower().startswith(query_lower) else
            0.6 if query_lower in s.name.lower() else
            0.4 if query_lower in s.description.lower() else
            0.0
        ),
        s.name,
    ), reverse=True)

    # Limit results
    results = hits[:max_results]
    search_time_ms = (time.time() - start_time) * 1000

    _skills_service_state.last_search_time_ms = search_time_ms
    _skills_service_state.cache_size = len(_skill_catalog)

    return SkillSearchResult(
        query=query,
        hits=results,
        total_hits=len(hits),
        search_time_ms=search_time_ms,
        from_cache=False,  # We don't cache individual searches
    )


def get_skills_stats() -> SkillsStats:
    """
    Get skills service statistics.

    Returns:
        SkillsStats with service statistics
    """
    state = _get_skills_service_state()
    skills = list(_skill_catalog.values())

    builtin_count = sum(1 for s in skills if s.source == "builtin")
    custom_count = sum(1 for s in skills if s.source in ("userSettings", "projectSettings"))
    installed_count = sum(1 for s in skills if s.source == "installed")

    # Get detailed stats from sub-services
    search_stats = {}
    discovery_stats = {}

    try:
        from py_claw.services.skill_search import get_skill_search_stats
        search_stats = get_skill_search_stats()
    except Exception:
        pass

    try:
        from py_claw.services.skill_manager import get_skill_stats
        discovery_stats = get_skill_stats()
    except Exception:
        pass

    return SkillsStats(
        enabled=True,
        initialized=state.initialized,
        total_skills=len(skills),
        builtin_skills=builtin_count,
        custom_skills=custom_count,
        installed_skills=installed_count,
        total_searches=state.total_searches,
        cache_size=state.cache_size,
        search_stats=search_stats,
        discovery_stats=discovery_stats,
    )


def get_all_skill_names() -> list[str]:
    """
    Get all skill names.

    Returns:
        List of skill names
    """
    return sorted(_skill_catalog.keys())


def skill_exists(name: str) -> bool:
    """
    Check if a skill exists.

    Args:
        name: Skill name

    Returns:
        True if skill exists
    """
    return name in _skill_catalog


def reset_skills_service() -> None:
    """Reset the skills service state (for testing)."""
    global _skill_catalog, _skills_service_state
    _skill_catalog.clear()
    _skills_service_state = SkillsServiceState()
