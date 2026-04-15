"""
Tasks service for task lifecycle management.

Manages all task types including local shell tasks, local agent tasks,
and background workflows. Handles task creation, state management, stopping.
"""
from __future__ import annotations

import logging
from typing import Any

from .types import Task, TaskPriority, TasksConfig, TasksResult, TaskStatus

logger = logging.getLogger(__name__)

_tasks_config = TasksConfig()


def get_tasks_config() -> TasksConfig:
    """Get the tasks service configuration."""
    return _tasks_config


def get_available_tasks() -> list[Task]:
    """Get all available tasks.

    Returns:
        List of Task objects
    """
    # This would integrate with the actual task runtime
    # For now, return an empty list as a placeholder
    return []


def get_task_by_id(task_id: str) -> Task | None:
    """Get a task by ID.

    Args:
        task_id: The task ID

    Returns:
        Task object or None if not found
    """
    tasks = get_available_tasks()
    for task in tasks:
        if task.id == task_id:
            return task
    return None


def is_background_task(task: Task) -> bool:
    """Check if task is a background task.

    Args:
        task: The task to check

    Returns:
        True if task runs in background
    """
    return task.status in (
        TaskStatus.PENDING,
        TaskStatus.IN_PROGRESS,
    )


def get_pill_label(tasks: list[Task]) -> str:
    """Generate pill label for background tasks.

    Args:
        tasks: List of tasks

    Returns:
        Formatted pill label string
    """
    if not tasks:
        return ""

    running = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
    pending = [t for t in tasks if t.status == TaskStatus.PENDING]

    parts = []
    if running:
        parts.append(f"{len(running)} running")
    if pending:
        parts.append(f"{len(pending)} pending")

    return f"Tasks: {', '.join(parts)}" if parts else ""


def format_tasks_text(tasks: list[Task]) -> str:
    """Format tasks as plain text.

    Args:
        tasks: List of Task objects

    Returns:
        Formatted text
    """
    if not tasks:
        return "No tasks."

    lines = ["Tasks:", ""]
    for task in tasks:
        status_marker = {
            TaskStatus.PENDING: "[ ]",
            TaskStatus.IN_PROGRESS: "[~]",
            TaskStatus.COMPLETED: "[x]",
            TaskStatus.FAILED: "[!]",
            TaskStatus.CANCELLED: "[-]",
        }.get(task.status, "[?]")

        lines.append(f"{status_marker} {task.title}")
        if task.description:
            lines.append(f"    {task.description}")
        lines.append(f"    ID: {task.id}, Priority: {task.priority.value}")
        lines.append("")

    return "\n".join(lines)


def get_tasks_info() -> TasksResult:
    """Get tasks information.

    Returns:
        TasksResult with task list
    """
    try:
        tasks = get_available_tasks()
        return TasksResult(
            success=True,
            message=f"Found {len(tasks)} tasks",
            tasks=tasks,
        )
    except Exception as e:
        logger.exception("Error getting tasks")
        return TasksResult(
            success=False,
            message=f"Error: {e}",
        )
