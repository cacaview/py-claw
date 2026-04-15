"""Permissions utilities from TypeScript utils/permissions/ - auto mode state, classifiers."""

from __future__ import annotations

from .auto_mode_state import (
    is_auto_mode_active,
    set_auto_mode_active,
    clear_auto_mode,
)
from .classifier_decision import (
    is_auto_mode_allowlisted_tool,
    classify_yolo_action,
)
from .path_validation import (
    path_in_allowed_working_path,
    check_path_safety_for_auto_edit,
)
from .permission_explainer import (
    explain_permission_result,
)

__all__ = [
    "is_auto_mode_active",
    "set_auto_mode_active",
    "clear_auto_mode",
    "is_auto_mode_allowlisted_tool",
    "classify_yolo_action",
    "path_in_allowed_working_path",
    "check_path_safety_for_auto_edit",
    "explain_permission_result",
]
