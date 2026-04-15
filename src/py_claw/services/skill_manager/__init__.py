"""
SkillManager service.

Manages built-in and custom skills.
"""
from py_claw.services.skill_manager.config import (
    BUILTIN_SKILL_DEFINITIONS,
    SkillDefinition,
    SkillManagerConfig,
    get_skill_manager_config,
    set_skill_manager_config,
)
from py_claw.services.skill_manager.service import (
    execute_skill,
    get_skill,
    get_skill_stats,
    initialize_skills,
    list_skills,
    register_custom_skill,
    search_skills,
    unregister_skill,
)
from py_claw.services.skill_manager.types import (
    SkillExecution,
    SkillManagerState,
    SkillMetadata,
    SkillStatus,
    get_skill_manager_state,
)


__all__ = [
    "SkillDefinition",
    "SkillManagerConfig",
    "SkillMetadata",
    "SkillExecution",
    "SkillStatus",
    "BUILTIN_SKILL_DEFINITIONS",
    "get_skill_manager_config",
    "set_skill_manager_config",
    "initialize_skills",
    "get_skill",
    "list_skills",
    "search_skills",
    "execute_skill",
    "register_custom_skill",
    "unregister_skill",
    "get_skill_stats",
    "get_skill_manager_state",
]
