"""Commit service - git commit analysis and preparation.

Provides commit attribution tracking and analysis of staged changes
to help create well-formatted commits with proper attribution.

Reference: ClaudeCode-main/src/commands/commit.ts
           ClaudeCode-main/src/utils/commitAttribution.ts
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from .types import (
    AttributionData,
    AttributionState,
    AttributionSummary,
    CommitAnalysisResult,
    CommitPreparationResult,
    FileAttribution,
    FileAttributionState,
)


# Internal model repos allowlist - repos where internal model names are allowed in trailers
_INTERNAL_MODEL_REPOS = [
    "github.com:anthropics/claude-cli-internal",
    "github.com/anthropics/claude-cli-internal",
    "github.com:anthropics/anthropic",
    "github.com/anthropics/anthropic",
    "github.com:anthropics/apps",
    "github.com/anthropics/apps",
    "github.com:anthropics/casino",
    "github.com/anthropics/casino",
    "github.com:anthropics/dbt",
    "github.com/anthropics/dbt",
    "github.com:anthropics/dotfiles",
    "github.com/anthropics/dotfiles",
    "github.com:anthropics/terraform-config",
    "github.com/anthropics/terraform-config",
    "github.com:anthropics/hex-export",
    "github.com/anthropics/hex-export",
    "github.com:anthropics/feedback-v2",
    "github.com/anthropics/feedback-v2",
    "github.com:anthropics/labs",
    "github.com/anthropics/labs",
    "github.com:anthropics/argo-rollouts",
    "github.com/anthropics/argo-rollouts",
    "github.com:anthropics/starling-configs",
    "github.com/anthropics/starling-configs",
    "github.com:anthropics/ts-tools",
    "github.com/anthropics/ts-tools",
    "github.com:anthropics/ts-capsules",
    "github.com/anthropics/ts-capsules",
    "github.com:anthropics/feldspar-testing",
    "github.com/anthropics/feldspar-testing",
    "github.com:anthropics/trellis",
    "github.com/anthropics/trellis",
    "github.com:anthropics/claude-for-hiring",
    "github.com/anthropics/claude-for-hiring",
    "github.com:anthropics/forge-web",
    "github.com/anthropics/forge-web",
    "github.com:anthropics/infra-manifests",
    "github.com/anthropics/infra-manifests",
    "github.com:anthropics/mycro_manifests",
    "github.com/anthropics/mycro_manifests",
    "github.com:anthropics/mycro_configs",
    "github.com/anthropics/mycro_configs",
    "github.com:anthropics/mobile-apps",
    "github.com/anthropics/mobile-apps",
]

# Model name sanitization - map internal variants to public names
_MODEL_SANITIZATION = {
    "opus-4-6": "claude-opus-4-6",
    "opus-4-5": "claude-opus-4-5",
    "opus-4-1": "claude-opus-4-1",
    "opus-4": "claude-opus-4",
    "sonnet-4-6": "claude-sonnet-4-6",
    "sonnet-4-5": "claude-sonnet-4-5",
    "sonnet-4": "claude-sonnet-4",
    "sonnet-3-7": "claude-sonnet-3-7",
    "haiku-4-5": "claude-haiku-4-5",
    "haiku-3-5": "claude-haiku-3-5",
}


def _get_git_root(cwd: str | None = None) -> str | None:
    """Find git root directory for the given path."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _run_git_command(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def _get_remote_url(cwd: str | None = None) -> str | None:
    """Get the remote URL for the current repo."""
    _, stdout, _ = _run_git_command(["remote", "get-url", "origin"], cwd)
    return stdout.strip() if stdout.strip() else None


def _is_internal_model_repo(cwd: str | None = None) -> bool:
    """Check if the current repo is in the allowlist for internal model names."""
    remote_url = _get_remote_url(cwd)
    if not remote_url:
        return False
    return any(repo in remote_url for repo in _INTERNAL_MODEL_REPOS)


def _sanitize_model_name(model_name: str) -> str:
    """Sanitize a model name to its public equivalent."""
    for internal, public in _MODEL_SANITIZATION.items():
        if internal in model_name:
            return public
    return "claude"


def _sanitize_surface_key(surface_key: str) -> str:
    """Sanitize a surface key to use public model names."""
    if "/" not in surface_key:
        return surface_key
    surface, model = surface_key.rsplit("/", 1)
    return f"{surface}/{_sanitize_model_name(model)}"


