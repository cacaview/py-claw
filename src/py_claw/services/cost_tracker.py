from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState

# Per-token pricing for Claude models (input, output, cache_read, cache_creation)
# All values are in USD per million tokens
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-20250514": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_creation": 18.75,
    },
    "claude-sonnet-4-20250514": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_creation": 3.75,
    },
    "claude-haiku-3-5-20241022": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_creation": 1.0,
    },
}

# Default fallback pricing (conservative estimate)
DEFAULT_PRICING = {
    "input": 3.0,
    "output": 15.0,
    "cache_read": 0.3,
    "cache_creation": 3.75,
}


def _get_pricing(model: str) -> dict[str, float]:
    """Get pricing for a model, falling back to default if not found."""
    normalized = model.lower()
    for model_name, pricing in MODEL_PRICING.items():
        if model_name.lower() in normalized or normalized in model_name.lower():
            return pricing
    return DEFAULT_PRICING


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_creation: int = 0,
) -> float:
    """Calculate cost in USD for the given token counts.

    Args:
        model: Model name to look up pricing
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_read: Number of cache read tokens
        cache_creation: Number of cache creation tokens

    Returns:
        Cost in USD
    """
    pricing = _get_pricing(model)
    cost = 0.0
    cost += (input_tokens / 1_000_000) * pricing["input"]
    cost += (output_tokens / 1_000_000) * pricing["output"]
    cost += (cache_read / 1_000_000) * pricing["cache_read"]
    cost += (cache_creation / 1_000_000) * pricing["cache_creation"]
    return cost


def accumulate_session_cost(
    state: RuntimeState,
    usage: dict[str, Any],
    model_usage: dict[str, Any],
    cost_usd: float,
    duration_ms: float,
) -> None:
    """Accumulate cost and token usage into RuntimeState.

    Args:
        state: RuntimeState to update
        usage: Usage dict from backend result
        model_usage: Model usage dict from backend result
        cost_usd: Cost in USD for this turn
        duration_ms: API duration in milliseconds
    """
    state.session_cost_usd += cost_usd
    state.session_input_tokens += int(usage.get("inputTokens", 0))
    state.session_output_tokens += int(usage.get("outputTokens", 0))
    state.session_cache_read_tokens += int(usage.get("cacheReadInputTokens", 0))
    state.session_cache_creation_tokens += int(usage.get("cacheCreationInputTokens", 0))
    state.session_api_duration_ms += duration_ms


def format_cost_report(state: RuntimeState) -> str:
    """Format a cost report for display.

    Args:
        state: RuntimeState with accumulated cost data

    Returns:
        Formatted string for display
    """
    lines = [
        "=== Session Cost Report ===",
        "",
        f"Total cost: ${state.session_cost_usd:.4f}",
        "",
        "Tokens:",
        f"  Input: {state.session_input_tokens:,}",
        f"  Output: {state.session_output_tokens:,}",
        f"  Cache read: {state.session_cache_read_tokens:,}",
        f"  Cache creation: {state.session_cache_creation_tokens:,}",
        f"  Total: {state.session_input_tokens + state.session_output_tokens + state.session_cache_read_tokens + state.session_cache_creation_tokens:,}",
        "",
        f"API time: {state.session_api_duration_ms:.0f}ms",
        f"Turns: {state.session_turn_count}",
    ]

    if state.cost_budget_usd is not None:
        lines.extend([
            "",
            "Budget:",
            f"  Cost budget: ${state.cost_budget_usd:.2f}",
            f"  Remaining: ${max(0.0, state.cost_budget_usd - state.session_cost_usd):.4f}",
        ])

    if state.token_budget is not None:
        total_tokens = state.session_input_tokens + state.session_output_tokens
        lines.extend([
            f"  Token budget: {state.token_budget:,}",
            f"  Token remaining: {max(0, state.token_budget - total_tokens):,}",
        ])

    return "\n".join(lines)


def check_budget_exceeded(state: RuntimeState) -> tuple[bool, str]:
    """Check if budget limits have been exceeded.

    Args:
        state: RuntimeState with budget settings

    Returns:
        Tuple of (exceeded, reason) where exceeded is True if budget is exceeded
    """
    if state.cost_budget_usd is not None and state.session_cost_usd > state.cost_budget_usd:
        return True, f"Cost budget exceeded: ${state.session_cost_usd:.4f} > ${state.cost_budget_usd:.2f}"

    if state.token_budget is not None:
        total_tokens = state.session_input_tokens + state.session_output_tokens
        if total_tokens > state.token_budget:
            return True, f"Token budget exceeded: {total_tokens:,} > {state.token_budget:,}"

    return False, ""
