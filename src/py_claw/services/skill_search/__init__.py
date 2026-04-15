"""
SkillSearch service.

Searches and discovers skills based on query.
"""
from py_claw.services.skill_search.config import (
    BUILTIN_SKILLS,
    SkillSearchConfig,
    get_skill_search_config,
    set_skill_search_config,
)
from py_claw.services.skill_search.service import (
    clear_search_cache,
    get_all_skills,
    get_skill_search_stats,
    search_builtin_skills,
    search_custom_skills,
    search_skills,
)
from py_claw.services.skill_search.types import (
    SearchResult,
    SkillHit,
    SkillSearchState,
    get_skill_search_state,
)


__all__ = [
    "SkillSearchConfig",
    "SkillHit",
    "SearchResult",
    "SkillSearchState",
    "BUILTIN_SKILLS",
    "get_skill_search_config",
    "set_skill_search_config",
    "search_skills",
    "search_builtin_skills",
    "search_custom_skills",
    "get_all_skills",
    "clear_search_cache",
    "get_skill_search_stats",
    "get_skill_search_state",
]
