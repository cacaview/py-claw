"""
AgentSummary service.

Summarizes agent activities and performance.
"""
from py_claw.services.agent_summary.config import (
    AgentSummaryConfig,
    get_agent_summary_config,
    set_agent_summary_config,
)
from py_claw.services.agent_summary.service import (
    generate_summary,
    generate_summary_with_ai,
    get_agent_stats,
    record_activity,
)
from py_claw.services.agent_summary.types import (
    AgentActivity,
    AgentActivityType,
    AgentMetrics,
    AgentSummary,
    AgentSummaryState,
    get_agent_summary_state,
)


__all__ = [
    "AgentSummaryConfig",
    "AgentActivity",
    "AgentActivityType",
    "AgentMetrics",
    "AgentSummary",
    "AgentSummaryState",
    "get_agent_summary_config",
    "set_agent_summary_config",
    "record_activity",
    "generate_summary",
    "generate_summary_with_ai",
    "get_agent_stats",
    "get_agent_summary_state",
]
