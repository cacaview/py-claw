"""
Skill discovery state management.

Thread-safe global state for dynamic and conditional skill discovery.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_claw.skills import DiscoveredSkill
    from .types import DiscoveredSkillState, SkillActivationType, SkillCondition


@dataclass
class SkillDiscoveryState:
    """Thread-safe global state for skill discovery."""

    # Skills pending conditional activation (name -> skill)
    conditional_skills: dict[str, "DiscoveredSkill"] = field(default_factory=dict)

    # Activated conditional/dynamic skills (name -> skill)
    dynamic_skills: dict[str, "DiscoveredSkill"] = field(default_factory=dict)

    # Directories already walked during discovery (resolved paths)
    discovered_dirs: set[str] = field(default_factory=set)

    # Mapping of skill name -> SkillCondition for conditional skills
    skill_conditions: dict[str, "SkillCondition"] = field(default_factory=dict)

    # Mapping of skill name -> full state for all discovered skills
    all_skills: dict[str, "DiscoveredSkillState"] = field(default_factory=dict)

    _lock: threading.RLock = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_lock", threading.RLock())

    # ------------------------------------------------------------------
    # Conditional skills
    # ------------------------------------------------------------------

    def add_conditional_skill(self, name: str, skill: "DiscoveredSkill", condition: "SkillCondition") -> None:
        """Add a pending conditional skill."""
        with self._lock:
            self.conditional_skills[name] = skill
            self.skill_conditions[name] = condition
            self.all_skills[name] = DiscoveredSkillState(
                skill=skill,
                activation_type=SkillActivationType.CONDITIONAL,
                condition=condition,
                is_active=False,
            )

    def activate_skill(self, name: str) -> "DiscoveredSkill | None":
        """Activate a conditional skill. Returns the skill if activated."""
        with self._lock:
            if name in self.conditional_skills:
                skill = self.conditional_skills.pop(name)
                self.dynamic_skills[name] = skill
                if name in self.all_skills:
                    self.all_skills[name].is_active = True
                return skill
            return None

    def add_always_skill(self, name: str, skill: "DiscoveredSkill") -> None:
        """Add an always-on skill."""
        with self._lock:
            self.all_skills[name] = DiscoveredSkillState(
                skill=skill,
                activation_type=SkillActivationType.ALWAYS,
                is_active=True,
            )

    def add_dynamic_skill(self, name: str, skill: "DiscoveredSkill") -> None:
        """Add a dynamically discovered skill."""
        with self._lock:
            self.dynamic_skills[name] = skill
            self.all_skills[name] = DiscoveredSkillState(
                skill=skill,
                activation_type=SkillActivationType.DYNAMIC,
                is_active=True,
            )

    # ------------------------------------------------------------------
    # Directory tracking
    # ------------------------------------------------------------------

    def add_discovered_dir(self, dir_path: str) -> None:
        """Mark a directory as discovered."""
        with self._lock:
            self.discovered_dirs.add(dir_path)

    def is_dir_discovered(self, dir_path: str) -> bool:
        """Check if a directory has been discovered."""
        with self._lock:
            return dir_path in self.discovered_dirs

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_skills(self) -> dict[str, "DiscoveredSkill"]:
        """Get all currently active skills (always + dynamic)."""
        with self._lock:
            result = {}
            for name, state in self.all_skills.items():
                if state.is_active:
                    result[name] = state.skill
            return result

    def get_conditional_skills(self) -> dict[str, "DiscoveredSkill"]:
        """Get all pending conditional skills."""
        with self._lock:
            return dict(self.conditional_skills)

    def get_dynamic_skills(self) -> dict[str, "DiscoveredSkill"]:
        """Get all activated dynamic skills."""
        with self._lock:
            return dict(self.dynamic_skills)

    def get_all_states(self) -> dict[str, "DiscoveredSkillState"]:
        """Get all skill states."""
        with self._lock:
            return dict(self.all_skills)

    def get_condition(self, name: str) -> "SkillCondition | None":
        """Get the condition for a skill."""
        with self._lock:
            return self.skill_conditions.get(name)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all state."""
        with self._lock:
            self.conditional_skills.clear()
            self.dynamic_skills.clear()
            self.discovered_dirs.clear()
            self.skill_conditions.clear()
            self.all_skills.clear()


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_state: SkillDiscoveryState | None = None


def get_skill_discovery_state() -> SkillDiscoveryState:
    """Get the global skill discovery state."""
    global _state
    if _state is None:
        _state = SkillDiscoveryState()
    return _state


def reset_skill_discovery_state() -> None:
    """Reset the global skill discovery state (for testing)."""
    global _state
    _state = None


# Import here to avoid circular import
from .types import DiscoveredSkillState, SkillActivationType, SkillCondition
