"""
PromptSuggestion service.

Suggests prompts based on context using various strategies.
"""
from py_claw.services.prompt_suggestion.config import (
    PromptSuggestionConfig,
    get_prompt_suggestion_config,
    set_prompt_suggestion_config,
)
from py_claw.services.prompt_suggestion.service import (
    clear_suggestion_cache,
    get_suggestion_stats,
    get_suggestions,
)
from py_claw.services.prompt_suggestion.types import (
    PromptSuggestion,
    SuggestionCategory,
    SuggestionResult,
    SuggestionState,
    get_suggestion_state,
)


__all__ = [
    "PromptSuggestionConfig",
    "PromptSuggestion",
    "SuggestionCategory",
    "SuggestionResult",
    "SuggestionState",
    "get_prompt_suggestion_config",
    "set_prompt_suggestion_config",
    "get_suggestions",
    "clear_suggestion_cache",
    "get_suggestion_stats",
    "get_suggestion_state",
]
