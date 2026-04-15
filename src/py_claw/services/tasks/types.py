"""
Types for tasks service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """Task status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Task priority."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Task:
    """A task definition."""
    id: str
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    created_at: str | None = None
    updated_at: str | None = None
    tags: list[str] | None = None


@dataclass
class TasksConfig:
    """Configuration for tasks service."""
    max_tasks: int = 100


@dataclass
class TasksResult:
    """Result of tasks operation."""
    success: bool
    message: str
    tasks: list[Task] | None = None
