"""
PromptSuggestion service.

Suggests prompts based on context using various strategies.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from py_claw.services.prompt_suggestion.config import (
    get_prompt_suggestion_config,
)

from .types import (
    PromptSuggestion,
    SuggestionCategory,
    SuggestionResult,
    SuggestionState,
    get_suggestion_state,
)

if TYPE_CHECKING:
    from py_claw.services.api import AnthropicAPIClient


def _compute_context_hash(context: str) -> str:
    """Compute hash of context for caching."""
    return hashlib.md5(context.encode("utf-8")).hexdigest()[:16]


def _get_context_suggestions(context: str) -> list[PromptSuggestion]:
    """Get suggestions based on context analysis.

    This is a rule-based approach that analyzes keywords
    in the context to suggest relevant prompts.
    """
    config = get_prompt_suggestion_config()
    context_lower = context.lower()
    suggestions: list[PromptSuggestion] = []

    # Coding-related keywords
    coding_keywords = ["code", "function", "class", "implement", "bug", "fix", "error", "exception"]
    if any(kw in context_lower for kw in coding_keywords):
        suggestions.append(PromptSuggestion(
            text="Can you explain how this code works?",
            category=SuggestionCategory.CODING,
            relevance_score=0.8,
            description="Get explanation of code",
        ))
        suggestions.append(PromptSuggestion(
            text="What improvements would you suggest for this code?",
            category=SuggestionCategory.REFACTOR,
            relevance_score=0.7,
            description="Get code improvement suggestions",
        ))

    # Review-related keywords
    review_keywords = ["review", "pr", "pull request", "merge", "diff", "changes"]
    if any(kw in context_lower for kw in review_keywords):
        suggestions.append(PromptSuggestion(
            text="Review these changes for potential issues",
            category=SuggestionCategory.REVIEW,
            relevance_score=0.9,
            description="Review code changes",
        ))
        suggestions.append(PromptSuggestion(
            text="Are there any security concerns with these changes?",
            category=SuggestionCategory.REVIEW,
            relevance_score=0.8,
            description="Check for security issues",
        ))

    # Debug-related keywords
    debug_keywords = ["debug", "bug", "crash", "fail", "error", "exception", "issue"]
    if any(kw in context_lower for kw in debug_keywords):
        suggestions.append(PromptSuggestion(
            text="Help me debug this issue step by step",
            category=SuggestionCategory.DEBUG,
            relevance_score=0.9,
            description="Debug assistance",
        ))
        suggestions.append(PromptSuggestion(
            text="What could be causing this error?",
            category=SuggestionCategory.DEBUG,
            relevance_score=0.8,
            description="Error analysis",
        ))

    # Refactor-related keywords
    refactor_keywords = ["refactor", "restructure", "rewrite", "improve", "clean"]
    if any(kw in context_lower for kw in refactor_keywords):
        suggestions.append(PromptSuggestion(
            text="Suggest a refactoring plan for this code",
            category=SuggestionCategory.REFACTOR,
            relevance_score=0.9,
            description="Get refactoring suggestions",
        ))

    # Docs-related keywords
    docs_keywords = ["documentation", "docs", "readme", "comment", "explain"]
    if any(kw in context_lower for kw in docs_keywords):
        suggestions.append(PromptSuggestion(
            text="Generate documentation for this code",
            category=SuggestionCategory.DOCS,
            relevance_score=0.8,
            description="Documentation generation",
        ))

    # If no specific suggestions, add general ones
    if not suggestions:
        suggestions.append(PromptSuggestion(
            text="What would you like to do next with this?",
            category=SuggestionCategory.GENERAL,
            relevance_score=0.5,
            description="General next step",
        ))
        suggestions.append(PromptSuggestion(
            text="Can you summarize the key points?",
            category=SuggestionCategory.GENERAL,
            relevance_score=0.6,
            description="Get summary",
        ))

    return suggestions[:config.max_suggestions]


async def get_suggestions(
    context: str,
    api_client: AnthropicAPIClient | None = None,
    category: SuggestionCategory | None = None,
) -> SuggestionResult:
    """Get prompt suggestions based on context.

    Args:
        context: Current context (file content, conversation, etc.)
        api_client: Optional API client for AI-powered suggestions
        category: Optional category filter

    Returns:
        SuggestionResult with list of suggestions
    """
    config = get_prompt_suggestion_config()
    state = get_suggestion_state()

    if not config.enabled:
        return SuggestionResult(
            suggestions=[],
            generated_at=datetime.now(timezone.utc),
        )

    # Check cache
    context_hash = _compute_context_hash(context)
    if config.cache_enabled:
        cached = state.get_cached(context_hash, config.cache_ttl)
        if cached is not None:
            filtered = cached if category is None else [s for s in cached if s.category == category]
            return SuggestionResult(
                suggestions=filtered,
                context_hash=context_hash,
                generated_at=datetime.now(timezone.utc),
                from_cache=True,
            )

    # Get base suggestions
    suggestions = _get_context_suggestions(context)

    # Use API for enhanced suggestions if enabled
    if api_client is not None and config.use_api and len(suggestions) < config.max_suggestions:
        try:
            from py_claw.services.api import MessageCreateParams, MessageParam

            prompt = f"""Based on the following context, suggest {config.max_suggestions - len(suggestions)} helpful prompts.
Return suggestions as a JSON array of objects with 'text', 'category', and 'relevance_score' fields.

Context:
{context[:2000]}"""

            response = api_client.create_message(
                MessageCreateParams(
                    model="claude-sonnet-4-20250514",
                    messages=[MessageParam(role="user", content=prompt)],
                    max_tokens=1024,
                )
            )

            if hasattr(response, "__await__"):
                response = await response

            # Parse API response and add suggestions
            # (In practice, this would parse JSON from the response)
            # For now, we skip this as it requires response parsing

        except Exception:
            # Fall back to rule-based suggestions
            pass

    # Filter by category if specified
    if category is not None:
        suggestions = [s for s in suggestions if s.category == category]

    # Cache results
    if config.cache_enabled:
        state.set_cached(context_hash, suggestions)

    return SuggestionResult(
        suggestions=suggestions,
        context_hash=context_hash,
        generated_at=datetime.now(timezone.utc),
        from_cache=False,
    )


def clear_suggestion_cache() -> None:
    """Clear the suggestion cache."""
    state = get_suggestion_state()
    state.clear_cache()


def get_suggestion_stats() -> dict:
    """Get suggestion service statistics.

    Returns:
        Dictionary with suggestion statistics
    """
    config = get_prompt_suggestion_config()
    state = get_suggestion_state()

    return {
        "enabled": config.enabled,
        "max_suggestions": config.max_suggestions,
        "cache_enabled": config.cache_enabled,
        "total_suggestions_generated": state.total_suggestions,
        "cache_size": len(state.cache),
    }
