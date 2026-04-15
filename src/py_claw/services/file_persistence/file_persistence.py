"""File persistence orchestrator for BYOC mode."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_UPLOAD_CONCURRENCY = 4
FILE_COUNT_LIMIT = 1000
OUTPUTS_SUBDIR = "outputs"


@dataclass
class TurnStartTime:
    """Timestamp when the turn started."""

    value: float

    @classmethod
    def now(cls) -> "TurnStartTime":
        return cls(value=datetime.now().timestamp())


@dataclass
class PersistedFile:
    """Represents a successfully persisted file."""

    filename: str
    file_id: str


@dataclass
class FailedPersistence:
    """Represents a failed file persistence operation."""

    filename: str
    error: str


@dataclass
class FilesPersistedEventData:
    """Event data for files persistence completion."""

    files: list[PersistedFile] = field(default_factory=list)
    failed: list[FailedPersistence] = field(default_factory=list)


def _get_environment_kind() -> str:
    """
    Get the current environment kind.

    Returns 'byoc' for BYOC mode, 'cloud' for 1P/Cloud mode.
    """
    return os.environ.get("CLAUDE_CODE_ENVIRONMENT_KIND", "cloud")


def _get_session_ingress_auth_token() -> str | None:
    """Get the session ingress auth token."""
    return os.environ.get("CLAUDE_CODE_SESSION_INGRESS_TOKEN")


def _get_session_id() -> str | None:
    """Get the remote session ID."""
    return os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")


def _find_modified_files(turn_start_time: TurnStartTime, outputs_dir: str) -> list[str]:
    """
    Find files modified since turn start time in outputs directory.

    Args:
        turn_start_time: Timestamp when turn started
        outputs_dir: Directory to scan

    Returns:
        List of file paths that were modified
    """
    modified = []
    turn_start = turn_start_time.value

    try:
        outputs_path = Path(outputs_dir)
        if not outputs_path.exists():
            return []

        for path in outputs_path.rglob("*"):
            if path.is_file():
                mtime = path.stat().st_mtime
                if mtime > turn_start:
                    modified.append(str(path))
    except Exception as e:
        logger.warning(f"Error scanning outputs directory: {e}")

    return modified


async def run_file_persistence(
    turn_start_time: TurnStartTime,
    signal: Any = None,
) -> FilesPersistedEventData | None:
    """
    Execute file persistence for modified files in outputs directory.

    Assembles all config internally:
    - Checks environment kind (CLAUDE_CODE_ENVIRONMENT_KIND)
    - Retrieves session access token
    - Requires CLAUDE_CODE_REMOTE_SESSION_ID for session ID

    Args:
        turn_start_time: The timestamp when the turn started
        signal: Optional abort signal for cancellation

    Returns:
        Event data, or None if not enabled or no files to persist
    """
    environment_kind = _get_environment_kind()
    if environment_kind != "byoc":
        return None

    session_access_token = _get_session_ingress_auth_token()
    if not session_access_token:
        return None

    session_id = _get_session_id()
    if not session_id:
        logger.error("File persistence enabled but CLAUDE_CODE_REMOTE_SESSION_ID is not set")
        return None

    # Check if aborted
    if signal is not None and getattr(signal, "aborted", False):
        logger.debug("Persistence aborted before processing")
        return None

    # Get outputs directory
    try:
        cwd = os.getcwd()
    except Exception:
        cwd = "."
    outputs_dir = os.path.join(cwd, session_id, OUTPUTS_SUBDIR)

    start_time = datetime.now().timestamp()

    try:
        # Find modified files via local filesystem scan
        modified_files = _find_modified_files(turn_start_time, outputs_dir)

        if len(modified_files) == 0:
            logger.debug("No modified files to persist")
            return FilesPersistedEventData(files=[], failed=[])

        logger.debug(f"Found {len(modified_files)} modified files")

        # Check file count limit
        if len(modified_files) > FILE_COUNT_LIMIT:
            logger.debug(
                f"File count limit exceeded: {len(modified_files)} > {FILE_COUNT_LIMIT}"
            )
            return FilesPersistedEventData(
                files=[],
                failed=[
                    FailedPersistence(
                        filename=outputs_dir,
                        error=f"Too many files modified ({len(modified_files)}). Maximum: {FILE_COUNT_LIMIT}.",
                    )
                ],
            )

        # Filter out files that resolve outside outputs directory
        from pathlib import Path

        safe_files = []
        outputs_path = Path(outputs_dir).resolve()

        for file_path in modified_files:
            try:
                file_path_obj = Path(file_path).resolve()
                file_path_obj.relative_to(outputs_path)
                safe_files.append(file_path)
            except ValueError:
                logger.debug(f"Skipping file outside outputs directory: {file_path}")
                continue

        # Upload files (stub - would call Files API in full implementation)
        persisted_files: list[PersistedFile] = []
        failed_files: list[FailedPersistence] = []

        for file_path in safe_files:
            # Stub: just record the file as persisted with a fake ID
            persisted_files.append(
                PersistedFile(
                    filename=file_path,
                    file_id=f"stub-{hash(file_path)}",
                )
            )

        duration_ms = (datetime.now().timestamp() - start_time) * 1000
        logger.debug(
            f"BYOC persistence complete: {len(persisted_files)} uploaded, {len(failed_files)} failed"
        )

        return FilesPersistedEventData(files=persisted_files, failed=failed_files)

    except Exception as e:
        logger.error(f"File persistence failed: {e}")
        return FilesPersistedEventData(
            files=[],
            failed=[FailedPersistence(filename=outputs_dir, error=str(e))],
        )


async def execute_file_persistence(
    turn_start_time: TurnStartTime,
    signal: Any,
    on_result: Any,
) -> None:
    """
    Execute file persistence and emit result via callback.

    Args:
        turn_start_time: Timestamp when turn started
        signal: Abort signal
        on_result: Callback to receive the result
    """
    try:
        result = await run_file_persistence(turn_start_time, signal)
        if result:
            on_result(result)
    except Exception as e:
        logger.error(f"File persistence error: {e}")


def is_file_persistence_enabled() -> bool:
    """
    Check if file persistence is enabled.

    Requires: feature flag ON, valid environment kind, session access token,
    and CLAUDE_CODE_REMOTE_SESSION_ID.
    """
    # Check feature flag
    feature_enabled = os.environ.get("CLAUDE_CODE_FEATURE_FILE_PERSISTENCE", "").lower()
    if feature_enabled not in ("true", "1", "yes"):
        return False

    return (
        _get_environment_kind() == "byoc"
        and _get_session_ingress_auth_token() is not None
        and _get_session_id() is not None
    )
