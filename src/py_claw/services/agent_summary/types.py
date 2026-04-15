"""
AgentSummary types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class AgentActivityType(str, Enum):
    """Types of agent activities."""

    TOOL_CALL = "tool_call"
    MESSAGE = "message"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    ERROR = "error"
    COMPACT = "compact"


@dataclass(frozen=True, slots=True)
class AgentActivity:
    """A single agent activity."""

    timestamp: datetime
    activity_type: AgentActivityType
    description: str
    duration_ms: int | None = None
    success: bool = True
    metadata: dict | None = None


@dataclass(frozen=True, slots=True)
class AgentMetrics:
    """Metrics for an agent."""

    total_activities: int = 0
    successful_activities: int = 0
    failed_activities: int = 0
    total_duration_ms: int = 0
    tools_used: dict[str, int] | None = None
    tasks_completed: int = 0
    tasks_failed: int = 0


@dataclass(frozen=True, slots=True)
class AgentSummary:
    """Summary of agent activities."""

    agent_name: str | None
    metrics: AgentMetrics
    recent_activities: list[AgentActivity]
    recommendations: list[str]
    generated_at: datetime


@dataclass
class AgentSummaryState:
    """State for agent summary service."""

    activities: list[AgentActivity] = field(default_factory=list)
    metrics_by_agent: dict[str, AgentMetrics] = field(default_factory=dict)
    _lock: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import threading
        if self._lock is None:
            self._lock = threading.RLock()

    def record_activity(self, activity: AgentActivity) -> None:
        """Record a new activity."""
        with self._lock:
            self.activities.append(activity)
            # Keep only recent activities
            if len(self.activities) > 1000:
                self.activities = self.activities[-500:]


# Global state
_state: AgentSummaryState | None = None


def get_agent_summary_state() -> AgentSummaryState:
    """Get the global agent summary state."""
    global _state
    if _state is None:
        _state = AgentSummaryState()
    return _state
