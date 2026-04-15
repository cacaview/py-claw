"""
Ultraplan service for CCR ExitPlanMode polling.

Based on ClaudeCode-main/src/utils/ultraplan/
"""
from py_claw.services.ultraplan.service import (
    create_exit_plan_mode_scanner,
    find_ultraplan_trigger_positions,
    get_ultraplan_info,
    has_ultraplan_keyword,
    poll_for_approval,
    replace_ultraplan_keyword,
)
from py_claw.services.ultraplan.types import (
    PollFailReason,
    ScanResult,
    UltraplanConfig,
    UltraplanPhase,
    UltraplanResult,
)


__all__ = [
    "create_exit_plan_mode_scanner",
    "find_ultraplan_trigger_positions",
    "has_ultraplan_keyword",
    "replace_ultraplan_keyword",
    "poll_for_approval",
    "get_ultraplan_info",
    "ExitPlanModeScanner",
    "UltraplanPhase",
    "PollFailReason",
    "ScanResult",
    "UltraplanConfig",
    "UltraplanResult",
]
