"""
Advisor service module.

Advisor tool functions for the advisor model integration.

Based on ClaudeCode-main/src/utils/advisor.ts
"""
from py_claw.services.advisor.service import (
    ADVISOR_TOOL_INSTRUCTIONS,
    can_user_configure_advisor,
    get_advisor_usage,
    get_experiment_advisor_models,
    get_initial_advisor_setting,
    is_advisor_block,
    is_advisor_enabled,
    is_valid_advisor_model,
    model_supports_advisor,
)
from py_claw.services.advisor.types import (
    ADVISOR_TOOL_INSTRUCTIONS as ADVISOR_TOOL_INSTRUCTIONS_CONST,
    AdvisorBlock,
    AdvisorConfig,
    AdvisorErrorContent,
    AdvisorRedactedContent,
    AdvisorResultContent,
    AdvisorServerToolUseBlock,
    AdvisorToolResultBlock,
    ExperimentAdvisorModels,
)


__all__ = [
    # Service functions
    "can_user_configure_advisor",
    "get_advisor_usage",
    "get_experiment_advisor_models",
    "get_initial_advisor_setting",
    "is_advisor_block",
    "is_advisor_enabled",
    "is_valid_advisor_model",
    "model_supports_advisor",
    # Types
    "AdvisorBlock",
    "AdvisorConfig",
    "AdvisorErrorContent",
    "AdvisorRedactedContent",
    "AdvisorResultContent",
    "AdvisorServerToolUseBlock",
    "AdvisorToolResultBlock",
    "ExperimentAdvisorModels",
    # Constants
    "ADVISOR_TOOL_INSTRUCTIONS",
]
