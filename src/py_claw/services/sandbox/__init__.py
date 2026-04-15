"""Sandbox adapter utilities - wraps sandbox-runtime with Claude CLI-specific integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .sandbox_adapter import (
    SandboxManager,
    SandboxRuntimeConfig,
    SandboxViolationEvent,
    resolve_path_pattern_for_sandbox,
    resolve_sandbox_filesystem_path,
    is_sandboxing_enabled,
    get_sandbox_unavailable_reason,
)

__all__ = [
    "SandboxManager",
    "SandboxRuntimeConfig",
    "SandboxViolationEvent",
    "resolve_path_pattern_for_sandbox",
    "resolve_sandbox_filesystem_path",
    "is_sandboxing_enabled",
    "get_sandbox_unavailable_reason",
]
