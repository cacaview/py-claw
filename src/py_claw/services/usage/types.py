"""
Types for usage service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TokenUsage:
    """Token usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class CostInfo:
    """Cost information."""
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0


@dataclass
class UsageStats:
    """Usage statistics."""
    sessions: int = 0
    messages: int = 0
    tokens: TokenUsage = None  # type: ignore[assignment]
    cost: CostInfo = None  # type: ignore[assignment]
    period_start: str | None = None
    period_end: str | None = None

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = TokenUsage()
        if self.cost is None:
            self.cost = CostInfo()


@dataclass
class UsageResult:
    """Result of usage query."""
    success: bool
    message: str
    usage: UsageStats | None = None
