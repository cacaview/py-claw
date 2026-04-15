"""
Types for teleport service.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SessionStatus(str, Enum):
    """Session status."""
    REQUIRES_ACTION = "requires_action"
    RUNNING = "running"
    IDLE = "idle"
    ARCHIVED = "archived"


class EnvironmentKind(str, Enum):
    """Environment type."""
    ANTHROPIC_CLOUD = "anthropic_cloud"
    BYOC = "byoc"
    BRIDGE = "bridge"


class EnvironmentState(str, Enum):
    """Environment state."""
    ACTIVE = "active"


@dataclass
class SessionContext:
    """Context for creating a session."""
    cwd: str
    sources: list[dict] | None = None
    custom_system_prompt: str | None = None
    model: str | None = None
    seed_bundle_file_id: str | None = None


@dataclass
class Environment:
    """A compute environment."""
    id: str
    name: str
    kind: EnvironmentKind
    status: str | None = None


@dataclass
class BundleResult:
    """Result of git bundle creation."""
    success: bool
    file_id: str | None = None
    bundle_size_bytes: int | None = None
    has_wip: bool = False
    error: str | None = None
    scope: str | None = None


@dataclass
class TeleportResult:
    """Result of teleport operation."""
    success: bool
    message: str
    session_id: str | None = None
    environment: Environment | None = None
    title: str | None = None
    branch_name: str | None = None


@dataclass
class SessionResource:
    """A remote session resource."""
    id: str
    title: str
    status: SessionStatus
    environment_id: str | None = None
    branch_name: str | None = None
    created_at: str | None = None
    last_active_at: str | None = None


@dataclass
class GitSource:
    """Git source for session."""
    type: str = "git_repository"
    url: str = ""
    revision: str | None = None
    allow_unrestricted_git_push: bool = False


@dataclass
class SessionCreateParams:
    """Parameters for creating a remote session."""
    environment_id: str
    title: str
    branch_name: str
    context_source: GitSource | None = None
    model: str | None = None
    permission_mode: str | None = None
    ultraplan: bool = False
    seed_bundle_file_id: str | None = None
    environment_variables: dict[str, str] | None = None
    github_pr: dict | None = None
    initial_message: str | None = None


@dataclass
class BundleUploadResult:
    """Result of bundle upload operation."""
    success: bool
    file_id: str | None = None
    bundle_size_bytes: int | None = None
    scope: str | None = None
    has_wip: bool = False
    error: str | None = None
    fail_reason: str | None = None


@dataclass
class RepoValidationResult:
    """Result of repository validation."""
    is_valid: bool
    current_repo: str | None = None
    session_repo: str | None = None
    error: str | None = None
