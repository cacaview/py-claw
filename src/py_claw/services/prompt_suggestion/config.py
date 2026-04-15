"""
PromptSuggestion configuration.

Service for suggesting prompts based on context.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSuggestionConfig:
    """Configuration for PromptSuggestion service."""

    enabled: bool = True
    # Maximum suggestions to return
    max_suggestions: int = 5
    # Minimum context length for suggestions
    min_context_length: int = 100
    # Suggestion categories
    categories: list[str] | None = None
    # API client for generating suggestions
    use_api: bool = True
    # Cache suggestions
    cache_enabled: bool = True
    # Cache TTL in seconds
    cache_ttl: int = 300

    def __post_init__(self) -> None:
        if self.categories is None:
            self.categories = ["coding", "review", "debug", "refactor", "docs"]

    @classmethod
    def from_settings(cls, settings: dict) -> PromptSuggestionConfig:
        """Create config from settings dictionary."""
        ps_settings = settings.get("promptSuggestion", {})
        return cls(
            enabled=ps_settings.get("enabled", True),
            max_suggestions=ps_settings.get("maxSuggestions", 5),
            min_context_length=ps_settings.get("minContextLength", 100),
            categories=ps_settings.get("categories", ["coding", "review", "debug", "refactor", "docs"]),
            use_api=ps_settings.get("useApi", True),
            cache_enabled=ps_settings.get("cacheEnabled", True),
            cache_ttl=ps_settings.get("cacheTtl", 300),
        )


# Global config instance
_config: PromptSuggestionConfig | None = None


def get_prompt_suggestion_config() -> PromptSuggestionConfig:
    """Get the current PromptSuggestion configuration."""
    global _config
    if _config is None:
        _config = PromptSuggestionConfig()
    return _config


def set_prompt_suggestion_config(config: PromptSuggestionConfig) -> None:
    """Set the PromptSuggestion configuration."""
    global _config
    _config = config
