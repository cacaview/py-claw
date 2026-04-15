"""
Usage service for tracking and displaying usage information.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from .types import CostInfo, TokenUsage, UsageResult, UsageStats

logger = logging.getLogger(__name__)

# Price per million tokens (approximate)
PRICING = {
    "claude-opus": {"input": 15.0, "output": 75.0},
    "claude-sonnet": {"input": 3.0, "output": 15.0},
    "claude-haiku": {"input": 0.25, "output": 1.25},
}


def get_usage_storage_path() -> Path:
    """Get the path to usage data storage.

    Returns:
        Path to usage.json
    """
    config_dir = Path.home() / ".claude"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "usage.json"


def load_usage_data() -> dict:
    """Load usage data from storage.

    Returns:
        Usage data dictionary
    """
    path = get_usage_storage_path()
    if not path.exists():
        return {"sessions": [], "total": {}}

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Error loading usage data: %s", e)
        return {"sessions": [], "total": {}}


def save_usage_data(data: dict) -> None:
    """Save usage data to storage.

    Args:
        data: Usage data to save
    """
    path = get_usage_storage_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        logger.error("Error saving usage data: %s", e)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> CostInfo:
    """Calculate cost for token usage.

    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        CostInfo with cost breakdown
    """
    # Find pricing tier
    model_lower = model.lower()
    if "opus" in model_lower:
        tier = PRICING["claude-opus"]
    elif "sonnet" in model_lower:
        tier = PRICING["claude-sonnet"]
    elif "haiku" in model_lower:
        tier = PRICING["claude-haiku"]
    else:
        tier = PRICING["claude-sonnet"]  # Default

    input_cost = (input_tokens / 1_000_000) * tier["input"]
    output_cost = (output_tokens / 1_000_000) * tier["output"]

    return CostInfo(
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=input_cost + output_cost,
    )


def get_usage_stats(period_days: int = 30) -> UsageStats:
    """Get usage statistics for the specified period.

    Args:
        period_days: Number of days to include in stats

    Returns:
        UsageStats with aggregated usage
    """
    data = load_usage_data()
    sessions_data = data.get("sessions", [])
    total_data = data.get("total", {})

    # Filter sessions by date
    cutoff = datetime.now() - timedelta(days=period_days)
    recent_sessions = []

    for session in sessions_data:
        try:
            timestamp = session.get("timestamp")
            if timestamp:
                if isinstance(timestamp, str):
                    session_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                else:
                    session_date = datetime.fromtimestamp(timestamp)

                if session_date >= cutoff:
                    recent_sessions.append(session)
        except Exception:
            pass

    # Aggregate stats
    total_messages = sum(s.get("messages", 0) for s in recent_sessions)
    total_input = sum(s.get("input_tokens", 0) for s in recent_sessions)
    total_output = sum(s.get("output_tokens", 0) for s in recent_sessions)

    tokens = TokenUsage(
        input_tokens=total_input,
        output_tokens=total_output,
        total_tokens=total_input + total_output,
    )

    # Get most common model from sessions
    models = [s.get("model", "unknown") for s in recent_sessions]
    most_common_model = max(set(models), default="claude-sonnet") if models else "claude-sonnet"

    cost = calculate_cost(most_common_model, total_input, total_output)

    return UsageStats(
        sessions=len(recent_sessions),
        messages=total_messages,
        tokens=tokens,
        cost=cost,
        period_start=cutoff.isoformat(),
        period_end=datetime.now().isoformat(),
    )


def get_usage_info() -> UsageResult:
    """Get usage information.

    Returns:
        UsageResult with usage statistics
    """
    try:
        stats = get_usage_stats()
        return UsageResult(
            success=True,
            message="Usage information retrieved",
            usage=stats,
        )
    except Exception as e:
        logger.exception("Error getting usage info")
        return UsageResult(
            success=False,
            message=f"Error getting usage info: {e}",
        )


def format_usage_text(result: UsageResult, period_days: int = 30) -> str:
    """Format usage result as plain text.

    Args:
        result: UsageResult to format
        period_days: Number of days in the period

    Returns:
        Formatted usage text
    """
    if not result.success or not result.usage:
        return f"Error: {result.message}"

    usage = result.usage
    lines = [
        f"Claude Code Usage (last {period_days} days)",
        "=" * 40,
        "",
        f"Sessions: {usage.sessions}",
        f"Messages: {usage.messages}",
        "",
        "Token Usage:",
        f"  Input:  {usage.tokens.input_tokens:,}",
        f"  Output: {usage.tokens.output_tokens:,}",
        f"  Total:  {usage.tokens.total_tokens:,}",
        "",
        "Estimated Cost:",
        f"  Input:  ${usage.cost.input_cost:.4f}",
        f"  Output: ${usage.cost.output_cost:.4f}",
        f"  Total:  ${usage.cost.total_cost:.4f}",
        "",
    ]

    if usage.period_start:
        lines.append(f"Period: {usage.period_start[:10]} to {usage.period_end[:10] if usage.period_end else 'now'}")

    return "\n".join(lines)
