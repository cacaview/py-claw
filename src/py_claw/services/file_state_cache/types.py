"""Types for file state cache."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FileState:
    """Represents the cached state of a file.

    Used to share file read state between parent and forked agents
    for prompt cache friendliness and avoiding redundant reads.
    """
    content: str
    timestamp: float
    offset: int | None = None
    limit: int | None = None
    is_partial_view: bool = False
