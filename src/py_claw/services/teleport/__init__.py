"""
Teleport service for CCR (Cloud Code Remote) session management.

Based on ClaudeCode-main/src/utils/teleport/

Features:
- Git state validation
- Git bundle creation and upload
- Environment management
- Session creation, polling, and archival
- OAuth-based authentication
"""
from py_claw.services.teleport.service import (
    archive_remote_session,
    create_and_upload_bundle,
    create_cloud_environment,
    create_git_bundle,
    create_session,
    fetch_environments,
    fetch_session,
    find_git_root,
    get_current_branch,
    get_teleport_info,
    is_transient_error,
    poll_remote_session_events,
    validate_git_state,
    validate_session_repository,
)
from py_claw.services.teleport.types import (
    BundleResult,
    BundleUploadResult,
    Environment,
    EnvironmentKind,
    EnvironmentState,
    GitSource,
    RepoValidationResult,
    SessionContext,
    SessionCreateParams,
    SessionResource,
    SessionStatus,
    TeleportResult,
)


__all__ = [
    # Utility functions
    "is_transient_error",
    "validate_git_state",
    "get_current_branch",
    "find_git_root",
    # Environment functions
    "fetch_environments",
    "create_cloud_environment",
    # Bundle functions
    "create_git_bundle",
    "create_and_upload_bundle",
    # Session functions
    "create_session",
    "fetch_session",
    "poll_remote_session_events",
    "archive_remote_session",
    "validate_session_repository",
    # Info
    "get_teleport_info",
    # Types
    "SessionStatus",
    "EnvironmentKind",
    "EnvironmentState",
    "Environment",
    "SessionContext",
    "SessionCreateParams",
    "SessionResource",
    "GitSource",
    "BundleResult",
    "BundleUploadResult",
    "TeleportResult",
    "RepoValidationResult",
]
