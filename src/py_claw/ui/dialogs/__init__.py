from __future__ import annotations

"""UI dialogs — High-level dialog components."""

from py_claw.ui.dialogs.agent import AgentDeleteConfirm, AgentEditor, AgentsMenu
from py_claw.ui.dialogs.chrome import ChromeDialog
from py_claw.ui.dialogs.config import ConfigDialog
from py_claw.ui.dialogs.context import ContextDialog
from py_claw.ui.dialogs.desktop_handoff import DesktopHandoff
from py_claw.ui.dialogs.mcp import MCPServerDialog, MCPServerTestDialog
from py_claw.ui.dialogs.permission import PermissionDialog
from py_claw.ui.dialogs.skill import SkillDetailDialog, SkillsDialog
from py_claw.ui.dialogs.trust import TrustDialog
from py_claw.ui.dialogs.workflow import WorkflowMultiselectDialog
from py_claw.ui.dialogs.worktree import WorktreeExitDialog

__all__ = [
    "AgentDeleteConfirm",
    "AgentEditor",
    "AgentsMenu",
    "ChromeDialog",
    "ConfigDialog",
    "ContextDialog",
    "DesktopHandoff",
    "MCPServerDialog",
    "MCPServerTestDialog",
    "PermissionDialog",
    "SkillDetailDialog",
    "SkillsDialog",
    "TrustDialog",
    "WorkflowMultiselectDialog",
    "WorktreeExitDialog",
]
