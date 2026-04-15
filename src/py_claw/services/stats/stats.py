"""Session stats aggregation - mirrors ClaudeCode-main/src/utils/debug.ts.

This module provides:
- Daily activity tracking (sessions, messages, tool calls)
- Token usage aggregation by model
- Streak calculation (current and longest)
- Claude Code stats aggregation from session files
- Shot distribution tracking (ant-only feature)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# Type definitions

DateString = str  # YYYY-MM-DD format


@dataclass(slots=True)
class DailyActivity:
    """Daily activity summary."""

    date: DateString  # YYYY-MM-DD format
    message_count: int = 0
    session_count: int = 0
    tool_call_count: int = 0


@dataclass(slots=True)
class DailyModelTokens:
    """Daily token usage per model."""

    date: DateString  # YYYY-MM-DD format
    tokens_by_model: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class StreakInfo:
    """Streak information."""

    current_streak: int = 0
    longest_streak: int = 0
    current_streak_start: DateString | None = None
    longest_streak_start: DateString | None = None
    longest_streak_end: DateString | None = None


@dataclass(slots=True)
class SessionStats:
    """Stats for a single session."""

    session_id: str
    duration: int  # milliseconds
    message_count: int
    timestamp: str  # ISO timestamp


@dataclass(slots=True)
class ModelUsage:
    """Model usage statistics."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    web_search_requests: int = 0
    cost_usd: float = 0.0
    context_window: int = 0
    max_output_tokens: int = 0


@dataclass(slots=True)
class ClaudeCodeStats:
    """Complete Claude Code statistics."""

    # Activity overview
    total_sessions: int = 0
    total_messages: int = 0
    total_days: int = 0
    active_days: int = 0

    # Streaks
    streaks: StreakInfo = field(default_factory=StreakInfo)

    # Daily activity for heatmap
    daily_activity: list[DailyActivity] = field(default_factory=list)

    # Daily token usage per model for charts
    daily_model_tokens: list[DailyModelTokens] = field(default_factory=list)

    # Session info
    longest_session: SessionStats | None = None

    # Model usage aggregated
    model_usage: dict[str, ModelUsage] = field(default_factory=dict)

    # Time stats
    first_session_date: DateString | None = None
    last_session_date: DateString | None = None
    peak_activity_day: DateString | None = None
    peak_activity_hour: int | None = None

    # Speculation time saved
    total_speculation_time_saved_ms: int = 0

    # Shot stats (ant-only)
    shot_distribution: dict[int, int] | None = None
    one_shot_rate: int | None = None


# Stats date range options
StatsDateRange = str  # '7d' | '30d' | 'all'


def to_date_string(date: datetime) -> DateString:
    """Convert datetime to YYYY-MM-DD string.

    Args:
        date: Datetime to convert

    Returns:
        Date string in YYYY-MM-DD format
    """
    return date.strftime("%Y-%m-%d")


def get_today_date_string() -> DateString:
    """Get today's date as YYYY-MM-DD string."""
    return to_date_string(datetime.now(timezone.utc))


