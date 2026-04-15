"""Skills service - unified skill management facade.

This module provides a unified interface for skill operations, coordinating
skill discovery, skill management, and skill search.

Reference: ClaudeCode-main/src/services/skills/ (stub)
          ClaudeCode-main/src/skills/loadSkillsDir.ts (actual loading)
"""

from py_claw.services.skills.service import (
    initialize_skills_service,
    get_skill,
    list_skills,
    search_skills,
    get_skills_stats,
    get_all_skill_names,
    skill_exists,
    reset_skills_service,
)
from py_claw.services.skills.types import (
    SkillInfo,
    SkillsServiceState,
    SkillSearchResult,
    SkillsStats,
)
from py_claw.services.skills.mcp_skills import (
    register_mcp_skill_builder,
    get_mcp_skill_builder,
    get_registered_builder_names,
    fetch_mcp_skills_for_client,
    is_mcp_skill,
    get_mcp_skill_tools,
)
from py_claw.services.skills.bundled_skills import (
    BundledSkillDefinition,
    get_bundled_root,
    set_bundled_root,
    register_bundled_skill,
    get_bundled_skill,
    list_bundled_skills,
    get_bundled_skill_content,
    resolve_skill_file_path,
    clear_bundled_skills,
    register_builtin_skill_factory,
    get_builtin_skill,
    initialize_builtin_skills,
    to_skill_info,
)

__all__ = [
    # Types
    "SkillInfo",
    "SkillsServiceState",
    "SkillSearchResult",
    "SkillsStats",
    # Service
    "initialize_skills_service",
    "get_skill",
    "list_skills",
    "search_skills",
    "get_skills_stats",
    "get_all_skill_names",
    "skill_exists",
    "reset_skills_service",
    # MCP skills
    "register_mcp_skill_builder",
    "get_mcp_skill_builder",
    "get_registered_builder_names",
    "fetch_mcp_skills_for_client",
    "is_mcp_skill",
    "get_mcp_skill_tools",
    # Bundled skills
    "BundledSkillDefinition",
    "get_bundled_root",
    "set_bundled_root",
    "register_bundled_skill",
    "get_bundled_skill",
    "list_bundled_skills",
    "get_bundled_skill_content",
    "resolve_skill_file_path",
    "clear_bundled_skills",
    "register_builtin_skill_factory",
    "get_builtin_skill",
    "initialize_builtin_skills",
    "to_skill_info",
]
