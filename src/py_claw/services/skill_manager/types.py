"""
SkillManager types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SkillStatus(str, Enum):
    """Status of a skill."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    """Metadata for a skill."""

    name: str
    description: str
    argument_hint: str | None = None
    when_to_use: str | None = None
    source: str = "builtin"
    version: str | None = None
    author: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillExecution:
    """Result of a skill execution."""

    skill_name: str
    success: bool
    output: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    execution_mode: str = "inline"  # "inline", "fork", "remote"


@dataclass
class SkillManagerState:
    """State for skill manager service."""

    registered_skills: dict[str, SkillMetadata] = field(default_factory=dict)
    execution_history: list[SkillExecution] = field(default_factory=list)
    total_executions: int = 0
    failed_executions: int = 0
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def register_skill(self, metadata: SkillMetadata) -> None:
        """Register a skill."""
        with self._lock:
            self.registered_skills[metadata.name] = metadata

    def unregister_skill(self, name: str) -> bool:
        """Unregister a skill."""
        with self._lock:
            if name in self.registered_skills:
                del self.registered_skills[name]
                return True
            return False

    def get_skill(self, name: str) -> SkillMetadata | None:
        """Get a skill by name."""
        with self._lock:
            return self.registered_skills.get(name)

    def list_skills(self) -> list[SkillMetadata]:
        """List all registered skills."""
        with self._lock:
            return list(self.registered_skills.values())

    def record_execution(self, execution: SkillExecution) -> None:
        """Record a skill execution."""
        with self._lock:
            self.execution_history.append(execution)
            self.total_executions += 1
            if not execution.success:
                self.failed_executions += 1
            # Keep only recent history
            if len(self.execution_history) > 100:
                self.execution_history = self.execution_history[-50:]


# Global state
_state: SkillManagerState | None = None


def get_skill_manager_state() -> SkillManagerState:
    """Get the global skill manager state."""
    global _state
    if _state is None:
        _state = SkillManagerState()
    return _state
