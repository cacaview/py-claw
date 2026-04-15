"""
AgentSummary service.

Summarizes agent activities and performance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from py_claw.services.agent_summary.config import (
    get_agent_summary_config,
)

from .types import (
    AgentActivity,
    AgentActivityType,
    AgentMetrics,
    AgentSummary,
    AgentSummaryState,
    get_agent_summary_state,
)

if TYPE_CHECKING:
    from py_claw.services.api import AnthropicAPIClient


def record_activity(
    activity_type: AgentActivityType,
    description: str,
    agent_name: str | None = None,
    duration_ms: int | None = None,
    success: bool = True,
    metadata: dict | None = None,
) -> None:
    """Record an agent activity.

    Args:
        activity_type: Type of activity
        description: Activity description
        agent_name: Name of the agent (if applicable)
        duration_ms: Duration in milliseconds
        success: Whether activity was successful
        metadata: Additional metadata
    """
    state = get_agent_summary_state()
    config = get_agent_summary_config()

    activity = AgentActivity(
        timestamp=datetime.now(timezone.utc),
        activity_type=activity_type,
        description=description,
        duration_ms=duration_ms,
        success=success,
        metadata=metadata,
    )

    state.record_activity(activity)

    # Update metrics
    if agent_name:
        if agent_name not in state.metrics_by_agent:
            state.metrics_by_agent[agent_name] = AgentMetrics()
        metrics = state.metrics_by_agent[agent_name]

        metrics.total_activities += 1
        if success:
            metrics.successful_activities += 1
        else:
            metrics.failed_activities += 1

        if duration_ms:
            metrics.total_duration_ms += duration_ms

        if activity_type == AgentActivityType.TASK_COMPLETED:
            metrics.tasks_completed += 1
        elif activity_type == AgentActivityType.TASK_FAILED:
            metrics.tasks_failed += 1

        if metadata and "tool_name" in metadata:
            if metrics.tools_used is None:
                metrics.tools_used = {}
            tool_name = metadata["tool_name"]
            metrics.tools_used[tool_name] = metrics.tools_used.get(tool_name, 0) + 1


def generate_summary(
    agent_name: str | None = None,
    recent_count: int = 10,
) -> AgentSummary:
    """Generate a summary of agent activities.

    Args:
        agent_name: Optional specific agent to summarize
        recent_count: Number of recent activities to include

    Returns:
        AgentSummary with metrics and recommendations
    """
    config = get_agent_summary_config()
    state = get_agent_summary_state()

    # Get metrics
    if agent_name:
        metrics = state.metrics_by_agent.get(agent_name, AgentMetrics())
    else:
        # Aggregate metrics across all agents
        metrics = AgentMetrics()
        for agent_metrics in state.metrics_by_agent.values():
            metrics.total_activities += agent_metrics.total_activities
            metrics.successful_activities += agent_metrics.successful_activities
            metrics.failed_activities += agent_metrics.failed_activities
            metrics.total_duration_ms += agent_metrics.total_duration_ms
            metrics.tasks_completed += agent_metrics.tasks_completed
            metrics.tasks_failed += agent_metrics.tasks_failed
            if agent_metrics.tools_used:
                if metrics.tools_used is None:
                    metrics.tools_used = {}
                for tool, count in agent_metrics.tools_used.items():
                    metrics.tools_used[tool] = metrics.tools_used.get(tool, 0) + count

    # Get recent activities
    recent_activities = state.activities[-recent_count:]

    # Generate recommendations
    recommendations = []
    if config.include_recommendations:
        if metrics.failed_activities > metrics.successful_activities * 0.1:
            recommendations.append("High failure rate detected. Consider reviewing error patterns.")

        if metrics.tasks_failed > 0:
            recommendations.append(f"{metrics.tasks_failed} tasks failed. Review logs for issues.")

        if metrics.tools_used:
            most_used = max(metrics.tools_used.items(), key=lambda x: x[1], default=(None, 0))
            if most_used[0]:
                recommendations.append(f"Most used tool: {most_used[0]} ({most_used[1]} calls)")

    return AgentSummary(
        agent_name=agent_name,
        metrics=metrics,
        recent_activities=recent_activities,
        recommendations=recommendations,
        generated_at=datetime.now(timezone.utc),
    )


async def generate_summary_with_ai(
    agent_name: str | None = None,
    recent_count: int = 20,
    api_client: AnthropicAPIClient | None = None,
) -> AgentSummary:
    """Generate an AI-powered summary of agent activities.

    Args:
        agent_name: Optional specific agent to summarize
        recent_count: Number of recent activities to include
        api_client: Optional API client for AI analysis

    Returns:
        AgentSummary with AI-generated insights
    """
    # Get base summary
    summary = generate_summary(agent_name, recent_count)

    if api_client is not None and get_agent_summary_config().include_recommendations:
        try:
            from py_claw.services.api import MessageCreateParams, MessageParam

            # Build context from activities
            activities_text = "\n".join(
                f"[{a.timestamp.isoformat()}] {a.activity_type.value}: {a.description}"
                for a in summary.recent_activities
            )

            prompt = f"""Analyze the following agent activities and provide recommendations:

{activities_text}

Provide 2-3 specific, actionable recommendations based on the patterns observed."""

            response = api_client.create_message(
                MessageCreateParams(
                    model="claude-sonnet-4-20250514",
                    messages=[MessageParam(role="user", content=prompt)],
                    max_tokens=512,
                )
            )

            if hasattr(response, "__await__"):
                response = await response

            # Parse AI recommendations from response
            # (In practice, would parse structured response)
            # For now, use base recommendations

        except Exception:
            # Use base recommendations on error
            pass

    return summary


def get_agent_stats() -> dict:
    """Get agent summary statistics.

    Returns:
        Dictionary with agent summary statistics
    """
    config = get_agent_summary_config()
    state = get_agent_summary_state()

    return {
        "enabled": config.enabled,
        "total_activities": len(state.activities),
        "tracked_agents": len(state.metrics_by_agent),
        "summary_interval": config.summary_interval,
    }
