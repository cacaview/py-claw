"""Tests for services/stats module - session stats aggregation.

These tests cover the stats aggregation functionality from
ClaudeCode-main/src/utils/debug.ts.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from py_claw.services.stats.stats import (
    ClaudeCodeStats,
    DailyActivity,
    DailyModelTokens,
    ModelUsage,
    SessionStats,
    StatsDateRange,
    StreakInfo,
    calculate_streaks,
    extract_shot_count_from_messages,
    get_empty_stats,
    get_next_day,
    get_today_date_string,
    get_yesterday_date_string,
    is_date_before,
    read_session_start_date,
    to_date_string,
)


class TestToDateString:
    """Tests for to_date_string function."""

    def test_basic_conversion(self):
        """Test basic datetime to date string."""
        date = datetime(2024, 1, 15, 10, 30, 0, 0, tzinfo=timezone.utc)
        result = to_date_string(date)
        assert result == "2024-01-15"

    def test_leading_zeros(self):
        """Test that month and day have leading zeros."""
        date = datetime(2024, 3, 5, 0, 0, 0, 0, tzinfo=timezone.utc)
        result = to_date_string(date)
        assert result == "2024-03-05"


class TestDateHelpers:
    """Tests for date helper functions."""

    def test_get_today_date_string(self):
        """Test get_today_date_string returns valid format."""
        result = get_today_date_string()
        assert isinstance(result, str)
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"

    def test_get_yesterday_date_string(self):
        """Test get_yesterday_date_string returns valid format."""
        result = get_yesterday_date_string()
        assert isinstance(result, str)
        assert len(result) == 10

    def test_is_date_before(self):
        """Test date comparison."""
        assert is_date_before("2024-01-01", "2024-01-02") is True
        assert is_date_before("2024-01-02", "2024-01-01") is False
        assert is_date_before("2024-01-01", "2024-01-01") is False

    def test_get_next_day(self):
        """Test get_next_day."""
        assert get_next_day("2024-01-01") == "2024-01-02"
        assert get_next_day("2024-01-31") == "2024-02-01"
        assert get_next_day("2024-12-31") == "2025-01-01"


class TestDailyActivity:
    """Tests for DailyActivity dataclass."""

    def test_daily_activity_creation(self):
        """Test creating DailyActivity."""
        activity = DailyActivity(
            date="2024-01-15",
            message_count=10,
            session_count=2,
            tool_call_count=5,
        )
        assert activity.date == "2024-01-15"
        assert activity.message_count == 10
        assert activity.session_count == 2
        assert activity.tool_call_count == 5

    def test_daily_activity_defaults(self):
        """Test DailyActivity default values."""
        activity = DailyActivity(date="2024-01-15")
        assert activity.message_count == 0
        assert activity.session_count == 0
        assert activity.tool_call_count == 0


class TestDailyModelTokens:
    """Tests for DailyModelTokens dataclass."""

    def test_daily_model_tokens_creation(self):
        """Test creating DailyModelTokens."""
        tokens = DailyModelTokens(
            date="2024-01-15",
            tokens_by_model={"claude-3": 1000, "claude-3-5": 2000},
        )
        assert tokens.date == "2024-01-15"
        assert tokens.tokens_by_model["claude-3"] == 1000
        assert tokens.tokens_by_model["claude-3-5"] == 2000


class TestStreakInfo:
    """Tests for StreakInfo dataclass."""

    def test_streak_info_defaults(self):
        """Test StreakInfo default values."""
        streak = StreakInfo()
        assert streak.current_streak == 0
        assert streak.longest_streak == 0
        assert streak.current_streak_start is None
        assert streak.longest_streak_start is None
        assert streak.longest_streak_end is None


class TestSessionStats:
    """Tests for SessionStats dataclass."""

    def test_session_stats_creation(self):
        """Test creating SessionStats."""
        session = SessionStats(
            session_id="abc123",
            duration=60000,
            message_count=10,
            timestamp="2024-01-15T10:00:00Z",
        )
        assert session.session_id == "abc123"
        assert session.duration == 60000
        assert session.message_count == 10
        assert session.timestamp == "2024-01-15T10:00:00Z"


class TestModelUsage:
    """Tests for ModelUsage dataclass."""

    def test_model_usage_defaults(self):
        """Test ModelUsage default values."""
        usage = ModelUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_input_tokens == 0
        assert usage.cache_creation_input_tokens == 0
        assert usage.web_search_requests == 0
        assert usage.cost_usd == 0.0
        assert usage.context_window == 0
        assert usage.max_output_tokens == 0


class TestCalculateStreaks:
    """Tests for calculate_streaks function."""

    def test_empty_activity(self):
        """Test calculate_streaks with empty activity."""
        result = calculate_streaks([])
        assert result.current_streak == 0
        assert result.longest_streak == 0

    def test_single_day(self):
        """Test calculate_streaks with single day."""
        # Use yesterday since we can't guarantee today is in the set
        from datetime import timedelta

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        activity = [DailyActivity(date=yesterday)]
        result = calculate_streaks(activity)
        # Current streak is 1 if yesterday is today-1
        assert result.longest_streak == 1

    def test_consecutive_days(self):
        """Test calculate_streaks with consecutive days."""
        from datetime import timedelta

        today = datetime.now(timezone.utc)
        dates = [
            (today - timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(3)
        ]
        activity = [DailyActivity(date=d) for d in dates]
        result = calculate_streaks(activity)
        # With dates spanning today, we should have current streak
        assert result.longest_streak == 3

    def test_non_consecutive_days(self):
        """Test calculate_streaks with non-consecutive days."""
        from datetime import timedelta

        today = datetime.now(timezone.utc)
        # Create gap in the middle
        dates = [
            (today - timedelta(days=5)).strftime("%Y-%m-%d"),  # 5 days ago
            (today - timedelta(days=2)).strftime("%Y-%m-%d"),  # 2 days ago
            (today - timedelta(days=1)).strftime("%Y-%m-%d"),  # yesterday
        ]
        activity = [DailyActivity(date=d) for d in dates]
        result = calculate_streaks(activity)
        # Longest streak should be 2 (yesterday and day before)
        assert result.longest_streak == 2


class TestGetEmptyStats:
    """Tests for get_empty_stats function."""

    def test_empty_stats_values(self):
        """Test that empty stats have zero/empty values."""
        stats = get_empty_stats()
        assert stats.total_sessions == 0
        assert stats.total_messages == 0
        assert stats.total_days == 0
        assert stats.active_days == 0
        assert stats.daily_activity == []
        assert stats.daily_model_tokens == []
        assert stats.longest_session is None
        assert stats.model_usage == {}
        assert stats.first_session_date is None
        assert stats.last_session_date is None
        assert stats.peak_activity_day is None
        assert stats.peak_activity_hour is None
        assert stats.total_speculation_time_saved_ms == 0


class TestClaudeCodeStats:
    """Tests for ClaudeCodeStats dataclass."""

    def test_claude_code_stats_defaults(self):
        """Test ClaudeCodeStats default values."""
        stats = ClaudeCodeStats()
        assert isinstance(stats.streaks, StreakInfo)
        assert isinstance(stats.daily_activity, list)
        assert isinstance(stats.daily_model_tokens, list)
        assert isinstance(stats.model_usage, dict)


class TestExtractShotCount:
    """Tests for extract_shot_count_from_messages function."""

    def test_no_messages(self):
        """Test with empty messages."""
        result = extract_shot_count_from_messages([])
        assert result is None

    def test_no_shot_count(self):
        """Test with messages but no shot count."""
        messages = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}
        ]
        result = extract_shot_count_from_messages(messages)
        assert result is None

    def test_shot_count_extraction(self):
        """Test extracting shot count from gh pr create."""
        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {
                                "command": "gh pr create --title 'Fix bug' --body '3-shotted by claude-3-5-sonnet'"
                            },
                        }
                    ]
                },
            }
        ]
        result = extract_shot_count_from_messages(messages)
        assert result == 3


class TestReadSessionStartDate:
    """Tests for read_session_start_date function."""

    def test_nonexistent_file(self):
        """Test reading non-existent file returns None."""
        import asyncio

        result = asyncio.run(read_session_start_date("/nonexistent/path.jsonl"))
        assert result is None
