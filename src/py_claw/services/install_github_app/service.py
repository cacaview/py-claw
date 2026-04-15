"""
Install GitHub App service.

Sets up Claude GitHub Actions integration for a repository.

Based on ClaudeCode-main/src/commands/install-github-app/setupGitHubActions.ts
"""
from __future__ import annotations

import base64
import json
import logging
import subprocess
import webbrowser
from pathlib import Path

from .types import (
    GitHubAppInstallConfig,
    GitHubAppInstallResult,
    GitHubAppInstallStep,
    GitHubCLIStatus,
)

logger = logging.getLogger(__name__)

# Workflow file content - matches ClaudeCode-main/src/constants/github-app.ts
WORKFLOW_CONTENT = """name: Claude Code

on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  issues:
    types: [opened, assigned]
  pull_request_review:
    types: [submitted]

jobs:
  claude:
    if: |
      (github.event_name == 'issue_comment' && contains(github.event.comment.body, '@claude')) ||
      (github.event_name == 'pull_request_review_comment' && contains(github.event.comment.body, '@claude')) ||
      (github.event_name == 'pull_request_review' && contains(github.event.review.body, '@claude')) ||
      (github.event_name == 'issues' && (contains(github.event.issue.body, '@claude') || contains(github.event.issue.title, '@claude')))
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
      issues: read
      id-token: write
      actions: read
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Run Claude Code
        id: claude
        uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}

          additional_permissions: |
            actions: read
"""

CODE_REVIEW_WORKFLOW_CONTENT = """name: Claude Code Review

on:
  pull_request:
    types: [opened, synchronize, ready_for_review, reopened]

jobs:
  claude-review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
      issues: read
      id-token: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Run Claude Code Review
        id: claaude-review
        uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: 'https://github.com/anthropics/claude-code.git'
          plugins: 'code-review@claude-code-plugins'
          prompt: '/code-review:code-review ${{ github.repository }}/pull/${{ github.event.pull_request.number }}'
"""

PR_TITLE = "Add Claude Code GitHub Workflow"

PR_BODY = """## 🤖 Installing Claude Code GitHub App

This PR adds a GitHub Actions workflow that enables Claude Code integration in our repository.

### What is Claude Code?

[Claude Code](https://claude.com/claude-code) is an AI coding agent that can help with:
- Bug fixes and improvements
- Documentation updates
- Implementing new features
- Code reviews and suggestions
- Writing tests
- And more!

### How it works

Once this PR is merged, we'll be able to interact with Claude by mentioning @claude in a pull request or issue comment.
Once the workflow is triggered, Claude will analyze the comment and surrounding context, and execute on the request in a GitHub action.

### Important Notes

- **This workflow won't take effect until this PR is merged**
- **@claude mentions won't work until after the merge is complete**
- The workflow runs automatically whenever Claude is mentioned in PR or issue comments
- Claude gets access to the entire PR or issue context including files, diffs, and previous comments

### Security

- Our Anthropic API key is securely stored as a GitHub Actions secret
- Only users with write access to the repository can trigger the workflow
- All Claude runs are stored in the GitHub Actions run history
- Claude's default tools are limited to reading/writing files and interacting with our repo by creating comments, branches, and commits.
- We can add more allowed tools by adding them to the workflow file like:

```
allowed_tools: Bash(npm install),Bash(npm run build),Bash(npm run lint),Bash(npm run test)
```

There's more information in the [Claude Code action repo](https://github.com/anthropics/claude-code-action).

After merging this PR, let's try mentioning @claude in a comment on any PR to get started!
"""

_github_app_config = GitHubAppInstallConfig()


def get_github_app_install_config() -> GitHubAppInstallConfig:
    """Get the GitHub App install configuration."""
    return _github_app_config


def check_github_cli() -> GitHubCLIStatus:
    """Check if GitHub CLI is installed and authenticated.

    Returns:
        GitHubCLIStatus with installation and auth status
    """
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            version_line = result.stdout.strip().split("\n")[0]
            version = version_line.replace("gh version ", "").split(" ")[0]

            # Check if authenticated
            auth_result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            authenticated = auth_result.returncode == 0

            return GitHubCLIStatus(
                installed=True,
                authenticated=authenticated,
                version=version,
            )
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        logger.debug("Error checking GitHub CLI: %s", e)

    return GitHubCLIStatus(installed=False, authenticated=False)


