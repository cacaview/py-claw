"""
SkillSearch service.

Searches and discovers skills based on query.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING

from py_claw.services.skill_search.config import (
    BUILTIN_SKILLS,
    get_skill_search_config,
)

from .types import SearchResult, SkillHit, get_skill_search_state

if TYPE_CHECKING:
    from py_claw.skills import DiscoveredSkill


def _compute_query_hash(query: str) -> str:
    """Compute hash of query for caching."""
    return hashlib.md5(query.lower().encode("utf-8")).hexdigest()[:16]


def _score_skill_match(skill_name: str, skill_info: dict, query: str) -> float:
    """Score how well a skill matches a query.

    Returns a score between 0.0 and 1.0.
    """
    query_lower = query.lower()
    name_lower = skill_name.lower()
    desc_lower = skill_info.get("description", "").lower()

    score = 0.0

    # Exact name match
    if name_lower == query_lower:
        score = 1.0
    # Name starts with query
    elif name_lower.startswith(query_lower):
        score = 0.8
    # Name contains query
    elif query_lower in name_lower:
        score = 0.6
    # Description contains query
    elif query_lower in desc_lower:
        score = 0.4
    # Query words in name or description
    else:
        query_words = set(query_lower.split())
        name_words = set(name_lower.split())
        desc_words = set(desc_lower.split())

        word_overlap = len(query_words & name_words) / max(len(query_words), 1)
        desc_overlap = len(query_words & desc_words) / max(len(query_words), 1)

        score = max(word_overlap * 0.5, desc_overlap * 0.3)

    return score


def search_builtin_skills(query: str) -> list[SkillHit]:
    """Search built-in skills.

    Args:
        query: Search query

    Returns:
        List of matching SkillHit objects
    """
    config = get_skill_search_config()

    if not config.include_builtin:
        return []

    hits: list[SkillHit] = []

    for name, info in BUILTIN_SKILLS.items():
        score = _score_skill_match(name, info, query)
        if score > 0.1:  # Minimum threshold
            hits.append(SkillHit(
                name=name,
                description=info.get("description", ""),
                source="builtin",
                relevance_score=score,
                argument_hint=info.get("argument_hint"),
                when_to_use=info.get("when_to_use"),
            ))

    # Sort by relevance
    hits.sort(key=lambda h: h.relevance_score, reverse=True)
    return hits


def search_custom_skills(query: str) -> list[SkillHit]:
    """Search custom/skills directory skills.

    Args:
        query: Search query

    Returns:
        List of matching SkillHit objects
    """
    config = get_skill_search_config()

    if not config.include_custom:
        return []

    hits: list[SkillHit] = []
    skill_dirs = [Path(".claude/skills"), Path("~/.claude/skills").expanduser()]

    for skill_dir in skill_dirs:
        if not skill_dir.exists():
            continue

        for skill_path in skill_dir.iterdir():
            if not skill_path.is_dir():
                continue

            skill_name = skill_path.name
            score = _score_skill_match(skill_name, {"description": ""}, query)
            if score > 0.1:
                # Try to read skill metadata
                skill_md = skill_path / "SKILL.md"
                description = ""
                argument_hint = None
                when_to_use = None

                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding="utf-8")
                        for line in content.split("\n"):
                            if line.startswith("description:"):
                                description = line.split(":", 1)[1].strip()
                            elif line.startswith("argument-hint:"):
                                argument_hint = line.split(":", 1)[1].strip()
                            elif line.startswith("when-to-use:"):
                                when_to_use = line.split(":", 1)[1].strip()
                    except Exception:
                        pass

                hits.append(SkillHit(
                    name=skill_name,
                    description=description or f"Custom skill: {skill_name}",
                    source="custom",
                    relevance_score=score,
                    argument_hint=argument_hint,
                    when_to_use=when_to_use,
                ))

    hits.sort(key=lambda h: h.relevance_score, reverse=True)
    return hits


def search_skills(query: str) -> SearchResult:
    """Search all skills (built-in and custom).

    Args:
        query: Search query

    Returns:
        SearchResult with matching skills
    """
    config = get_skill_search_config()
    state = get_skill_search_state()
    start_time = time.time()

    if not config.enabled:
        return SearchResult(
            query=query,
            hits=[],
            total_hits=0,
            search_time_ms=(time.time() - start_time) * 1000,
        )

    # Check cache
    query_hash = _compute_query_hash(query)
    if config.cache_enabled:
        cached = state.get_cached(query_hash, config.cache_ttl)
        if cached is not None:
            return SearchResult(
                query=query,
                hits=cached[:config.max_results],
                total_hits=len(cached),
                search_time_ms=(time.time() - start_time) * 1000,
                from_cache=True,
            )

    # Search built-in skills
    builtin_hits = search_builtin_skills(query)

    # Search custom skills
    custom_hits = search_custom_skills(query)

    # Combine and deduplicate (prefer builtin if same name)
    all_hits: list[SkillHit] = []
    seen_names: set[str] = set()

    for hit in builtin_hits + custom_hits:
        if hit.name not in seen_names:
            all_hits.append(hit)
            seen_names.add(hit.name)

    # Sort by relevance
    all_hits.sort(key=lambda h: h.relevance_score, reverse=True)

    # Limit results
    results = all_hits[:config.max_results]

    # Cache results
    if config.cache_enabled:
        state.set_cached(query_hash, all_hits)

    return SearchResult(
        query=query,
        hits=results,
        total_hits=len(all_hits),
        search_time_ms=(time.time() - start_time) * 1000,
        from_cache=False,
    )


def get_all_skills() -> list[SkillHit]:
    """Get all available skills.

    Returns:
        List of all SkillHit objects
    """
    config = get_skill_search_config()
    hits: list[SkillHit] = []

    if config.include_builtin:
        for name, info in BUILTIN_SKILLS.items():
            hits.append(SkillHit(
                name=name,
                description=info.get("description", ""),
                source="builtin",
                relevance_score=1.0,
                argument_hint=info.get("argument_hint"),
                when_to_use=info.get("when_to_use"),
            ))

    if config.include_custom:
        custom_hits = search_custom_skills("")
        hits.extend(custom_hits)

    return hits


def clear_search_cache() -> None:
    """Clear the search cache."""
    state = get_skill_search_state()
    state.clear_cache()


def get_skill_search_stats() -> dict:
    """Get skill search statistics.

    Returns:
        Dictionary with search statistics
    """
    config = get_skill_search_config()
    state = get_skill_search_state()

    return {
        "enabled": config.enabled,
        "max_results": config.max_results,
        "include_builtin": config.include_builtin,
        "include_custom": config.include_custom,
        "cache_enabled": config.cache_enabled,
        "total_searches": state.total_searches,
        "cache_size": len(state.search_cache),
        "builtin_skills_count": len(BUILTIN_SKILLS),
    }
