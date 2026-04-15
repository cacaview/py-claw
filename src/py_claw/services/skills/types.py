"""Skills service types - unified skill management types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillInfo:
    """Complete skill information with metadata."""
    name: str
    description: str
    source: str  # 'userSettings', 'projectSettings', 'builtin', 'installed', 'policy', 'mcp'
    skill_path: str | None = None
    skill_root: str | None = None
    content: str | None = None
    argument_hint: str | None = None
    when_to_use: str | None = None
    version: str | None = None
    model: str | None = None
    allowed_tools: list[str] | None = None
    effort: str | None = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    # Conditional activation
    paths: list[str] | None = None
    # Hooks
    hooks: dict | None = None
    # Execution context
    execution_context: str | None = None
    agent: str | None = None
    display_name: str | None = None
    argument_names: list[str] | None = None
    shell: str | None = None
    aliases: list[str] | None = None


@dataclass
class SkillsServiceState:
    """Global state for skills service."""
    initialized: bool = False
    total_searches: int = 0
    cache_size: int = 0
    last_search_time_ms: float = 0.0


@dataclass
class SkillSearchResult:
    """Result from a skill search."""
    query: str
    hits: list[SkillInfo]
    total_hits: int
    search_time_ms: float
    from_cache: bool = False


@dataclass
class SkillsStats:
    """Skills service statistics."""
    enabled: bool
    initialized: bool
    total_skills: int
    builtin_skills: int
    custom_skills: int
    installed_skills: int
    total_searches: int
    cache_size: int
    search_stats: dict[str, Any] = field(default_factory=dict)
    discovery_stats: dict[str, Any] = field(default_factory=dict)
