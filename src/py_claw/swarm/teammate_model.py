"""
Teammate Model Module

Provides model selection utilities for teammates.

Based on ClaudeCode-main/src/utils/swarm/teammateModel.ts
"""

from __future__ import annotations

# Default model configurations for teammates
# These should be aligned with the API provider settings
TEAMMATE_MODEL_CONFIGS = {
    "anthropic": {
        "default": "claude-opus-4-6-5",
        "fallback": "claude-sonnet-4-7-20260220",
    },
    "bedrock": {
        "default": "arn:aws:bedrock:us-east-1:agent:application-inference-prod:claude-opus-4-6-5",
        "fallback": "arn:aws:bedrock:us-east-1:agent:application-inference-prod:claude-sonnet-4-7-20260220",
    },
    "vertex": {
        "default": "claude-opus-4-6-5@community.vertex.ai",
        "fallback": "claude-sonnet-4-7-20260220@community.vertex.ai",
    },
    "foundry": {
        "default": "claude-opus-4-6-5",
        "fallback": "claude-sonnet-4-7-20260220",
    },
}


def get_hardcoded_teammate_model_fallback(provider: str = "anthropic") -> str:
    """Get the hardcoded default model for teammates.

    When the user has never set teammateDefaultModel in /config, new teammates
    use Opus 4.6. Must be provider-aware so Bedrock/Vertex/Foundry customers get
    the correct model ID.

    Args:
        provider: API provider name (anthropic, bedrock, vertex, foundry)

    Returns:
        The default model ID for teammates
    """
    config = TEAMMATE_MODEL_CONFIGS.get(provider, TEAMMATE_MODEL_CONFIGS["anthropic"])
    return config["default"]


def get_teammate_model_fallback(provider: str = "anthropic") -> str:
    """Get the fallback model for teammates.

    This is used when the primary default model is unavailable.

    Args:
        provider: API provider name

    Returns:
        The fallback model ID
    """
    config = TEAMMATE_MODEL_CONFIGS.get(provider, TEAMMATE_MODEL_CONFIGS["anthropic"])
    return config["fallback"]


__all__ = [
    "TEAMMATE_MODEL_CONFIGS",
    "get_hardcoded_teammate_model_fallback",
    "get_teammate_model_fallback",
]
