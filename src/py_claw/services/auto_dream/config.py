"""
AutoDream configuration.

Background memory consolidation service that triggers /dream prompt.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AutoDreamConfig:
    """Configuration for AutoDream service."""

    enabled: bool = False
    # Minimum messages before auto dream triggers
    min_messages: int = 10
    # Minimum tokens before auto dream triggers
    min_tokens: int = 5000
    # Interval between dream checks (seconds)
    check_interval: int = 300
    # Whether to run dream in background
    run_in_background: bool = True
    # Dream prompt template
    prompt_template: str | None = None

    @classmethod
    def from_settings(cls, settings: dict) -> AutoDreamConfig:
        """Create config from settings dictionary."""
        auto_dream_settings = settings.get("autoDream", {})
        return cls(
            enabled=auto_dream_settings.get("enabled", False),
            min_messages=auto_dream_settings.get("minMessages", 10),
            min_tokens=auto_dream_settings.get("minTokens", 5000),
            check_interval=auto_dream_settings.get("checkInterval", 300),
            run_in_background=auto_dream_settings.get("runInBackground", True),
            prompt_template=auto_dream_settings.get("promptTemplate"),
        )


# Global config instance
_config: AutoDreamConfig | None = None


def get_auto_dream_config() -> AutoDreamConfig:
    """Get the current AutoDream configuration."""
    global _config
    if _config is None:
        _config = AutoDreamConfig()
    return _config


def set_auto_dream_config(config: AutoDreamConfig) -> None:
    """Set the AutoDream configuration."""
    global _config
    _config = config


# Default dream prompt
DEFAULT_DREAM_PROMPT = """You are about to dream. Reflect on the following aspects of this session:

1. Key decisions made and their rationale
2. Patterns observed in user requests
3. Useful techniques or approaches discovered
4. Things to remember for future sessions
5. Any unresolved issues or follow-ups needed

Compile your reflections into a concise memory entry."""
