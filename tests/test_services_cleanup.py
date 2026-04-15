"""Tests for cleanup services."""

import pytest
from datetime import datetime, timedelta

from py_claw.services.cleanup import (
    CleanupResult,
    add_cleanup_results,
    convert_filename_to_date,
    get_cutoff_date,
)


class TestCleanupResult:
    """Tests for CleanupResult dataclass."""

    def test_create_empty_result(self):
        """Test creating empty cleanup result."""
        result = CleanupResult()
        assert result.messages == 0
        assert result.errors == 0

    def test_create_with_values(self):
        """Test creating cleanup result with values."""
        result = CleanupResult(messages=5, errors=2)
        assert result.messages == 5
        assert result.errors == 2


class TestAddCleanupResults:
    """Tests for add_cleanup_results."""

    def test_add_empty_results(self):
        """Test adding empty results."""
        a = CleanupResult()
        b = CleanupResult()
        result = add_cleanup_results(a, b)
        assert result.messages == 0
        assert result.errors == 0

    def test_add_results_with_values(self):
        """Test adding results with values."""
        a = CleanupResult(messages=3, errors=1)
        b = CleanupResult(messages=2, errors=2)
        result = add_cleanup_results(a, b)
        assert result.messages == 5
        assert result.errors == 3


class TestGetCutoffDate:
    """Tests for get_cutoff_date."""

    def test_default_period(self):
        """Test cutoff date with default period."""
        cutoff = get_cutoff_date()
        now = datetime.now()
        expected = now - timedelta(days=30)
        # Allow 1 second tolerance for test execution time
        diff = abs((cutoff - expected).total_seconds())
        assert diff < 1

    def test_custom_period(self):
        """Test cutoff date with custom period."""
        cutoff = get_cutoff_date(cleanup_period_days=7)
        now = datetime.now()
        expected = now - timedelta(days=7)
        diff = abs((cutoff - expected).total_seconds())
        assert diff < 1


class TestConvertFilenameToDate:
    """Tests for convert_filename_to_date."""

    def test_standard_iso_format(self):
        """Test converting standard ISO format filename."""
        filename = "2024-01-15T10-30-00-000Z"
        result = convert_filename_to_date(filename)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 0

    def test_filename_with_milliseconds(self):
        """Test converting filename with milliseconds."""
        filename = "2024-01-15T10-30-45-123Z"
        result = convert_filename_to_date(filename)
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 45

    def test_date_only_filename(self):
        """Test converting date-only filename."""
        filename = "2024-01-15"
        result = convert_filename_to_date(filename)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_with_extension(self):
        """Test converting filename with extension."""
        filename = "2024-01-15T10-30-00-000Z.json"
        result = convert_filename_to_date(filename)
        assert result.year == 2024