def _run_gh_command(args: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a gh command and return (returncode, stdout, stderr).

    Args:
        args: Command arguments starting with 'gh'
        timeout: Timeout in seconds

    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except FileNotFoundError:
        return 1, "", "gh CLI not found"
    except Exception as e:
        return 1, "", str(e)


def check_repository_permissions(repo: str) -> bool:
    """Check if we have write access to a repository.

    Args:
        repo: Repository in 'owner/repo' format

    Returns:
        True if we have write access
    """
    code, stdout, _ = _run_gh_command(["api", f"/repos/{repo}", "--jq", ".permissions.contents"])
    if code == 0:
        return stdout.strip() == "write"
    return False


def _get_default_branch(repo: str) -> str | None:
    """Get the default branch of a repository.

    Args:
        repo: Repository in 'owner/repo' format

    Returns:
        Default branch name or None on error
    """
    code, stdout, _ = _run_gh_command(
        ["api", f"/repos/{repo}", "--jq", ".default_branch"]
    )
    if code == 0:
        return stdout.strip()
    return None


def _get_branch_sha(repo: str, branch: str) -> str | None:
    """Get the SHA of a branch head.

    Args:
        repo: Repository in 'owner/repo' format
        branch: Branch name

    Returns:
        SHA or None on error
    """
    code, stdout, _ = _run_gh_command(
        ["api", f"/repos/{repo}/git/ref/heads/{branch}", "--jq", ".object.sha"]
    )
    if code == 0:
        return stdout.strip()
    return None


def _create_workflow_file(
    repo: str,
    branch: str,
    workflow_path: str,
    content: str,
    message: str,
    secret_name: str,
) -> tuple[bool, str | None]:
    """Create or update a workflow file via GitHub API.

    Args:
        repo: Repository in 'owner/repo' format
        branch: Branch name to create file on
        workflow_path: Path within the repo (e.g., '.github/workflows/claude.yml')
        content: File content
        message: Commit message
        secret_name: Secret name for replacement in content

    Returns:
        Tuple of (success, error_message)
    """
    # Check if file exists and get its SHA
    code, stdout, _ = _run_gh_command(
        ["api", f"/repos/{repo}/contents/{workflow_path}", "--jq", ".sha"]
    )
    file_sha = stdout.strip() if code == 0 else None

    # Replace secret name in content if needed
    if secret_name != "ANTHROPIC_API_KEY":
        content = content.replace(
            "anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}",
            f"anthropic_api_key: ${{ secrets.{secret_name} }}",
        )

    # Base64 encode content
    encoded_content = base64.b64encode(content.encode()).decode()

    # Build API params
    params = [
        "api",
        "--method", "PUT",
        f"/repos/{repo}/contents/{workflow_path}",
        "-f", f"message={message}",
        "-f", f"content={encoded_content}",
        "-f", f"branch={branch}",
    ]

    if file_sha:
        params.extend(["-f", f"sha={file_sha}"])

    code, _, stderr = _run_gh_command(params)

    if code != 0:
        # Check for specific error about existing file
        if "422" in stderr and "sha" in stderr:
            return False, f"A workflow file already exists at {workflow_path}. Please remove it first or update it manually."
        return False, f"Failed to create workflow file: {stderr}"

    return True, None


def _create_branch(repo: str, branch_name: str, sha: str) -> tuple[bool, str | None]:
    """Create a new branch.

    Args:
        repo: Repository in 'owner/repo' format
        branch_name: Name of new branch
        sha: SHA to create branch from

    Returns:
        Tuple of (success, error_message)
    """
    code, _, stderr = _run_gh_command(
        [
            "api",
            "--method", "POST",
            f"/repos/{repo}/git/refs",
            "-f", f"ref=refs/heads/{branch_name}",
            "-f", f"sha={sha}",
        ],
    )

    if code != 0:
        return False, f"Failed to create branch: {stderr}"

    return True, None


def _set_secret(repo: str, secret_name: str, value: str) -> tuple[bool, str | None]:
    """Set a secret in the repository.

    Args:
        repo: Repository in 'owner/repo' format
        secret_name: Name of the secret
        value: Secret value

    Returns:
        Tuple of (success, error_message)
    """
    code, _, stderr = _run_gh_command(
        ["secret", "set", secret_name, "--body", value, "--repo", repo],
    )

    if code != 0:
        return False, f"Failed to set secret: {stderr}"

    return True, None


async def install_github_app(
    repository: str,
    api_key: str | None = None,
    selected_workflows: list[str] | None = None,
) -> GitHubAppInstallResult:
    """Install GitHub Actions integration for a repository.

    This implements the full workflow from TypeScript setupGitHubActions.ts:
    1. Check gh CLI and authentication
    2. Verify repository access
    3. Create a new branch
    4. Create workflow file(s) via GitHub API
    5. Set API key secret
    6. Open browser for PR creation

    Args:
        repository: Repository in 'owner/repo' format
        api_key: Optional API key to set as secret
        selected_workflows: List of workflows to create ('claude', 'claude-review')

    Returns:
        GitHubAppInstallResult with installation status
    """
    config = _github_app_config
    if selected_workflows is None:
        selected_workflows = ["claude"]

    try:
        # Step 1: Check GitHub CLI
        cli_status = check_github_cli()
        if not cli_status.installed:
            return GitHubAppInstallResult(
                success=False,
                step=GitHubAppInstallStep.CHECK_GITHUB_CLI,
                message="GitHub CLI (gh) is not installed. Please install it first: https://cli.github.com",
            )
        if not cli_status.authenticated:
            return GitHubAppInstallResult(
                success=False,
                step=GitHubAppInstallStep.CHECK_GITHUB_CLI,
                message="GitHub CLI is not authenticated. Run 'gh auth login' first.",
            )

        # Step 2: Check if repository exists and is accessible
        code, _, stderr = _run_gh_command(["api", f"/repos/{repository}", "--jq", ".id"])
        if code != 0:
            return GitHubAppInstallResult(
                success=False,
                step=GitHubAppInstallStep.CHECK_GITHUB_STATUS,
                message=f"Failed to access repository {repository}: {stderr}",
                repository=repository,
            )

        # Step 3: Get default branch and SHA
        default_branch = _get_default_branch(repository)
        if not default_branch:
            return GitHubAppInstallResult(
                success=False,
                step=GitHubAppInstallStep.CHECK_GITHUB_STATUS,
                message="Failed to get default branch",
                repository=repository,
            )

        sha = _get_branch_sha(repository, default_branch)
        if not sha:
            return GitHubAppInstallResult(
                success=False,
                step=GitHubAppInstallStep.CHECK_GITHUB_STATUS,
                message="Failed to get branch SHA",
                repository=repository,
            )

        # Step 4: Create new branch for the workflow changes
        branch_name = f"add-claude-github-actions-{__import__('time').time():.0f}"
        success, error = _create_branch(repository, branch_name, sha)
        if not success:
            return GitHubAppInstallResult(
                success=False,
                step=GitHubAppInstallStep.CREATING,
                message=error,
                repository=repository,
            )

        # Step 5: Create workflow files
        workflows_to_create = []

        if "claude" in selected_workflows:
            workflows_to_create.append({
                "path": ".github/workflows/claude.yml",
                "content": WORKFLOW_CONTENT,
                "message": "Add Claude PR Assistant workflow",
            })

        if "claude-review" in selected_workflows:
            workflows_to_create.append({
                "path": ".github/workflows/claude-code-review.yml",
                "content": CODE_REVIEW_WORKFLOW_CONTENT,
                "message": "Add Claude Code Review workflow",
            })

        workflow_paths = []
        for workflow in workflows_to_create:
            success, error = _create_workflow_file(
                repository,
                branch_name,
                workflow["path"],
                workflow["content"],
                workflow["message"],
                config.secret_name,
            )
            if not success:
                return GitHubAppInstallResult(
                    success=False,
                    step=GitHubAppInstallStep.CREATING,
                    message=error,
                    repository=repository,
                    workflow_path=workflow["path"],
                )
            workflow_paths.append(workflow["path"])

        # Step 6: Set the API key secret
        if api_key:
            success, error = _set_secret(repository, config.secret_name, api_key)
            if not success:
                return GitHubAppInstallResult(
                    success=False,
                    step=GitHubAppInstallStep.CREATING,
                    message=error,
                    repository=repository,
                    workflow_path=", ".join(workflow_paths) if workflow_paths else None,
                )

        # Step 7: Open browser to create PR
        pr_url = (
            f"https://github.com/{repository}/compare/{default_branch}...{branch_name}"
            f"?quick_pull=1&title={PR_TITLE.replace(' ', '+')}"
            f"&body={PR_BODY.replace(' ', '+').replace('\n', '%0A')}"
        )
        try:
            webbrowser.open(pr_url)
        except Exception:
            pass  # Best effort

        return GitHubAppInstallResult(
            success=True,
            step=GitHubAppInstallStep.SUCCESS,
            message=f"Successfully configured GitHub Actions for {repository}. Opening PR...",
            repository=repository,
            workflow_path=", ".join(workflow_paths) if workflow_paths else None,
            secret_name=config.secret_name,
        )

    except Exception as e:
        logger.exception("Error installing GitHub App")
        return GitHubAppInstallResult(
            success=False,
            step=GitHubAppInstallStep.ERROR,
            message=f"Error: {e}",
        )
