"""
Skill discovery service for dynamic and conditional skill loading.

Supports:
- Always-on skills: loaded immediately on startup
- Conditional skills: activated when matching current file paths
- Dynamic skills: discovered from nested skill directories
- Policy tier: skills from CLAUDE_CODE_POLICY_DIR
- Bare mode: discover skills without project context
"""
from __future__ import annotations

from .types import (
    SkillActivationType,
    SkillCondition,
    DiscoveredSkillState,
)
from .state import (
    SkillDiscoveryState,
    get_skill_discovery_state,
    reset_skill_discovery_state,
)
from .service import (
    SkillDiscoveryService,
    get_skill_discovery_service,
    reset_skill_discovery_service,
)
from .dynamic import (
    discover_skill_dirs_for_paths,
    activate_conditional_skills_for_paths,
    discover_nested_skills_in_dir,
)

__all__ = [
    # Types
    "SkillActivationType",
    "SkillCondition",
    "DiscoveredSkillState",
    # State
    "SkillDiscoveryState",
    "get_skill_discovery_state",
    "reset_skill_discovery_state",
    # Service
    "SkillDiscoveryService",
    "get_skill_discovery_service",
    "reset_skill_discovery_service",
    # Dynamic discovery
    "discover_skill_dirs_for_paths",
    "activate_conditional_skills_for_paths",
    "discover_nested_skills_in_dir",
]
