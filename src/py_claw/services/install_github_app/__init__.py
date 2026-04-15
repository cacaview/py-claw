"""
Install GitHub App service.

Sets up Claude GitHub Actions integration for a repository.

Based on ClaudeCode-main/src/services/install-github-app/
"""
from py_claw.services.install_github_app.service import (
    check_github_cli,
    check_repository_permissions,
    get_github_app_install_config,
    install_github_app,
)
from py_claw.services.install_github_app.types import (
    GitHubAppInstallConfig,
    GitHubAppInstallResult,
    GitHubAppInstallStep,
    GitHubCLIStatus,
    Workflow,
)


__all__ = [
    "check_github_cli",
    "check_repository_permissions",
    "get_github_app_install_config",
    "install_github_app",
    "GitHubAppInstallConfig",
    "GitHubAppInstallResult",
    "GitHubAppInstallStep",
    "GitHubCLIStatus",
    "Workflow",
]
