"""
Types for the tool use summary service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolInfo:
    """Information about a tool that was executed."""

    name: str
    input: Any
    output: Any


@dataclass(slots=True)
class GenerateToolUseSummaryParams:
    """Parameters for generating a tool use summary."""

    tools: list[ToolInfo]
    is_non_interactive_session: bool
    last_assistant_text: str | None = None
