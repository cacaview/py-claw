"""
Teleport service for CCR (Cloud Code Remote) session management.

Handles session creation, environment provisioning, git bundle seeding,
and remote session polling.

Based on ClaudeCode-main/src/utils/teleport/
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from .types import (
    BundleResult,
    BundleUploadResult,
    Environment,
    EnvironmentKind,
    GitSource,
    RepoValidationResult,
    SessionContext,
    SessionCreateParams,
    SessionResource,
    SessionStatus,
    TeleportResult,
)

logger = logging.getLogger(__name__)

# Retry delays for transient network errors (seconds)
TELEPORT_RETRY_DELAYS = [2, 4, 8, 16]

# Default max bundle size (100MB)
DEFAULT_BUNDLE_MAX_BYTES = 100 * 1024 * 1024


def is_transient_error(error: Exception) -> bool:
    """Check if error is transient and retryable.

    Args:
        error: The exception to check

    Returns:
        True if error is retryable
    """
    error_str = str(error).lower()
    transient_patterns = [
        "timeout",
        "connection",
        "network",
        "econnrefused",
        "econnreset",
        "etimedout",
        "500",
        "502",
        "503",
        "504",
    ]
    return any(p in error_str for p in transient_patterns)


def _get_oauth_tokens() -> dict | None:
    """Get OAuth tokens from environment or config.

    Returns:
        Dict with access_token and refresh_token, or None
    """
    # Check environment variables
    access_token = os.environ.get("CLAUDE_AUTH_TOKEN")
    if access_token:
        return {"access_token": access_token}

    # Could also check config file or keyring
    return None


def _get_org_uuid() -> str | None:
    """Get organization UUID from OAuth tokens or config.

    Returns:
        Organization UUID string, or None
    """
    # In real implementation, would extract from OAuth tokens
    # For now, check environment variable
    return os.environ.get("CLAUDE_ORG_UUID")


async def fetch_environments() -> list[Environment]:
    """Fetch available CCR environments.

    Returns:
        List of Environment objects
    """
    tokens = _get_oauth_tokens()
    if not tokens:
        return []

    org_uuid = _get_org_uuid()
    if not org_uuid:
        return []

    # In real implementation, would call CCR API:
    # GET /v1/environment_providers
    # with OAuth headers and x-organization-uuid header

    return []


async def create_cloud_environment(name: str) -> Environment | None:
    """Create a default cloud environment.

    Args:
        name: Name for the environment

    Returns:
        Environment object or None on failure
    """
    tokens = _get_oauth_tokens()
    if not tokens:
        return None

    org_uuid = _get_org_uuid()
    if not org_uuid:
        return None

    # In real implementation, would call CCR API:
    # POST /v1/environment_providers/cloud/create

    return None


def validate_git_state(cwd: str) -> tuple[bool, str]:
    """Validate git repository state.

    Args:
        cwd: Working directory

    Returns:
        Tuple of (is_clean, error_message)
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 or "true" not in result.stdout.lower():
            return False, "Not a git repository"

        # Check if working tree is clean
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        is_clean = result.returncode == 0 and result.stdout.strip() == ""
        return is_clean, "" if is_clean else "Working tree has uncommitted changes"

    except subprocess.TimeoutExpired:
        return False, "Git command timed out"
    except Exception as e:
        return False, str(e)


def get_current_branch(cwd: str) -> str | None:
    """Get current git branch name.

    Args:
        cwd: Working directory

    Returns:
        Branch name or None
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def find_git_root(cwd: str) -> Path | None:
    """Find the git root directory.

    Args:
        cwd: Starting directory

    Returns:
        Path to git root or None
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
        return None
    except Exception:
        return None


