"""
Skill discovery types.

Type definitions for dynamic/conditional skill discovery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.skills import DiscoveredSkill


class SkillActivationType(str, Enum):
    """How a skill is activated."""
    ALWAYS = "always"
    CONDITIONAL = "conditional"
    DYNAMIC = "dynamic"


@dataclass(frozen=True, slots=True)
class SkillCondition:
    """Condition for conditional skill activation (paths frontmatter)."""
    glob_patterns: list[str] | None = None  # from paths: frontmatter
    # Additional conditions can be added here as needed

    @classmethod
    def from_paths_list(cls, paths: list[str]) -> SkillCondition:
        """Create a SkillCondition from a paths list."""
        # Strip /** suffix, ** suffix, and trailing slashes from patterns
        cleaned = []
        for p in paths:
            stripped = p
            original = p
            # Strip trailing /**
            if stripped.endswith("/**"):
                stripped = stripped[:-3]
            elif stripped.endswith("/**/"):
                stripped = stripped[:-4]
            # Strip trailing **
            if stripped.endswith("**"):
                stripped = stripped[:-2]
            # Strip trailing slashes
            stripped = stripped.rstrip("/")
            # If original had /** suffix (recursive pattern), treat as unconditional
            if original.endswith("/**") or original.endswith("/**/"):
                continue  # recursive patterns are match-all
            if stripped == "**":
                continue  # match-all, treat as unconditional
            if stripped:
                cleaned.append(stripped)
        if not cleaned:
            return cls(glob_patterns=None)
        return cls(glob_patterns=cleaned)


@dataclass
class DiscoveredSkillState:
    """Runtime state associated with a discovered skill."""
    skill: "DiscoveredSkill"
    activation_type: SkillActivationType = SkillActivationType.ALWAYS
    condition: SkillCondition | None = None
    is_active: bool = True  # always and dynamic are active; conditional starts False
