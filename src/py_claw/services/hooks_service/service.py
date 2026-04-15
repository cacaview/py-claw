"""
Hooks service for viewing and managing hook configurations.

This service wraps the existing hooks functionality from py_claw.hooks
and provides a service interface for the hooks command.
"""
from __future__ import annotations

import logging
from typing import Any

from .types import HookEntry, HookEvent, HooksServiceConfig, HooksServiceResult

logger = logging.getLogger(__name__)

_hooks_config = HooksServiceConfig()


def get_hooks_service_config() -> HooksServiceConfig:
    """Get the hooks service configuration."""
    return _hooks_config


def get_available_hook_events() -> list[HookEvent]:
    """Get all available hook events.

    Returns:
        List of HookEvent objects
    """
    # These are the hook events supported by py_claw
    return [
        HookEvent(
            name="on_tool_call",
            description="Called before a tool is executed",
            available=True,
        ),
        HookEvent(
            name="after_tool_call",
            description="Called after a tool executes",
            available=True,
        ),
        HookEvent(
            name="on_message",
            description="Called when a message is received",
            available=True,
        ),
        HookEvent(
            name="before_request",
            description="Called before making an API request",
            available=True,
        ),
        HookEvent(
            name="after_request",
            description="Called after an API request completes",
            available=True,
        ),
        HookEvent(
            name="on_error",
            description="Called when an error occurs",
            available=True,
        ),
        HookEvent(
            name="on_completion",
            description="Called when a completion is received",
            available=True,
        ),
        HookEvent(
            name="on_exit",
            description="Called before exiting",
            available=True,
        ),
        HookEvent(
            name="on_start",
            description="Called when Claude Code starts",
            available=True,
        ),
    ]


def get_configured_hooks(settings_hooks: dict[str, Any] | None = None) -> list[HookEntry]:
    """Get configured hooks from settings.

    Args:
        settings_hooks: Optional hooks dict from settings

    Returns:
        List of HookEntry objects
    """
    if not settings_hooks:
        return []

    hooks = []
    for event, command in settings_hooks.items():
        if isinstance(command, str):
            hooks.append(HookEntry(
                event=event,
                command=command,
                enabled=True,
            ))
        elif isinstance(command, dict):
            hooks.append(HookEntry(
                event=event,
                command=command.get("command", ""),
                enabled=command.get("enabled", True),
            ))
    return hooks


def format_hooks_info(settings_hooks: dict[str, Any] | None = None) -> str:
    """Format hooks information as text.

    Args:
        settings_hooks: Optional hooks dict from settings

    Returns:
        Formatted hooks information
    """
    available = get_available_hook_events()
    configured = get_configured_hooks(settings_hooks)
    configured_map = {h.event: h for h in configured}

    lines = [
        "Claude Code Hooks",
        "=" * 40,
        "",
        "Available hook events:",
    ]

    for event in available:
        status = "configured" if event.name in configured_map else "not configured"
        lines.append(f"  - {event.name}: {event.description} [{status}]")

    lines.append("")
    lines.append("Configured hooks:")

    if configured:
        for hook in configured:
            lines.append(f"  - {hook.event}: {hook.command}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("To configure hooks, edit ~/.claude/settings.json:")
    lines.append('  { "hooks": { "on_tool_call": "echo $TOOL_NAME" } }')

    return "\n".join(lines)


def validate_hook_command(command: str) -> HooksServiceResult:
    """Validate a hook command.

    Args:
        command: The command to validate

    Returns:
        HooksServiceResult with validation status
    """
    if not command:
        return HooksServiceResult(
            success=False,
            message="Hook command cannot be empty",
        )

    if len(command) > 1000:
        return HooksServiceResult(
            success=False,
            message="Hook command too long (max 1000 characters)",
        )

    # Check for dangerous patterns
    dangerous = ["rm -rf /", "dd if=", "> /dev/sda", ":(){:|:&};:"]
    for pattern in dangerous:
        if pattern in command:
            return HooksServiceResult(
                success=False,
                message=f"Hook command contains dangerous pattern: {pattern}",
            )

    return HooksServiceResult(
        success=True,
        message="Hook command is valid",
    )
