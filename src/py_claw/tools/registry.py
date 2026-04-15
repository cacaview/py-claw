from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from py_claw.tasks import TaskRuntime
from py_claw.tools.base import Tool
from py_claw.tools.local_fs import GlobTool, GrepTool, NotebookEditTool, ReadTool, WriteTool
from py_claw.tools.file_edit_tool import FileEditTool
from py_claw.tools.ask_user_question_tool import AskUserQuestionTool
from py_claw.tools.agent_tools import AgentTool, SendMessageTool, TeamCreateTool, TeamDeleteTool
from py_claw.tools.brief_tool import BriefTool, SendUserFileTool, SendUserMessageTool
from py_claw.tools.local_shell import BashTool
from py_claw.tools.powershell import PowerShellTool
from py_claw.tools.mcp_resource_tools import ListMcpResourcesTool, ReadMcpResourceTool
from py_claw.tools.mcp_tool import MCPTool, ListMCPToolsTool
from py_claw.tools.plan_mode_tools import EnterPlanModeTool, ExitPlanModeTool
from py_claw.tools.schedule_cron_tool import CronCreateTool, CronDeleteTool, CronListTool
from py_claw.tools.skill_tool import SkillTool
from py_claw.tools.sleep_tool import SleepTool
from py_claw.tools.snip_tool import SnipTool
from py_claw.tools.synthetic_output_tool import SyntheticOutputTool
from py_claw.tools.task_tools import TaskCreateTool, TaskGetTool, TaskListTool, TaskOutputTool, TaskStopTool, TaskUpdateTool
from py_claw.tools.todo_write_tool import TodoWriteTool
from py_claw.tools.tool_search_tool import ToolSearchTool
from py_claw.tools.web_fetch_tool import WebFetchTool
from py_claw.tools.web_search_tool import WebSearchTool
from py_claw.tools.worktree_tools import EnterWorktreeTool, ExitWorktreeTool
from py_claw.tools.config_tool import ConfigTool, ConfigSetTool, ConfigListTool
from py_claw.tools.lsp_tool import LSPTool
from py_claw.tools.monitor_tool import MonitorTool
from py_claw.tools.terminal_capture_tool import TerminalCaptureTool
from py_claw.tools.verify_plan_execution_tool import VerifyPlanExecutionTool
from py_claw.tools.web_browser_tool import WebBrowserTool
from py_claw.tools.workflow_tool import WorkflowTool
from py_claw.tools.review_artifact_tool import ReviewArtifactTool


# Tools that are only accessible via REPL when REPL mode is enabled.
# When REPL mode is on, these tools are hidden from Claude's direct use,
# forcing Claude to use REPL for batch operations.
REPL_ONLY_TOOL_NAMES = frozenset([
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "NotebookEdit",
    "Agent",
])


def is_repl_mode_enabled() -> bool:
    """Detect whether REPL mode is enabled.

    REPL mode is default-on for interactive CLI (ant binary),
    but opt-out via CLAUDE_CODE_REPL=0.

    SDK entrypoints are NOT defaulted on — SDK consumers script
    direct tool calls and REPL mode hides those tools from the model.

    Enabled when:
    - CLAUDE_CODE_REPL is unset or truthy, OR
    - CLAUDE_REPL_MODE=1, AND
    - Not an SDK context (no SDK_URL override)
    """
    # Explicit disable wins
    repl_env = os.environ.get("CLAUDE_CODE_REPL", "")
    if repl_env in ("0", "false", "no"):
        return False

    # Explicit enable
    if repl_env in ("1", "true", "yes"):
        return True

    # Legacy flag
    if repl_env == "" and os.environ.get("CLAUDE_REPL_MODE", "") in ("1", "true", "yes"):
        return True

    # SDK context: disable REPL by default
    if os.environ.get("SDK_URL"):
        return False

    return False


@dataclass(slots=True)
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition.name] = tool

    def get(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)

    def require(self, tool_name: str) -> Tool:
        tool = self.get(tool_name)
        if tool is None:
            raise KeyError(f"Unknown tool: {tool_name}")
        return tool

    def values(self) -> list[Tool]:
        return list(self._tools.values())


def build_default_tool_registry(
    task_runtime: TaskRuntime | None = None,
    *,
    state: Any | None = None,
    repl_mode: bool | None = None,
) -> ToolRegistry:
    # Auto-detect REPL mode if not explicitly specified
    if repl_mode is None:
        repl_mode = is_repl_mode_enabled()

    registry = ToolRegistry()
    tasks = task_runtime or TaskRuntime()
    all_tools = [
        ReadTool(),
        FileEditTool(),
        WriteTool(),
        NotebookEditTool(),
        GlobTool(),
        GrepTool(),
        BashTool(tasks),
        PowerShellTool(tasks),
        AskUserQuestionTool(state),
        EnterPlanModeTool(state),
        ExitPlanModeTool(state),
        CronCreateTool(state),
        CronDeleteTool(state),
        CronListTool(state),
        EnterWorktreeTool(state),
        ExitWorktreeTool(state),
        ListMcpResourcesTool(state),
        ReadMcpResourceTool(state),
        ListMCPToolsTool(state),
        MCPTool(state),
        LSPTool(),
        AgentTool(state),
        TeamCreateTool(state),
        TeamDeleteTool(state),
        SendMessageTool(state),
        SendUserMessageTool(state),
        SendUserFileTool(state),
        BriefTool(state),
        WebFetchTool(),
        WebSearchTool(),
        SkillTool(),
        SleepTool(),
        SnipTool(state),
        SyntheticOutputTool(state),
        TodoWriteTool(state),
        ToolSearchTool(),
        TaskCreateTool(tasks),
        TaskGetTool(tasks),
        TaskListTool(tasks),
        TaskUpdateTool(tasks),
        TaskOutputTool(tasks),
        TaskStopTool(tasks),
        ConfigTool(state),
        ConfigSetTool(state),
        ConfigListTool(state),
        MonitorTool(tasks),
        TerminalCaptureTool(tasks),
        VerifyPlanExecutionTool(),
        WebBrowserTool(),
        WorkflowTool(),
        ReviewArtifactTool(),
    ]
    for tool in all_tools:
        tool_name = tool.definition.name
        # REPL mode: when enabled, only register REPL-only tools
        # (model uses REPL for batch operations, not direct tool calls)
        # Non-REPL mode: register all tools normally
        if repl_mode:
            if tool_name in REPL_ONLY_TOOL_NAMES:
                registry.register(tool)
        else:
            registry.register(tool)
    tool_search = registry.get("ToolSearch")
    if tool_search is not None and hasattr(tool_search, "bind_registry"):
        tool_search.bind_registry(registry)
    return registry
