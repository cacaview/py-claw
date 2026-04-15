"""Types for file persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


class TurnStartTime(TypedDict):
    """Timestamp when the turn started."""

    value: float


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


# Constants
DEFAULT_UPLOAD_CONCURRENCY = 4
FILE_COUNT_LIMIT = 1000
OUTPUTS_SUBDIR = "outputs"
