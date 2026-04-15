"""
Types for theme service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ThemeColor:
    """A theme color definition."""
    name: str
    hex: str
    ansi: int | None = None


@dataclass
class Theme:
    """A color theme."""
    name: str
    colors: dict[str, str]
    description: str | None = None


@dataclass
class ThemeResult:
    """Result of theme operation."""
    success: bool
    message: str
    theme: Theme | None = None
