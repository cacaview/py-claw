"""
Types for install_github_app service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GitHubAppInstallStep(str, Enum):
    """Steps in the GitHub App installation wizard."""
    CHECK_GITHUB_CLI = "check-github-cli"
    CHECK_EXISTING_SECRET = "check-existing-secret"
    CHECK_GITHUB_STATUS = "check-github-status"
    CHOOSE_REPO = "choose-repo"
    OAUTH_FLOW = "oauth-flow"
    CREATING = "creating"
    SUCCESS = "success"
    ERROR = "error"


class Workflow(str, Enum):
    """Available GitHub Action workflows."""
    CLAUDE = "claude"
    CLAUDE_REVIEW = "claude-review"


@dataclass
class GitHubAppInstallConfig:
    """Configuration for GitHub App installation."""
    workflow_dir: str = ".github/workflows"
    secret_name: str = "ANTHROPIC_API_KEY"
    app_name: str = "Claude Code"


@dataclass
class GitHubAppInstallResult:
    """Result of GitHub App installation."""
    success: bool
    step: GitHubAppInstallStep
    message: str
    repository: str | None = None
    workflow_path: str | None = None
    secret_name: str | None = None


@dataclass
class GitHubCLIStatus:
    """Status of GitHub CLI installation."""
    installed: bool
    authenticated: bool
    version: str | None = None
