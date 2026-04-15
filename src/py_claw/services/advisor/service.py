"""
Advisor service.

Advisor tool functions for the advisor model integration.

Based on ClaudeCode-main/src/utils/advisor.ts
"""
from __future__ import annotations

import os
from typing import Any

from .types import (
    ADVISOR_TOOL_INSTRUCTIONS,
    AdvisorBlock,
    AdvisorConfig,
    ExperimentAdvisorModels,
)


# Environment variable to disable advisor
CLAUDE_CODE_DISABLE_ADVISOR_TOOL = "CLAUDE_CODE_DISABLE_ADVISOR_TOOL"

# Environment variable for user type
USER_TYPE = os.environ.get("USER_TYPE", "")


def _is_env_truthy(env_var: str | None) -> bool:
    """Check if an environment variable is set to a truthy value."""
    if not env_var:
        return False
    return env_var.lower() in ("1", "true", "yes")


def _get_advisor_config() -> AdvisorConfig:
    """
    Get advisor configuration from GrowthBook experiment.

    In Python, we use a simplified config since GrowthBook integration
    may not be available. Returns default values.

    Returns:
        AdvisorConfig with experiment values
    """
    # In a full implementation, this would call GrowthBook
    # For now, return disabled config
    return AdvisorConfig(enabled=False, can_user_configure=False)


def is_advisor_enabled() -> bool:
    """
    Check if the advisor feature is enabled.

    Returns:
        True if advisor is enabled via GrowthBook experiment
        and not disabled via environment variable
    """
    if _is_env_truthy(os.environ.get(CLAUDE_CODE_DISABLE_ADVISOR_TOOL)):
        return False

    # Check if first-party only betas are included
    # In Python, we assume first-party only betas are included
    # since there's no equivalent to shouldIncludeFirstPartyOnlyBetas()

    config = _get_advisor_config()
    return config.enabled


def can_user_configure_advisor() -> bool:
    """
    Check if users can manually configure the advisor model.

    Returns:
        True if advisor is enabled and users can configure it
    """
    if not is_advisor_enabled():
        return False

    config = _get_advisor_config()
    return config.can_user_configure


def get_experiment_advisor_models() -> ExperimentAdvisorModels | None:
    """
    Get the advisor models from experiment config.

    Returns:
        ExperimentAdvisorModels if experiment is active and user can't configure,
        None otherwise
    """
    if not is_advisor_enabled():
        return None

    config = _get_advisor_config()
    if config.can_user_configure:
        return None

    if not config.base_model or not config.advisor_model:
        return None

    return ExperimentAdvisorModels(
        base_model=config.base_model,
        advisor_model=config.advisor_model,
    )


def model_supports_advisor(model: str) -> bool:
    """
    Check whether the main loop model supports calling the advisor tool.

    Args:
        model: Model name to check

    Returns:
        True if the model supports advisor tool
    """
    m = model.lower()
    return (
        "opus-4-6" in m
        or "sonnet-4-6" in m
        or USER_TYPE == "ant"
    )


def is_valid_advisor_model(model: str) -> bool:
    """
    Check if a model can serve as an advisor model.

    Args:
        model: Model name to validate

    Returns:
        True if the model is a valid advisor model
    """
    m = model.lower()
    return (
        "opus-4-6" in m
        or "sonnet-4-6" in m
        or USER_TYPE == "ant"
    )


def is_advisor_block(param: dict[str, Any]) -> bool:
    """
    Check if a block is an advisor block.

    Args:
        param: Block to check (must have 'type' key)

    Returns:
        True if the block is an advisor block
    """
    if param.get("type") == "advisor_tool_result":
        return True
    if param.get("type") == "server_tool_use" and param.get("name") == "advisor":
        return True
    return False


def get_initial_advisor_setting() -> str | None:
    """
    Get the initial advisor setting from user settings.

    Returns:
        Advisor model from settings, or None if not enabled
    """
    if not is_advisor_enabled():
        return None

    # In a full implementation, this would read from settings
    return None


def get_advisor_usage(
    usage: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extract advisor usage from BetaUsage.

    Args:
        usage: BetaUsage object with iterations

    Returns:
        List of advisor message iterations
    """
    iterations = usage.get("iterations")
    if not iterations:
        return []

    return [
        it for it in iterations
        if isinstance(it, dict) and it.get("type") == "advisor_message"
    ]
