"""
Statistics aggregation from Claude Code session files.

Provides:
- Daily activity tracking (sessions, messages, tool calls)
- Model token usage per day
- Streak calculation (current/longest)
- Session duration stats
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    pass

# -----------------------------------------------------------------------------
# Data types
# -----------------------------------------------------------------------------

@dataclass
class DailyActivity:
    """Activity stats for a single day."""

    date: str  # YYYY-MM-DD
    message_count: int = 0
    session_count: int = 0
    tool_call_count: int = 0


@dataclass
class DailyModelTokens:
    """Token usage per model for a single day."""

    date: str  # YYYY-MM-DD
    tokens_by_model: dict[str, int] = field(default_factory=dict)


@dataclass
class StreakInfo:
    """Streak information."""

    current_streak: int = 0
    longest_streak: int = 0
    current_streak_start: str | None = None
    longest_streak_start: str | None = None
    longest_streak_end: str | None = None


@dataclass
class SessionStats:
    """Stats for a single session."""

    session_id: str
    duration: int  # milliseconds
    message_count: int
    timestamp: str


@dataclass
class ClaudeCodeStats:
    """Aggregated Claude Code statistics."""

    total_sessions: int = 0
    total_messages: int = 0
    total_days: int = 0
    active_days: int = 0
    streaks: StreakInfo = field(default_factory=StreakInfo)
    daily_activity: list[DailyActivity] = field(default_factory=list)
    daily_model_tokens: list[DailyModelTokens] = field(default_factory=list)
    longest_session: SessionStats | None = None
    model_usage: dict[str, dict] = field(default_factory=dict)
    first_session_date: str | None = None
    last_session_date: str | None = None
    peak_activity_day: str | None = None
    peak_activity_hour: int | None = None
    total_speculation_time_saved_ms: int = 0


# -----------------------------------------------------------------------------
# Date helpers
# -----------------------------------------------------------------------------

def to_date_string(dt: datetime) -> str:
    """Convert datetime to YYYY-MM-DD string."""
    return dt.strftime("%Y-%m-%d")


def get_today_date_string() -> str:
    """Get today's date as YYYY-MM-DD string."""
    return to_date_string(datetime.now())


def get_yesterday_date_string() -> str:
    """Get yesterday's date as YYYY-MM-DD string."""
    return to_date_string(datetime.now() - timedelta(days=1))


def is_date_before(date_str: str, other_str: str) -> bool:
    """Check if date_str < other_str (YYYY-MM-DD format)."""
    return date_str < other_str