def _compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _normalize_file_path(file_path: str, cwd: str) -> str:
    """Normalize file path to relative path from cwd."""
    import os
    path = Path(file_path)
    if path.is_absolute():
        try:
            return str(path.relative_to(Path(cwd)))
        except ValueError:
            return file_path
    return file_path


def _get_client_surface() -> str:
    """Get the current client surface from environment."""
    import os
    return os.environ.get("CLAUDE_CODE_ENTRYPOINT", "cli")


def create_empty_attribution_state() -> AttributionState:
    """Create an empty attribution state for a new session."""
    return AttributionState(
        file_states={},
        session_baselines={},
        surface=_get_client_surface(),
        starting_head_sha=None,
        prompt_count=0,
        prompt_count_at_last_commit=0,
        permission_prompt_count=0,
        permission_prompt_count_at_last_commit=0,
        escape_count=0,
        escape_count_at_last_commit=0,
    )


def track_file_modification(
    state: AttributionState,
    file_path: str,
    old_content: str,
    new_content: str,
    mtime: float | None = None,
) -> AttributionState:
    """Track a file modification by Claude."""
    if mtime is None:
        import time
        mtime = time.time()

    cwd = _get_git_root() or "."
    normalized_path = _normalize_file_path(file_path, cwd)

    # Calculate Claude's character contribution
    old_len = len(old_content)
    new_len = len(new_content)

    if old_content == "" or new_content == "":
        # New file or full deletion
        claude_contribution = new_len if old_content == "" else old_len
    else:
        # Find common prefix and suffix
        min_len = min(old_len, new_len)
        prefix_end = 0
        while prefix_end < min_len and old_content[prefix_end] == new_content[prefix_end]:
            prefix_end += 1

        suffix_len = 0
        while (suffix_len < min_len - prefix_end and
               old_content[old_len - 1 - suffix_len] == new_content[new_len - 1 - suffix_len]):
            suffix_len += 1

        old_changed_len = old_len - prefix_end - suffix_len
        new_changed_len = new_len - prefix_end - suffix_len
        claude_contribution = max(old_changed_len, new_changed_len)

    # Update state
    new_file_states = dict(state.file_states)
    existing = new_file_states.get(normalized_path)
    existing_contribution = existing.claude_contribution if existing else 0

    new_file_states[normalized_path] = FileAttributionState(
        content_hash=_compute_content_hash(new_content),
        claude_contribution=existing_contribution + claude_contribution,
        mtime=mtime,
    )

    return AttributionState(
        file_states=new_file_states,
        session_baselines=state.session_baselines,
        surface=state.surface,
        starting_head_sha=state.starting_head_sha,
        prompt_count=state.prompt_count,
        prompt_count_at_last_commit=state.prompt_count_at_last_commit,
        permission_prompt_count=state.permission_prompt_count,
        permission_prompt_count_at_last_commit=state.permission_prompt_count_at_last_commit,
        escape_count=state.escape_count,
        escape_count_at_last_commit=state.escape_count_at_last_commit,
    )


def get_staged_files(cwd: str | None = None) -> list[str]:
    """Get list of staged files."""
    _, stdout, _ = _run_git_command(["diff", "--cached", "--name-only"], cwd)
    return [f.strip() for f in stdout.split("\n") if f.strip()]


def get_git_status(cwd: str | None = None) -> str:
    """Get git status summary."""
    _, stdout, _ = _run_git_command(["status", "--short"], cwd)
    return stdout


def get_git_diff(cwd: str | None = None) -> str:
    """Get git diff of staged changes."""
    _, stdout, _ = _run_git_command(["diff", "HEAD", "--"], cwd)
    return stdout


def get_current_branch(cwd: str | None = None) -> str:
    """Get current branch name."""
    _, stdout, _ = _run_git_command(["branch", "--show-current"], cwd)
    return stdout.strip()


def get_recent_commits(cwd: str | None = None, count: int = 10) -> list[str]:
    """Get recent commit messages."""
    _, stdout, _ = _run_git_command(["log", f"--oneline", f"-{count}"], cwd)
    return [c.strip() for c in stdout.split("\n") if c.strip()]


