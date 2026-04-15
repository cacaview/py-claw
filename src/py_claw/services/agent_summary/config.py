"""
AgentSummary configuration.

Service for summarizing agent activities and performance.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSummaryConfig:
    """Configuration for AgentSummary service."""

    enabled: bool = True
    # Summary interval (seconds)
    summary_interval: int = 300
    # Include metrics in summary
    include_metrics: bool = True
    # Include recommendations
    include_recommendations: bool = True
    # Max history entries to consider
    max_history: int = 100

    @classmethod
    def from_settings(cls, settings: dict) -> AgentSummaryConfig:
        """Create config from settings dictionary."""
        as_settings = settings.get("agentSummary", {})
        return cls(
            enabled=as_settings.get("enabled", True),
            summary_interval=as_settings.get("summaryInterval", 300),
            include_metrics=as_settings.get("includeMetrics", True),
            include_recommendations=as_settings.get("includeRecommendations", True),
            max_history=as_settings.get("maxHistory", 100),
        )


# Global config instance
_config: AgentSummaryConfig | None = None


def get_agent_summary_config() -> AgentSummaryConfig:
    """Get the current AgentSummary configuration."""
    global _config
    if _config is None:
        _config = AgentSummaryConfig()
    return _config


def set_agent_summary_config(config: AgentSummaryConfig) -> None:
    """Set the AgentSummary configuration."""
    global _config
    _config = config
