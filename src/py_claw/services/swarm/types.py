"""
Swarm types.

Type definitions for the Swarm multi-agent system.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

# Teammate identity
TeammateIdentity = dict[str, Any]


@dataclass
class TeammateIdentity:
    """Identity information for a teammate."""

    agent_id: str
    agent_name: str
    team_name: str
    parent_session_id: str
    color: str | None = None
    plan_mode_required: bool = False


@dataclass
class TeammateContext:
    """Context information for a teammate."""

    identity: TeammateIdentity
    task_id: str
    mailbox_path: str | None = None


class SwarmMessage(TypedDict):
    """Base message in the swarm system."""

    from_: str  # sender ID
    text: str
    timestamp: str
    color: str | None
    read: bool = False


class MailboxEntry(TypedDict):
    """Entry in a mailbox."""

    from_: str
    text: str
    timestamp: str
    color: str | None
    read: bool


class IdleNotification(TypedDict):
    """Idle notification from a teammate."""

    type: Literal["idle"]
    from_: str
    idle_reason: Literal["available", "interrupted", "failed"]
    summary: str | None
    completed_task_id: str | None
    completed_status: Literal["resolved", "blocked", "failed"] | None
    failure_reason: str | None


class PermissionRequest(TypedDict):
    """Permission request from a teammate to the leader."""

    type: Literal["permission_request"]
    id: str
    tool_name: str
    tool_use_id: str
    input: dict[str, Any]
    description: str
    permission_suggestions: list[str]
    worker_id: str
    worker_name: str
    worker_color: str | None
    team_name: str


class PermissionResponse(TypedDict):
    """Permission response from the leader."""

    type: Literal["success", "error"]
    request_id: str
    subtype: Literal["success", "error"]
    response: dict[str, Any] | None
    error: str | None


class ShutdownRequest(TypedDict):
    """Shutdown request from the leader to a teammate."""

    type: Literal["shutdown"]
    from_: str
    reason: str | None


class PermissionUpdate(TypedDict):
    """Permission update from the leader."""

    tool_name: str
    permission: Literal["allow", "deny"]
    reason: str | None


# Result types
class InProcessRunnerResult(TypedDict):
    """Result from running an in-process teammate."""

    success: bool
    error: str | None
    messages: list[dict[str, Any]]


# Hook result types
class HookResult(TypedDict, total=False):
    """Result from a hook."""

    hook_id: str
    observations: list[str]
    prevent_continuation: bool
    stop_reason: str | None
    permission_behavior: Literal["allow", "deny"] | None
    blocking_error: Any | None
    system_message: str | None


# Task types
class Task(TypedDict):
    """Task in the task list."""

    id: str
    subject: str
    description: str | None
    status: Literal["pending", "in_progress", "completed", "failed"]
    owner: str | None
    blocked_by: list[str]
    created_at: str | None


@dataclass
class TaskClaimResult:
    """Result of claiming a task."""

    success: bool
    reason: str | None = None