def is_git_transient_state(cwd: str | None = None) -> bool:
    """Check if we're in a transient git state (rebase, merge, cherry-pick)."""
    git_root = _get_git_root(cwd)
    if not git_root:
        return False

    indicators = [
        "rebase-merge",
        "rebase-apply",
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "BISECT_LOG",
    ]

    for indicator in indicators:
        if (Path(git_root) / ".git" / indicator).exists():
            return True
    return False


def analyze_staged_changes(cwd: str | None = None) -> CommitAnalysisResult:
    """Analyze staged changes for commit preparation."""
    staged_files = get_staged_files(cwd)
    branch = get_current_branch(cwd)
    recent = get_recent_commits(cwd)
    in_transient = is_git_transient_state(cwd)

    # Categorize files
    modified = []
    new_files = []
    deleted = []

    for file in staged_files:
        _, stdout, _ = _run_git_command(["diff", "--cached", "--name-status", "--", file], cwd)
        status = stdout.strip()[0] if stdout.strip() else "M"
        if status == "D":
            deleted.append(file)
        elif status == "?":
            new_files.append(file)
        else:
            modified.append(file)

    has_staged = len(staged_files) > 0

    return CommitAnalysisResult(
        staged_files=staged_files,
        modified_files=modified,
        new_files=new_files,
        deleted_files=deleted,
        total_changes=len(staged_files),
        has_staged_changes=has_staged,
        current_branch=branch,
        recent_commits=recent,
        is_in_transient_state=in_transient,
    )


def prepare_commit(
    attribution_state: AttributionState | None = None,
    cwd: str | None = None,
) -> CommitPreparationResult:
    """Prepare for a commit by analyzing staged changes and attribution."""
    if attribution_state is None:
        attribution_state = create_empty_attribution_state()

    analysis = analyze_staged_changes(cwd)

    if not analysis.has_staged_changes:
        return CommitPreparationResult(
            ready=False,
            staged_files=[],
            analysis=analysis,
            error_message="No staged changes to commit",
        )

    if analysis.is_in_transient_state:
        return CommitPreparationResult(
            ready=False,
            staged_files=analysis.staged_files,
            analysis=analysis,
            error_message="Cannot commit during rebase/merge/cherry-pick",
        )

    # Build attribution data
    attribution_data = _calculate_commit_attribution(
        attribution_state,
        analysis.staged_files,
        cwd,
    )

    return CommitPreparationResult(
        ready=True,
        staged_files=analysis.staged_files,
        analysis=analysis,
        attribution_data=attribution_data,
    )


def _calculate_commit_attribution(
    state: AttributionState,
    staged_files: list[str],
    cwd: str | None = None,
) -> AttributionData:
    """Calculate attribution for staged files."""
    cwd_value = cwd or _get_git_root() or "."

    files: dict[str, FileAttribution] = {}
    excluded_generated: list[str] = []
    total_claude_chars = 0
    total_human_chars = 0
    surfaces = {state.surface}

    for file in staged_files:
        # Skip generated files (simple check - could be enhanced)
        if _is_generated_file(file):
            excluded_generated.append(file)
            continue

        abs_path = Path(cwd_value) / file
        file_state = state.file_states.get(file)
        baseline = state.session_baselines.get(file)

        claude_chars = 0
        human_chars = 0

        # Check if file was deleted
        _, stdout, _ = _run_git_command(["diff", "--cached", "--name-status", "--", file], cwd_value)
        is_deleted = stdout.strip().startswith("D") if stdout.strip() else False

        if is_deleted:
            if file_state:
                claude_chars = file_state.claude_contribution
                human_chars = 0
        elif abs_path.exists():
            if file_state:
                claude_chars = file_state.claude_contribution
                human_chars = 0
            elif baseline:
                diff_size = _get_git_diff_size(file, cwd_value)
                human_chars = diff_size if diff_size > 0 else abs_path.stat().st_size
            else:
                human_chars = abs_path.stat().st_size
        else:
            # File doesn't exist - skip
            continue

        # Ensure non-negative
        claude_chars = max(0, claude_chars)
        human_chars = max(0, human_chars)

        total = claude_chars + human_chars
        percent = int((claude_chars / total) * 100) if total > 0 else 0

        files[file] = FileAttribution(
            claude_chars=claude_chars,
            human_chars=human_chars,
            percent=percent,
            surface=state.surface,
        )

        total_claude_chars += claude_chars
        total_human_chars += human_chars

    total_chars = total_claude_chars + total_human_chars
    claude_percent = int((total_claude_chars / total_chars) * 100) if total_chars > 0 else 0

    summary = AttributionSummary(
        claude_percent=claude_percent,
        claude_chars=total_claude_chars,
        human_chars=total_human_chars,
        surfaces=list(surfaces),
    )

    return AttributionData(
        version=1,
        summary=summary,
        files=files,
        excluded_generated=excluded_generated,
        sessions=[],
    )


