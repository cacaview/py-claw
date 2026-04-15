"""API-based microcompact that uses native context management strategies."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


# Default values for context management strategies
DEFAULT_MAX_INPUT_TOKENS = 180_000  # Typical warning threshold
DEFAULT_TARGET_INPUT_TOKENS = 40_000  # Keep last 40k tokens

# Tools whose results can be cleared
TOOLS_CLEARABLE_RESULTS = (
    "Bash",
    "Glob",
    "Grep",
    "Read",
    "WebFetch",
    "WebSearch",
)

# Tools whose uses (not just results) can be cleared
TOOLS_CLEARABLE_USES = (
    "Edit",
    "Write",
    "NotebookEdit",
)


@dataclass(frozen=True, slots=True)
class InputTokenTrigger:
    """Trigger based on input token count."""

    type: Literal["input_tokens"]
    value: int


@dataclass(frozen=True, slots=True)
class ToolUsesKeep:
    """Keep last N tool uses."""

    type: Literal["tool_uses"]
    value: int


ClearableTools = bool | list[str] | None


@dataclass(frozen=True, slots=True)
class ClearToolUsesStrategy:
    """Strategy to clear tool uses by token threshold."""

    type: Literal["clear_tool_uses_20250919"]
    trigger: InputTokenTrigger | None = None
    keep: ToolUsesKeep | None = None
    clear_tool_inputs: ClearableTools = None
    exclude_tools: list[str] | None = None
    clear_at_least: InputTokenTrigger | None = None


@dataclass(frozen=True, slots=True)
class ClearThinkingStrategy:
    """Strategy to clear thinking blocks."""

    type: Literal["clear_thinking_20251015"]
    keep: Literal["all"] | dict[Literal["type", "value"], str | int] | None = None


ContextEditStrategy = ClearToolUsesStrategy | ClearThinkingStrategy


@dataclass(frozen=True, slots=True)
class ContextManagementConfig:
    """Configuration for API context management."""

    edits: list[ContextEditStrategy]


def get_api_context_management(
    *,
    has_thinking: bool = False,
    is_redact_thinking_active: bool = False,
    clear_all_thinking: bool = False,
) -> ContextManagementConfig | None:
    """
    Get API context management configuration.

    This implements API-based microcompact that uses native context management
    strategies supported by the API.

    Args:
        has_thinking: Whether thinking is enabled for the session
        is_redact_thinking_active: Whether think content is being redacted
        clear_all_thinking: Whether to clear all thinking (e.g., after >1h idle)

    Returns:
        ContextManagementConfig if any strategies are enabled, None otherwise
    """
    strategies: list[ContextEditStrategy] = []

    # Preserve thinking blocks in previous assistant turns
    # Skip when redact-thinking is active since redacted blocks have no model-visible content
    if has_thinking and not is_redact_thinking_active:
        if clear_all_thinking:
            # Keep only the last thinking turn (API schema requires value >= 1)
            strategies.append(
                ClearThinkingStrategy(
                    type="clear_thinking_20251015",
                    keep={"type": "thinking_turns", "value": 1},
                )
            )
        else:
            strategies.append(
                ClearThinkingStrategy(
                    type="clear_thinking_20251015",
                    keep="all",
                )
            )

    # Tool clearing strategies require ant environment
    if os.environ.get("USER_TYPE") != "ant":
        return strategies[0] if strategies else None

    use_clear_tool_results = os.environ.get("USE_API_CLEAR_TOOL_RESULTS")
    use_clear_tool_uses = os.environ.get("USE_API_CLEAR_TOOL_USES")

    if not use_clear_tool_results and not use_clear_tool_uses:
        return strategies[0] if strategies else None

    # Get thresholds from environment or use defaults
    trigger_threshold = int(os.environ.get("API_MAX_INPUT_TOKENS", DEFAULT_MAX_INPUT_TOKENS))
    keep_target = int(os.environ.get("API_TARGET_INPUT_TOKENS", DEFAULT_TARGET_INPUT_TOKENS))

    if use_clear_tool_results:
        strategies.append(
            ClearToolUsesStrategy(
                type="clear_tool_uses_20250919",
                trigger=InputTokenTrigger(type="input_tokens", value=trigger_threshold),
                clear_at_least=InputTokenTrigger(
                    type="input_tokens",
                    value=trigger_threshold - keep_target,
                ),
                clear_tool_inputs=list(TOOLS_CLEARABLE_RESULTS),
            )
        )

    if use_clear_tool_uses:
        strategies.append(
            ClearToolUsesStrategy(
                type="clear_tool_uses_20250919",
                trigger=InputTokenTrigger(type="input_tokens", value=trigger_threshold),
                clear_at_least=InputTokenTrigger(
                    type="input_tokens",
                    value=trigger_threshold - keep_target,
                ),
                exclude_tools=list(TOOLS_CLEARABLE_USES),
            )
        )

    return ContextManagementConfig(edits=strategies) if strategies else None