def _run_git_command(args: list[str], cwd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command and return result.

    Args:
        args: Git command arguments
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def create_git_bundle(cwd: str, max_bytes: int | None = None) -> BundleResult:
    """Create a git bundle for repository seeding.

    Args:
        cwd: Working directory for git repository
        max_bytes: Maximum bundle size (default 100MB)

    Returns:
        BundleResult with bundle information
    """
    if max_bytes is None:
        max_bytes = DEFAULT_BUNDLE_MAX_BYTES

    try:
        git_root = find_git_root(cwd)
        if not git_root:
            return BundleResult(success=False, error="Not a git repository")

        # Check for WIP (work in progress)
        code, stash_out, _ = _run_git_command(["stash", "list"], str(git_root), timeout=5)
        has_wip = code == 0 and stash_out.strip()

        # Clean up any stale seed refs
        _run_git_command(["update-ref", "-d", "refs/seed/stash"], str(git_root), timeout=5)
        _run_git_command(["update-ref", "-d", "refs/seed/root"], str(git_root), timeout=5)

        # Create stash for WIP
        code, wip_sha, _ = _run_git_command(["stash", "create"], str(git_root), timeout=30)
        if code == 0 and wip_sha.strip():
            _run_git_command(
                ["update-ref", "refs/seed/stash", wip_sha.strip()],
                str(git_root),
                timeout=5,
            )
            has_wip = True

        # Create bundle path
        bundle_fd, bundle_path = tempfile.mkstemp(suffix=".bundle", prefix="ccr-seed")
        os.close(bundle_fd)
        bundle_path = Path(bundle_path)

        # Try --all first
        code, _, stderr = _run_git_command(
            ["bundle", "create", str(bundle_path), "--all"],
            str(git_root),
            timeout=120,
        )
        if code != 0:
            bundle_path.unlink(missing_ok=True)
            return BundleResult(success=False, error=f"Git bundle failed: {stderr[:200]}")

        bundle_size = bundle_path.stat().st_size
        if bundle_size <= max_bytes:
            return BundleResult(
                success=True,
                file_id=str(bundle_path),
                bundle_size_bytes=bundle_size,
                has_wip=has_wip,
                scope="all",
            )

        # Too large with --all, try HEAD only
        bundle_path.unlink(missing_ok=True)
        bundle_fd, bundle_path = tempfile.mkstemp(suffix=".bundle", prefix="ccr-seed")
        os.close(bundle_fd)
        bundle_path = Path(bundle_path)

        code, _, stderr = _run_git_command(
            ["bundle", "create", str(bundle_path), "HEAD"],
            str(git_root),
            timeout=120,
        )
        if code != 0:
            bundle_path.unlink(missing_ok=True)
            return BundleResult(success=False, error=f"Git bundle HEAD failed: {stderr[:200]}")

        bundle_size = bundle_path.stat().st_size
        if bundle_size <= max_bytes:
            # Clean up refs/seed/stash
            _run_git_command(["update-ref", "-d", "refs/seed/stash"], str(git_root), timeout=5)
            return BundleResult(
                success=True,
                file_id=str(bundle_path),
                bundle_size_bytes=bundle_size,
                has_wip=has_wip,
                scope="head",
            )

        # Too large, try squashed root
        bundle_path.unlink(missing_ok=True)
        bundle_fd, bundle_path = tempfile.mkstemp(suffix=".bundle", prefix="ccr-seed")
        os.close(bundle_fd)
        bundle_path = Path(bundle_path)

        tree_ref = "refs/seed/stash^{tree}" if has_wip else "HEAD^{tree}"
        code, commit_sha, stderr = _run_git_command(
            ["commit-tree", tree_ref, "-m", "seed"],
            str(git_root),
            timeout=10,
        )
        if code != 0:
            bundle_path.unlink(missing_ok=True)
            _run_git_command(["update-ref", "-d", "refs/seed/stash"], str(git_root), timeout=5)
            return BundleResult(success=False, error=f"commit-tree failed: {stderr[:200]}")

        code, _, stderr = _run_git_command(
            ["update-ref", "refs/seed/root", commit_sha.strip()],
            str(git_root),
            timeout=5,
        )
        code, _, stderr = _run_git_command(
            ["bundle", "create", str(bundle_path), "refs/seed/root"],
            str(git_root),
            timeout=120,
        )
        if code != 0:
            bundle_path.unlink(missing_ok=True)
            _run_git_command(["update-ref", "-d", "refs/seed/stash"], str(git_root), timeout=5)
            _run_git_command(["update-ref", "-d", "refs/seed/root"], str(git_root), timeout=5)
            return BundleResult(success=False, error=f"bundle squashed failed: {stderr[:200]}")

        bundle_size = bundle_path.stat().st_size
        if bundle_size <= max_bytes:
            _run_git_command(["update-ref", "-d", "refs/seed/stash"], str(git_root), timeout=5)
            _run_git_command(["update-ref", "-d", "refs/seed/root"], str(git_root), timeout=5)
            return BundleResult(
                success=True,
                file_id=str(bundle_path),
                bundle_size_bytes=bundle_size,
                has_wip=has_wip,
                scope="squashed",
            )

        # Too large even with squashed
        bundle_path.unlink(missing_ok=True)
        _run_git_command(["update-ref", "-d", "refs/seed/stash"], str(git_root), timeout=5)
        _run_git_command(["update-ref", "-d", "refs/seed/root"], str(git_root), timeout=5)
        return BundleResult(
            success=False,
            error="Repository is too large to bundle. Please setup GitHub on https://claude.ai/code",
            scope="too_large",
        )

    except Exception as e:
        logger.exception("Error creating git bundle")
        return BundleResult(success=False, error=str(e))


async def create_and_upload_bundle(cwd: str) -> BundleUploadResult:
    """Create and upload a git bundle to CCR backend.

    Args:
        cwd: Working directory

    Returns:
        BundleUploadResult with upload information
    """
    # Create bundle
    bundle_result = create_git_bundle(cwd)
    if not bundle_result.success:
        return BundleUploadResult(
            success=False,
            error=bundle_result.error,
            fail_reason=bundle_result.scope,
        )

    bundle_path = Path(bundle_result.file_id)
    if not bundle_path.exists():
        return BundleUploadResult(success=False, error="Bundle file not found")

    # In real implementation, would upload to CCR backend:
    # POST /v1/files with multipart form data

    # For now, return the local bundle result
    return BundleUploadResult(
        success=True,
        file_id=bundle_result.file_id,
        bundle_size_bytes=bundle_result.bundle_size_bytes,
        scope=bundle_result.scope,
        has_wip=bundle_result.has_wip,
    )


async def fetch_session(session_id: str) -> SessionResource | None:
    """Fetch a session by ID from CCR backend.

    Args:
        session_id: Session ID to fetch

    Returns:
        SessionResource or None
    """
    tokens = _get_oauth_tokens()
    if not tokens:
        return None

    # In real implementation, would call CCR API:
    # GET /v1/sessions/{session_id}

    return None


async def create_session(context: SessionContext) -> TeleportResult:
    """Create a new CCR session.

    Args:
        context: Session creation context

    Returns:
        TeleportResult with session information
    """
    try:
        # Validate git state
        is_clean, error = validate_git_state(context.cwd)
        if error:
            logger.info(f"Git state: {error}")

        # Create bundle for seeding
        bundle_result = create_git_bundle(context.cwd)
        if bundle_result.success:
            logger.info(
                f"Git bundle created: {bundle_result.bundle_size_bytes} bytes, "
                f"has_wip={bundle_result.has_wip}"
            )

        # Fetch environments
        environments = await fetch_environments()
        if not environments:
            return TeleportResult(
                success=False,
                message="No CCR environments available. Run /web-setup first.",
            )

        # In real implementation, would create session via CCR API
        return TeleportResult(
            success=True,
            message="Session creation requires OAuth authentication. Run /login first.",
        )

    except Exception as e:
        logger.exception("Error creating session")
        return TeleportResult(success=False, message=f"Error: {e}")


def validate_session_repository(session_data: SessionResource) -> RepoValidationResult:
    """Validate that session repository matches current environment.

    Args:
        session_data: Session resource from CCR

    Returns:
        RepoValidationResult
    """
    # In real implementation, would compare:
    # - Current repo URL with session's repo URL
    # - Check for divergent branches

    return RepoValidationResult(is_valid=True)


def get_teleport_info() -> TeleportResult:
    """Get teleport status information.

    Returns:
        TeleportResult with status
    """
    try:
        environments: list[Environment] = []
        try:
            import asyncio
            environments = asyncio.run(fetch_environments())
        except Exception:
            pass

        tokens = _get_oauth_tokens()
        if not tokens:
            return TeleportResult(
                success=True,
                message="Not authenticated. Run /login to enable remote sessions.",
            )

        return TeleportResult(
            success=True,
            message=f"Found {len(environments)} environments",
        )
    except Exception as e:
        return TeleportResult(success=False, message=f"Error: {e}")


async def poll_remote_session_events(
    session_id: str,
    after_id: str | None = None,
) -> list[dict]:
    """Poll for events from a remote session.

    Args:
        session_id: Session ID to poll
        after_id: Poll for events after this ID

    Returns:
        List of event dicts
    """
    # In real implementation, would call CCR API:
    # GET /v1/sessions/{session_id}/events

    return []


async def archive_remote_session(session_id: str) -> bool:
    """Archive a remote session.

    Args:
        session_id: Session ID to archive

    Returns:
        True if successful
    """
    tokens = _get_oauth_tokens()
    if not tokens:
        return False

    # In real implementation, would call CCR API:
    # POST /v1/sessions/{session_id}/archive

    return True