def _is_generated_file(file_path: str) -> bool:
    """Check if a file is generated (simple heuristic)."""
    # Common generated file patterns
    generated_indicators = [
        ".min.",
        ".bundle.",
        ".generated.",
        "__pycache__",
        ".pyc",
        "node_modules",
        ".git",
    ]
    return any(indicator in file_path for indicator in generated_indicators)


def _get_git_diff_size(file_path: str, cwd: str) -> int:
    """Get the size of changes for a file from git diff."""
    _, stdout, _ = _run_git_command(["diff", "--cached", "--stat", "--", file_path], cwd)

    # Parse stat output - format: "file | 5 ++---"
    # or "1 file changed, 3 insertions(+), 2 deletions(-)"
    total_changes = 0
    for line in stdout.split("\n"):
        if "file changed" in line or "files changed" in line:
            # Extract insertions and deletions
            import re
            insert_match = re.search(r"(\d+) insertion", line)
            delete_match = re.search(r"(\d+) deletion", line)
            insertions = int(insert_match.group(1)) if insert_match else 0
            deletions = int(delete_match.group(1)) if delete_match else 0
            # Approximate chars per line (~40 chars average)
            total_changes = (insertions + deletions) * 40

    return total_changes


def build_commit_prompt(
    attribution_data: AttributionData | None = None,
    cwd: str | None = None,
) -> str:
    """Build the commit prompt content with git context."""
    status = get_git_status(cwd)
    diff = get_git_diff(cwd)
    branch = get_current_branch(cwd)
    recent_commits = get_recent_commits(cwd)

    prompt_parts = [
        "## Context\n",
        f"- Current git status:\n```\n{status or '(no output)'}\n```\n",
        f"- Current git diff (staged and unstaged changes):\n```\n{diff[:2000] if diff else '(no output)'}\n```\n",
        f"- Current branch: {branch or 'unknown'}\n",
        f"- Recent commits:\n" + "\n".join(f"  - {c}" for c in recent_commits[:10]),
        "\n## Git Safety Protocol\n",
        "- NEVER update the git config\n",
        "- NEVER skip hooks (--no-verify, --no-gpg-sign, etc) unless the user explicitly requests it\n",
        "- CRITICAL: ALWAYS create NEW commits. NEVER use git commit --amend, unless the user explicitly requests it\n",
        "- Do not commit files that likely contain secrets (.env, credentials.json, etc). Warn the user if they specifically request to commit those files\n",
        "- If there are no changes to commit (i.e., no untracked files and no modifications), do not create an empty commit\n",
        "- Never use git commands with the -i flag (like git rebase -i or git add -i) since they require interactive input which is not supported\n",
    ]

    # Add attribution info if available
    if attribution_data and attribution_data.summary:
        prompt_parts.extend([
            "\n## Attribution\n",
            f"- Claude's contribution: {attribution_data.summary.claude_percent}% ({attribution_data.summary.claude_chars} chars)\n",
            f"- Human contribution: {100 - attribution_data.summary.claude_percent}% ({attribution_data.summary.human_chars} chars)\n",
        ])

    prompt_parts.extend([
        "\n## Your task\n",
        "Based on the above changes, create a single git commit:\n",
        "1. Analyze all staged changes and draft a commit message:\n",
        "   - Look at the recent commits above to follow this repository's commit message style\n",
        "   - Summarize the nature of the changes (new feature, enhancement, bug fix, refactoring, test, docs, etc.)\n",
        "   - Ensure the message accurately reflects the changes and their purpose\n",
        "   - Draft a concise (1-2 sentences) commit message that focuses on the \"why\" rather than the \"what\"\n",
        "\n2. Create the commit using HEREDOC syntax:\n",
        "```\ngit commit -m \"$(cat <<'EOF'\n",
        "Your commit message here.\n",
        "EOF\n",
        ")\n",
        "```\n",
    ])

    return "".join(prompt_parts)
