"""Types for insights service."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SessionInsight:
    """A single insight from session analysis."""

    category: str
    title: str
    description: str
    metric: float | None = None
    unit: str | None = None


@dataclass(slots=True)
class UsageStats:
    """Top-level usage statistics."""

    total_sessions: int
    total_messages: int
    total_tokens: int
    total_cost: float
    average_session_length: float


@dataclass(slots=True)
class InsightsConfig:
    """Configuration for insights service."""

    insights_enabled: bool = True
    collection_enabled: bool = True
    transcript_summary_char_limit: int = 30_000
    transcript_summary_chunk_size: int = 25_000
    max_sessions: int = 100


@dataclass(slots=True)
class SessionLog:
    """Raw parsed session log."""

    session_id: str
    file_path: str
    project_path: str | None
    mtime: float
    entries: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SessionMeta:
    """Derived per-session metadata used by the insights pipeline."""

    session_id: str
    file_path: str
    project_path: str | None
    user_message_count: int = 0
    assistant_message_count: int = 0
    total_messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_minutes: float = 0.0
    tool_counts: dict[str, int] = field(default_factory=dict)
    languages: dict[str, int] = field(default_factory=dict)
    files_modified: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    git_commits: int = 0
    git_pushes: int = 0
    message_hours: list[int] = field(default_factory=list)
    message_timestamps: list[float] = field(default_factory=list)
    active_days: list[str] = field(default_factory=list)
    first_prompt: str | None = None
    custom_title: str | None = None
    tag: str | None = None
    brief_summary: str | None = None
    summary_source: str = "raw"


@dataclass(slots=True)
class SessionFacet:
    """Facet extraction result for a session."""

    session_id: str
    underlying_goal: str
    goal_categories: list[str] = field(default_factory=list)
    outcome: str = "unknown"
    friction_counts: dict[str, int] = field(default_factory=dict)
    brief_summary: str = ""
    user_instructions_to_claude: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MultiClaudingStats:
    """Overlap statistics for concurrent/multi-session activity."""

    overlap_events: int = 0
    sessions_involved: int = 0
    user_messages_during: int = 0


@dataclass(slots=True)
class NarrativeSections:
    """Human-readable narrative sections derived from aggregates."""

    at_a_glance: str = ""
    what_works: str = ""
    friction_analysis: str = ""
    suggestions: str = ""


@dataclass(slots=True)
class AggregatedInsightsData:
    """Aggregated insights data across sessions and facets."""

    total_sessions: int
    total_messages: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost: float
    average_session_length: float
    total_duration_minutes: float
    git_commits: int
    git_pushes: int
    lines_added: int
    lines_removed: int
    files_modified: int
    tool_counts: dict[str, int] = field(default_factory=dict)
    languages: dict[str, int] = field(default_factory=dict)
    projects: dict[str, int] = field(default_factory=dict)
    active_days: int = 0
    active_hours: dict[int, int] = field(default_factory=dict)
    goal_categories: dict[str, int] = field(default_factory=dict)
    outcomes: dict[str, int] = field(default_factory=dict)
    friction_counts: dict[str, int] = field(default_factory=dict)
    summaries: list[str] = field(default_factory=list)
    user_instructions: list[str] = field(default_factory=list)
    multi_clauding: MultiClaudingStats = field(default_factory=MultiClaudingStats)
    narratives: NarrativeSections = field(default_factory=NarrativeSections)


@dataclass(slots=True)
class InsightsResult:
    """Result of insights analysis."""

    success: bool
    message: str
    insights: list[SessionInsight] | None = None
    usage_stats: UsageStats | None = None
    sessions: list[SessionMeta] | None = None
    facets: list[SessionFacet] | None = None
    aggregated: AggregatedInsightsData | None = None
