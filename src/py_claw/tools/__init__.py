from typing import Any

from py_claw.tools.ask_user_question_tool import AskUserQuestionTool
from py_claw.tools.agent_tools import SendMessageTool
from py_claw.tools.base import Tool, ToolDefinition, ToolError, ToolPermissionError
from py_claw.tools.brief_tool import BriefTool, SendUserFileTool, SendUserMessageTool
from py_claw.tools.mcp_resource_tools import ListMcpResourcesTool, ReadMcpResourceTool
from py_claw.tools.plan_mode_tools import EnterPlanModeTool, ExitPlanModeTool
from py_claw.tools.schedule_cron_tool import CronCreateTool, CronDeleteTool, CronListTool
from py_claw.tools.registry import ToolRegistry, build_default_tool_registry
from py_claw.tools.runtime import ToolExecutionResult, ToolRuntime, ToolRuntimePermissionTarget
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
from py_claw.tools.monitor_tool import MonitorTool
from py_claw.tools.terminal_capture_tool import TerminalCaptureTool
from py_claw.tools.verify_plan_execution_tool import VerifyPlanExecutionTool
from py_claw.tools.web_browser_tool import WebBrowserTool
from py_claw.tools.workflow_tool import WorkflowTool
from py_claw.tools.review_artifact_tool import ReviewArtifactTool


def __getattr__(name: str) -> Any:
    if name == "AgentTool":
        from py_claw.tools.agent_tools import AgentTool

        return AgentTool
    if name == "TeamCreateTool":
        from py_claw.tools.agent_tools import TeamCreateTool

        return TeamCreateTool
    if name == "TeamDeleteTool":
        from py_claw.tools.agent_tools import TeamDeleteTool

        return TeamDeleteTool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



__all__ = [
    "AgentTool",
    "TeamCreateTool",
    "TeamDeleteTool",
    "SendMessageTool",
    "BriefTool",
    "SendUserMessageTool",
    "SendUserFileTool",
    "AskUserQuestionTool",
    "Tool",
    "ToolDefinition",
    "ToolError",
    "ToolPermissionError",
    "ToolRegistry",
    "ToolRuntime",
    "ToolRuntimePermissionTarget",
    "ToolExecutionResult",
    "EnterPlanModeTool",
    "ExitPlanModeTool",
    "CronCreateTool",
    "CronDeleteTool",
    "CronListTool",
    "EnterWorktreeTool",
    "ExitWorktreeTool",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
    "SkillTool",
    "SleepTool",
    "SnipTool",
    "SyntheticOutputTool",
    "TodoWriteTool",
    "ToolSearchTool",
    "TaskCreateTool",
    "TaskGetTool",
    "TaskListTool",
    "TaskUpdateTool",
    "TaskOutputTool",
    "TaskStopTool",
    "WebFetchTool",
    "WebSearchTool",
    "MonitorTool",
    "TerminalCaptureTool",
    "VerifyPlanExecutionTool",
    "WebBrowserTool",
    "WorkflowTool",
    "ReviewArtifactTool",
    "build_default_tool_registry",
]