def get_next_day(date_str: str) -> str:
    """Get the next day after a YYYY-MM-DD string."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return to_date_string(dt + timedelta(days=1))


# -----------------------------------------------------------------------------
# Session file processing
# -----------------------------------------------------------------------------

def get_projects_dir() -> Path:
    """Get the Claude projects directory."""
    from .path import get_home_dir

    home = get_home_dir()
    return home / ".claude" / "projects"


def get_all_session_files(projects_dir: Path) -> list[Path]:
    """Get all session .jsonl files from all project directories."""
    session_files: list[Path] = []

    try:
        entries = list(projects_dir.iterdir())
    except OSError:
        return []

    for entry in entries:
        if not entry.is_dir():
            continue
        try:
            sub_entries = list(entry.iterdir())
            for sub in sub_entries:
                if sub.is_file() and sub.suffix == ".jsonl":
                    session_files.append(sub)
        except OSError:
            continue

    return session_files


def parse_iso_string(s: str) -> datetime:
    """Parse an ISO format timestamp string to datetime."""
    s = s.replace("Z", "+00:00")
    parts = re.split(r"[-T:.+Z]", s)
    vals = [int(x) for x in parts[:7] if x.isdigit()]
    if len(vals) >= 6:
        year, month, day = vals[0], vals[1], vals[2]
        hour, minute, second = vals[3], vals[4], vals[5]
        microsecond = int(vals[6]) * 1000 if len(vals) > 6 else 0
        return datetime(year, month, day, hour, minute, second, microsecond)
    raise ValueError(f"Cannot parse: {s}")


@dataclass
class ProcessedStats:
    """Result of processing session files."""

    daily_activity: list[DailyActivity]
    daily_model_tokens: list[DailyModelTokens]
    model_usage: dict[str, dict]
    session_stats: list[SessionStats]
    hour_counts: dict[int, int]
    total_messages: int
    total_speculation_time_saved_ms: int


def process_session_files(
    session_files: list[Path],
    *,
    from_date: str | None = None,
    to_date: str | None = None,
) -> ProcessedStats:
    """
    Process session files and extract stats.
    Optionally filter by date range.
    """
    daily_activity_map: dict[str, DailyActivity] = {}
    daily_model_tokens_map: dict[str, dict[str, int]] = {}
    sessions: list[SessionStats] = []
    hour_counts: dict[int, int] = defaultdict(int)
    total_messages = 0
    total_speculation_time_saved_ms = 0
    model_usage: dict[str, dict] = defaultdict(
        lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "web_search_requests": 0,
            "cost_usd": 0,
        }
    )

    for session_file in session_files:
        try:
            content = session_file.read_text(encoding="utf-8")
        except OSError:
            continue

        messages: list[dict] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if not messages:
            continue

        # Get session metadata from filename
        session_id = session_file.stem

        # Find first user message for date
        first_message = None
        last_message = None
        for msg in messages:
            if isinstance(msg, dict) and msg.get("type") == "user":
                first_message = msg
                break

        if first_message:
            last_message = messages[-1] if messages else None
        else:
            continue

        # Get timestamp
        ts = first_message.get("timestamp") if first_message else None
        if not ts:
            continue

        try:
            first_ts = parse_iso_string(ts)
        except (ValueError, IndexError):
            continue

        date_key = to_date_string(first_ts)

        # Apply date filters
        if from_date and is_date_before(date_key, from_date):
            continue
        if to_date and is_date_before(to_date, date_key):
            continue

        # Update daily activity
        if date_key not in daily_activity_map:
            daily_activity_map[date_key] = DailyActivity(
                date=date_key, message_count=0, session_count=0, tool_call_count=0
            )

        # Count messages and tool calls
        msg_count = 0
        tool_calls = 0
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "user" or msg.get("type") == "assistant":
                msg_count += 1
            if msg.get("type") == "assistant":
                content = msg.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_calls += 1
                            # Update model usage
                            usage = msg.get("message", {}).get("usage", {})
                            model = msg.get("message", {}).get("model") or "unknown"
                            if usage:
                                model_usage[model]["input_tokens"] += usage.get("input_tokens", 0)
                                model_usage[model]["output_tokens"] += usage.get("output_tokens", 0)
                                model_usage[model]["cache_read_input_tokens"] += usage.get(
                                    "cache_read_input_tokens", 0
                                )
                                model_usage[model]["cache_creation_input_tokens"] += usage.get(
                                    "cache_creation_input_tokens", 0
                                )
                                # Track daily tokens
                                total_tokens = usage.get("input_tokens", 0) + usage.get(
                                    "output_tokens", 0
                                )
                                if total_tokens > 0:
                                    if date_key not in daily_model_tokens_map:
                                        daily_model_tokens_map[date_key] = {}
                                    daily_model_tokens_map[date_key][model] = (
                                        daily_model_tokens_map[date_key].get(model, 0) + total_tokens
                                    )

        if msg_count > 0:
            daily_activity_map[date_key].message_count += msg_count
            daily_activity_map[date_key].session_count += 1
            daily_activity_map[date_key].tool_call_count += tool_calls
            total_messages += msg_count

            # Calculate duration
            last_ts_str = last_message.get("timestamp") if last_message else None
            try:
                last_ts = parse_iso_string(last_ts_str) if last_ts_str else first_ts
            except (ValueError, IndexError):
                last_ts = first_ts

            duration_ms = int((last_ts - first_ts).total_seconds() * 1000)

            sessions.append(
                SessionStats(
                    session_id=session_id,
                    duration=duration_ms,
                    message_count=msg_count,
                    timestamp=ts,
                )
            )

            # Track hour distribution
            hour = first_ts.hour
            hour_counts[hour] += 1

    # Build result
    daily_activity = sorted(daily_activity_map.values(), key=lambda x: x.date)
    daily_model_tokens = [
        DailyModelTokens(date=date, tokens_by_model=tokens)
        for date, tokens in sorted(daily_model_tokens_map.items())
    ]

    return ProcessedStats(
        daily_activity=daily_activity,
        daily_model_tokens=daily_model_tokens,
        model_usage=dict(model_usage),
        session_stats=sessions,
        hour_counts=dict(hour_counts),
        total_messages=total_messages,
        total_speculation_time_saved_ms=total_speculation_time_saved_ms,
    )


# -----------------------------------------------------------------------------
# Streak calculation
# -----------------------------------------------------------------------------

def calculate_streaks(daily_activity: list[DailyActivity]) -> StreakInfo:
    """
    Calculate current and longest streaks from daily activity.

    A streak is a consecutive sequence of active days.
    """
    if not daily_activity:
        return StreakInfo()

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    active_dates = {a.date for a in daily_activity}

    # Calculate current streak (working backwards from today)
    current_streak = 0
    current_streak_start: str | None = None
    check_date = today

    while True:
        date_str = to_date_string(check_date)
        if date_str not in active_dates:
            break
        current_streak += 1
        current_streak_start = date_str
        check_date -= timedelta(days=1)

    # Calculate longest streak
    sorted_dates = sorted(active_dates)
    longest_streak = 0
    longest_streak_start: str | None = None
    longest_streak_end: str | None = None
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


# -----------------------------------------------------------------------------
# Main aggregation
# -----------------------------------------------------------------------------

async def aggregate_claude_code_stats(
    projects_dir: Path | None = None,
) -> ClaudeCodeStats:
    """
    Aggregate stats from all Claude Code sessions.

    Uses the projects directory to find session files.
    """
    if projects_dir is None:
        projects_dir = get_projects_dir()

    session_files = get_all_session_files(projects_dir)
    if not session_files:
        return ClaudeCodeStats()

    yesterday = get_yesterday_date_string()
    today = get_today_date_string()

    # Process historical data (up to yesterday)
    historical = process_session_files(
        session_files, from_date=None, to_date=yesterday
    )

    # Process today's data
    today_stats = process_session_files(session_files, from_date=today, to_date=today)

    # Merge results
    daily_activity_map: dict[str, DailyActivity] = {}
    for a in historical.daily_activity:
        daily_activity_map[a.date] = a

    for a in today_stats.daily_activity:
        if a.date in daily_activity_map:
            existing = daily_activity_map[a.date]
            existing.message_count += a.message_count
            existing.session_count += a.session_count
            existing.tool_call_count += a.tool_call_count
        else:
            daily_activity_map[a.date] = a

    daily_activity = sorted(daily_activity_map.values(), key=lambda x: x.date)
    streaks = calculate_streaks(daily_activity)

    # Find longest session
    longest_session = None
    for s in historical.session_stats:
        if longest_session is None or s.duration > longest_session.duration:
            longest_session = s
    for s in today_stats.session_stats:
        if longest_session is None or s.duration > longest_session.duration:
            longest_session = s

    # Find first/last session dates
    all_sessions = historical.session_stats + today_stats.session_stats
    first_date = None
    last_date = None
    for s in all_sessions:
        if first_date is None or s.timestamp < first_date:
            first_date = s.timestamp
        if last_date is None or s.timestamp > last_date:
            last_date = s.timestamp

    # Peak activity
    peak_day = None
    peak_messages = 0
    for a in daily_activity:
        if a.message_count > peak_messages:
            peak_messages = a.message_count
            peak_day = a.date

    peak_hour = None
    peak_hour_count = 0
    for hour, count in historical.hour_counts.items():
        if count > peak_hour_count:
            peak_hour_count = count
            peak_hour = hour

    return ClaudeCodeStats(
        total_sessions=len(all_sessions),
        total_messages=historical.total_messages + today_stats.total_messages,
        total_days=0,  # Would calculate from date range
        active_days=len(daily_activity),
        streaks=streaks,
        daily_activity=daily_activity,
        longest_session=longest_session,
        model_usage=historical.model_usage,
        first_session_date=first_date,
        last_session_date=last_date,
        peak_activity_day=peak_day,
        peak_activity_hour=peak_hour,
        total_speculation_time_saved_ms=(
            historical.total_speculation_time_saved_ms
            + today_stats.total_speculation_time_saved_ms
        ),
    )
