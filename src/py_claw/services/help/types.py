"""
Types for help service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HelpCategory:
    """A category of help topics."""
    name: str
    description: str
    topics: list["HelpTopic"]


@dataclass
class HelpTopic:
    """A help topic."""
    id: str
    title: str
    content: str
    related_topics: list[str] | None = None


@dataclass
class HelpConfig:
    """Configuration for help service."""
    show_tips: bool = True
    show_shortcuts: bool = True
