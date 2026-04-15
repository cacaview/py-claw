"""
Context Collapse configuration.

Service for collapsing context windows while preserving key information.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextCollapseConfig:
    """Configuration for ContextCollapse service."""

    enabled: bool = True
    # Minimum tokens before collapse triggers
    min_tokens: int = 8000
    # Target tokens after collapse
    target_tokens: int = 4000
    # Preserve recent messages count
    preserve_recent_messages: int = 5
    # Collapse strategy: "boundary", "importance", "hybrid"
    strategy: str = "hybrid"
    # Whether to use summarization
    use_summarization: bool = True
    # Importance scoring threshold
    importance_threshold: float = 0.5

    @classmethod
    def from_settings(cls, settings: dict) -> ContextCollapseConfig:
        """Create config from settings dictionary."""
        cc_settings = settings.get("contextCollapse", {})
        return cls(
            enabled=cc_settings.get("enabled", True),
            min_tokens=cc_settings.get("minTokens", 8000),
            target_tokens=cc_settings.get("targetTokens", 4000),
            preserve_recent_messages=cc_settings.get("preserveRecentMessages", 5),
            strategy=cc_settings.get("strategy", "hybrid"),
            use_summarization=cc_settings.get("useSummarization", True),
            importance_threshold=cc_settings.get("importanceThreshold", 0.5),
        )


# Global config instance
_config: ContextCollapseConfig | None = None


def get_context_collapse_config() -> ContextCollapseConfig:
    """Get the current ContextCollapse configuration."""
    global _config
    if _config is None:
        _config = ContextCollapseConfig()
    return _config


def set_context_collapse_config(config: ContextCollapseConfig) -> None:
    """Set the ContextCollapse configuration."""
    global _config
    _config = config
