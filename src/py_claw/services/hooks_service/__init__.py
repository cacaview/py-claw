"""
Hooks service for viewing and managing hook configurations.

Based on ClaudeCode-main/src/services/hooks/

This service provides a service interface for the hooks command,
wrapping the existing hooks functionality from py_claw.hooks.
"""
from py_claw.services.hooks_service.service import (
    format_hooks_info,
    get_available_hook_events,
    get_configured_hooks,
    get_hooks_service_config,
    validate_hook_command,
)
from py_claw.services.hooks_service.types import (
    HookEntry,
    HookEvent,
    HooksServiceConfig,
    HooksServiceResult,
)


__all__ = [
    "get_hooks_service_config",
    "get_available_hook_events",
    "get_configured_hooks",
    "format_hooks_info",
    "validate_hook_command",
    "HookEntry",
    "HookEvent",
    "HooksServiceConfig",
    "HooksServiceResult",
]
