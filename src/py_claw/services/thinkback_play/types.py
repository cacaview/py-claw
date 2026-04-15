"""
Types for thinkback_play service.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThinkbackPlayResult:
    """Result of playing thinkback animation."""
    success: bool
    message: str
