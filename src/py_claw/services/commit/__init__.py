"""Commit service - git commit analysis and preparation.

Public API for commit attribution tracking and staged change analysis.

Example:
    >>> from py_claw.services.commit import prepare_commit, build_commit_prompt
    >>> result = prepare_commit()
    >>> if result.ready:
    ...     prompt = build_commit_prompt(result.attribution_data)
"""

from .service import (
    create_empty_attribution_state,
    track_file_modification,
    get_staged_files,
    get_git_status,
    get_git_diff,
    get_current_branch,
    get_recent_commits,
    is_git_transient_state,
    analyze_staged_changes,
    prepare_commit,
    build_commit_prompt,
)
from .types import (
    AttributionState,
    AttributionData,
    AttributionSummary,
    FileAttribution,
    FileAttributionState,
    ContentBaseline,
    CommitAnalysisResult,
    CommitPreparationResult,
)

__all__ = [
    # State management
    "create_empty_attribution_state",
    "track_file_modification",
    # Git operations
    "get_staged_files",
    "get_git_status",
    "get_git_diff",
    "get_current_branch",
    "get_recent_commits",
    "is_git_transient_state",
    # Analysis and preparation
    "analyze_staged_changes",
    "prepare_commit",
    "build_commit_prompt",
    # Types
    "AttributionState",
    "AttributionData",
    "AttributionSummary",
    "FileAttribution",
    "FileAttributionState",
    "ContentBaseline",
    "CommitAnalysisResult",
    "CommitPreparationResult",
]
