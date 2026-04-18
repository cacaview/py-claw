"""Speculation execution service.

Provides pipelined suggestion execution with overlay copy-on-write isolation.
"""

from py_claw.services.speculation.analytics import log_speculation
from py_claw.services.speculation.constants import (
    MAX_SPECULATION_MESSAGES,
    MAX_SPECULATION_TURNS,
    READ_ONLY_COMMANDS,
    SAFE_READ_ONLY_TOOLS,
    WRITE_TOOLS,
)
from py_claw.services.speculation.overlay import (
    OverlayManager,
    create_overlay,
    get_overlay_base,
    remove_overlay,
)
from py_claw.services.speculation.read_only_check import (
    ReadOnlyCheckResult,
    check_read_only_constraints,
    check_tool_in_speculation,
)
from py_claw.services.speculation.service import (
    SpeculationResult,
    SpeculationService,
    get_speculation_service,
)

__all__ = [
    # Service
    "SpeculationService",
    "SpeculationResult",
    "get_speculation_service",
    # Overlay
    "OverlayManager",
    "create_overlay",
    "get_overlay_base",
    "remove_overlay",
    # Analytics
    "log_speculation",
    # Constraints
    "check_read_only_constraints",
    "check_tool_in_speculation",
    "ReadOnlyCheckResult",
    # Constants
    "WRITE_TOOLS",
    "SAFE_READ_ONLY_TOOLS",
    "READ_ONLY_COMMANDS",
    "MAX_SPECULATION_TURNS",
    "MAX_SPECULATION_MESSAGES",
]
