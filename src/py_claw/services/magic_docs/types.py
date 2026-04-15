"""
MagicDocs types.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MagicDoc:
    """A magic documentation file."""

    path: Path
    title: str
    last_updated: datetime
    size_bytes: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class MagicDocUpdate:
    """Result of a magic doc update operation."""

    path: Path
    success: bool
    message: str
    lines_added: int = 0
    lines_removed: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MagicDocStats:
    """Statistics about magic docs."""

    total_docs: int
    total_size_bytes: int
    last_scan: datetime | None
    updates_count: int
    errors_count: int