def get_yesterday_date_string() -> DateString:
    """Get yesterday's date as YYYY-MM-DD string."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    return to_date_string(yesterday)


def is_date_before(date_str: DateString, other: DateString) -> bool:
    """Check if date is before another date.

    Args:
        date_str: First date (YYYY-MM-DD)
        other: Second date (YYYY-MM-DD)

    Returns:
        True if date_str < other
    """
    return date_str < other


def get_next_day(date_str: DateString) -> DateString:
    """Get the next day after a given date string.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Next day in YYYY-MM-DD format
    """
    date = datetime.strptime(date_str, "%Y-%m-%d")
    next_date = date + timedelta(days=1)
    return to_date_string(next_date)


def calculate_streaks(daily_activity: list[DailyActivity]) -> StreakInfo:
    """Calculate streak information from daily activity.

    Args:
        daily_activity: Sorted list of daily activity entries

    Returns:
        StreakInfo with current and longest streak data
    """
    if not daily_activity:
        return StreakInfo()

    today = datetime.now(timezone.utc)
    today = today.replace(hour=0, minute=0, second=0, microsecond=0)

    # Build set of active dates
    active_dates = {day.date for day in daily_activity}

    # Calculate current streak (working backwards from today)
    current_streak = 0
    current_streak_start: DateString | None = None
    check_date = today

    while True:
        date_str = to_date_string(check_date)
        if date_str not in active_dates:
            break
        current_streak += 1
        current_streak_start = date_str
        check_date -= timedelta(days=1)

    # Calculate longest streak
    longest_streak = 0
    longest_streak_start: DateString | None = None
    longest_streak_end: DateString | None = None

    sorted_dates = sorted(active_dates)
    if sorted_dates:
        temp_streak = 1
        temp_start = sorted_dates[0]

        for i in range(1, len(sorted_dates)):
            prev_date = datetime.strptime(sorted_dates[i - 1], "%Y-%m-%d")
            curr_date = datetime.strptime(sorted_dates[i], "%Y-%m-%d")

            day_diff = (curr_date - prev_date).days

            if day_diff == 1:
                temp_streak += 1
            else:
                if temp_streak > longest_streak:
                    longest_streak = temp_streak
                    longest_streak_start = temp_start
                    longest_streak_end = sorted_dates[i - 1]
                temp_streak = 1
                temp_start = sorted_dates[i]

        # Check final streak
        if temp_streak > longest_streak:
            longest_streak = temp_streak
            longest_streak_start = temp_start
            longest_streak_end = sorted_dates[-1]

    return StreakInfo(
        current_streak=current_streak,
        longest_streak=longest_streak,
        current_streak_start=current_streak_start,
        longest_streak_start=longest_streak_start,
        longest_streak_end=longest_streak_end,
    )


def get_empty_stats() -> ClaudeCodeStats:
    """Get an empty stats object with zero values.

    Returns:
        ClaudeCodeStats initialized to empty/zero values
    """
    return ClaudeCodeStats(
        streaks=StreakInfo(),
        daily_activity=[],
        daily_model_tokens=[],
        longest_session=None,
        model_usage={},
        first_session_date=None,
        last_session_date=None,
        peak_activity_day=None,
        peak_activity_hour=None,
        total_speculation_time_saved_ms=0,
    )


async def aggregate_claude_code_stats() -> ClaudeCodeStats:
    """Aggregate stats from all Claude Code sessions across all projects.

    Uses a disk cache to avoid reprocessing historical data.

    Returns:
        Complete ClaudeCodeStats aggregation
    """
    # Placeholder - actual implementation would:
    # 1. Get all session files from projects directory
    # 2. Load and merge with cache
    # 3. Process today's data live
    # 4. Return aggregated stats
    return get_empty_stats()


async def aggregate_claude_code_stats_for_range(
    range: StatsDateRange,
) -> ClaudeCodeStats:
    """Aggregate stats for a specific date range.

    Args:
        range: Date range ('7d', '30d', or 'all')

    Returns:
        ClaudeCodeStats for the specified range
    """
    if range == "all":
        return await aggregate_claude_code_stats()

    # Calculate from date
    today = datetime.now(timezone.utc)
    days_back = 7 if range == "7d" else 30
    from_date = today - timedelta(days=days_back - 1)  # +1 to include today

    # Placeholder - would process session files for date range
    return get_empty_stats()


async def read_session_start_date(file_path: str) -> DateString | None:
    """Peek at session file to get start date without reading full file.

    Uses a small 4KB read to extract the session start date.
    This is used as an optimization to skip files outside date ranges.

    Args:
        file_path: Path to session JSONL file

    Returns:
        Session start date (YYYY-MM-DD) or None if not found
    """
    import json

    TRANSCRIPT_MESSAGE_TYPES = {"user", "assistant", "attachment", "system", "progress"}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Read first 4KB
            head = f.read(4096)

        if not head:
            return None

        # Find last complete line
        last_newline = head.rfind("\n")
        if last_newline < 0:
            return None

        content = head[:last_newline]

        for line in content.split("\n"):
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Check type
            entry_type = entry.get("type")
            if entry_type not in TRANSCRIPT_MESSAGE_TYPES:
                continue

            # Skip sidechain
            if entry.get("isSidechain") is True:
                continue

            # Get timestamp
            timestamp = entry.get("timestamp")
            if not isinstance(timestamp, str):
                return None

            try:
                date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return to_date_string(date)
            except (ValueError, TypeError):
                return None

        return None

    except (OSError, IOError):
        return None


# Shot count extraction (ant-only feature)
SHOT_COUNT_REGEX = r"(\d+)-shotted by"


def extract_shot_count_from_messages(messages: list[dict]) -> int | None:
    """Extract shot count from PR attribution in gh pr create calls.

    The attribution format is: "N-shotted by model-name"

    Args:
        messages: List of transcript messages

    Returns:
        Shot count or None if not found
    """
    import re

    SHELL_TOOL_NAMES = {"Bash", "bash", "Shell", "shell"}

    for message in messages:
        if message.get("type") != "assistant":
            continue

        content = message.get("message", {}).get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if block.get("type") != "tool_use":
                continue

            name = block.get("name")
            if name not in SHELL_TOOL_NAMES:
                continue

            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                continue

            command = tool_input.get("command")
            if not isinstance(command, str):
                continue

            match = re.search(SHOT_COUNT_REGEX, command)
            if match:
                return int(match.group(1))

    return None
