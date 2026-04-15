"""Tests for cron services."""

import pytest
from datetime import datetime, timedelta

from py_claw.services.cron import (
    CronFields,
    compute_next_cron_run,
    cron_to_human,
    parse_cron_expression,
)


class TestParseCronExpression:
    """Tests for parse_cron_expression."""

    def test_parse_wildcard(self):
        """Test parsing wildcard cron expression."""
        result = parse_cron_expression("* * * * *")
        assert result is not None
        assert len(result.minute) == 60  # 0-59
        assert len(result.hour) == 24  # 0-23

    def test_parse_specific_value(self):
        """Test parsing specific value."""
        result = parse_cron_expression("30 9 * * *")
        assert result is not None
        assert 30 in result.minute
        assert 9 in result.hour

    def test_parse_step(self):
        """Test parsing step expression (*/5)."""
        result = parse_cron_expression("*/5 * * * *")
        assert result is not None
        # Should include 0, 5, 10, 15, ... 55
        assert 0 in result.minute
        assert 5 in result.minute
        assert 10 in result.minute
        assert 55 in result.minute

    def test_parse_range(self):
        """Test parsing range expression (1-5)."""
        result = parse_cron_expression("* 9-17 * * *")
        assert result is not None
        assert 9 in result.hour
        assert 12 in result.hour
        assert 17 in result.hour

    def test_parse_list(self):
        """Test parsing list expression (1,15,30)."""
        result = parse_cron_expression("0 0 1,15 * *")
        assert result is not None
        assert 1 in result.day_of_month
        assert 15 in result.day_of_month
        assert 31 not in result.day_of_month

    def test_parse_invalid_expression(self):
        """Test parsing invalid expression returns None."""
        result = parse_cron_expression("invalid")
        assert result is None

    def test_parse_wrong_field_count(self):
        """Test parsing expression with wrong field count."""
        result = parse_cron_expression("* * *")
        assert result is None

    def test_parse_sunday_alias(self):
        """Test parsing day of week with 7 as Sunday alias."""
        result = parse_cron_expression("0 0 * * 7")
        assert result is not None
        # 7 should be converted to 0 (Sunday)
        assert 0 in result.day_of_week


class TestComputeNextCronRun:
    """Tests for compute_next_cron_run."""

    def test_next_minute(self):
        """Test computing next minute."""
        fields = CronFields(
            minute=(30,),
            hour=tuple(range(24)),
            day_of_month=tuple(range(1, 32)),
            month=tuple(range(1, 13)),
            day_of_week=tuple(range(7)),
        )
        now = datetime(2024, 1, 15, 10, 29, 45)
        next_run = compute_next_cron_run(fields, now)
        assert next_run is not None
        assert next_run.minute == 30
        assert next_run.hour == 10

    def test_next_hour(self):
        """Test computing next hour."""
        fields = CronFields(
            minute=(0,),
            hour=(14,),
            day_of_month=tuple(range(1, 32)),
            month=tuple(range(1, 13)),
            day_of_week=tuple(range(7)),
        )
        now = datetime(2024, 1, 15, 10, 0, 0)
        next_run = compute_next_cron_run(fields, now)
        assert next_run is not None
        assert next_run.hour == 14

    def test_next_day(self):
        """Test computing next day."""
        fields = CronFields(
            minute=(0,),
            hour=(9,),
            day_of_month=(15,),
            month=tuple(range(1, 13)),
            day_of_week=tuple(range(7)),
        )
        now = datetime(2024, 1, 14, 10, 0, 0)
        next_run = compute_next_cron_run(fields, now)
        assert next_run is not None
        assert next_run.day == 15

    def test_dow_constraint(self):
        """Test day of week constraint."""
        fields = CronFields(
            minute=(0,),
            hour=(9,),
            day_of_month=tuple(range(1, 32)),
            month=tuple(range(1, 13)),
            day_of_week=(1,),  # Monday
        )
        # A Monday
        now = datetime(2024, 1, 15, 10, 0, 0)  # This is a Monday
        next_run = compute_next_cron_run(fields, now)
        assert next_run is not None
        # The next Monday from current time


class TestCronToHuman:
    """Tests for cron_to_human."""

    def test_every_minute(self):
        """Test every minute expression."""
        result = cron_to_human("*/1 * * * *")
        assert result == "Every minute"

    def test_every_n_minutes(self):
        """Test every N minutes expression."""
        result = cron_to_human("*/5 * * * *")
        assert result == "Every 5 minutes"

    def test_every_hour(self):
        """Test every hour expression."""
        result = cron_to_human("0 * * * *")
        assert result == "Every hour"

    def test_every_hour_at_minute(self):
        """Test every hour at specific minute."""
        result = cron_to_human("30 * * * *")
        assert "at :" in result

    def test_every_day(self):
        """Test daily expression."""
        result = cron_to_human("0 9 * * *")
        assert "Every day" in result

    def test_weekdays(self):
        """Test weekdays expression."""
        result = cron_to_human("0 9 * * 1-5")
        assert "Weekdays" in result

    def test_invalid_expression(self):
        """Test invalid expression returns raw cron."""
        result = cron_to_human("invalid cron")
        assert result == "invalid cron"

    def test_specific_day_of_week(self):
        """Test specific day of week."""
        result = cron_to_human("0 9 * * 0")
        assert "Sunday" in result

    def test_utc_option(self):
        """Test UTC option for remote triggers."""
        result = cron_to_human("0 9 * * *", utc=True)
        assert isinstance(result, str)
        assert len(result) > 0
