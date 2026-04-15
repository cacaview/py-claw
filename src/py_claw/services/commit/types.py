"""Commit service types - git commit attribution and analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AttributionState:
    """Attribution state for tracking Claude's contributions to files."""
    file_states: dict[str, FileAttributionState] = field(default_factory=dict)
    session_baselines: dict[str, ContentBaseline] = field(default_factory=dict)
    surface: str = "cli"
    starting_head_sha: str | None = None
    prompt_count: int = 0
    prompt_count_at_last_commit: int = 0
    permission_prompt_count: int = 0
    permission_prompt_count_at_last_commit: int = 0
    escape_count: int = 0
    escape_count_at_last_commit: int = 0


@dataclass
class FileAttributionState:
    """Per-file attribution state."""
    content_hash: str
    claude_contribution: int
    mtime: float


@dataclass
class ContentBaseline:
    """Session baseline for net change calculation."""
    content_hash: str
    mtime: float


@dataclass
class AttributionSummary:
    """Summary of Claude's contribution for a commit."""
    claude_percent: int
    claude_chars: int
    human_chars: int
    surfaces: list[str]


@dataclass
class FileAttribution:
    """Per-file attribution details."""
    claude_chars: int
    human_chars: int
    percent: int
    surface: str


@dataclass
class AttributionData:
    """Full attribution data for commit."""
    version: int = 1
    summary: AttributionSummary | None = None
    files: dict[str, FileAttribution] = field(default_factory=dict)
    surface_breakdown: dict[str, Any] = field(default_factory=dict)
    excluded_generated: list[str] = field(default_factory=list)
    sessions: list[str] = field(default_factory=list)


@dataclass
class CommitAnalysisResult:
    """Result of analyzing staged changes for commit."""
    staged_files: list[str]
    modified_files: list[str]
    new_files: list[str]
    deleted_files: list[str]
    total_changes: int
    has_staged_changes: bool
    current_branch: str
    recent_commits: list[str]
    is_in_transient_state: bool


@dataclass
class CommitPreparationResult:
    """Result of preparing a commit."""
    ready: bool
    staged_files: list[str]
    analysis: CommitAnalysisResult | None = None
    error_message: str | None = None
    attribution_data: AttributionData | None = None
