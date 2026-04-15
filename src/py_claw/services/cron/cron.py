"""Cron utilities - parsing and next-run calculation.

Based on ClaudeCode-main/src/utils/cron.ts

Supports standard 5-field cron: minute hour day-of-month month day-of-week

Field syntax: wildcard, N, step (*/N), range (N-M), lists (N,M,...)
No L, W, ?, or name aliases. All times are interpreted in local timezone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

# Type definitions
MINUTE = 0
HOUR = 1
DAY_OF_MONTH = 2
MONTH = 3
DAY_OF_WEEK = 4


@dataclass(frozen=True)
class CronFields:
    """Parsed cron expression fields."""

    minute: tuple[int, ...]
    hour: tuple[int, ...]
    day_of_month: tuple[int, ...]
    month: tuple[int, ...]
    day_of_week: tuple[int, ...]


# Field ranges
FIELD_RANGES: list[dict[str, int]] = [
    {"min": 0, "max": 59},  # minute
    {"min": 0, "max": 23},  # hour
    {"min": 1, "max": 31},  # dayOfMonth
    {"min": 1, "max": 12},  # month
    {"min": 0, "max": 6},  # dayOfWeek (0=Sunday; 7 accepted as Sunday alias)
]


def _expand_field(field: str, range_info: dict[str, int]) -> list[int] | None:
    """Parse a single cron field into a sorted array of matching values.

    Supports: wildcard, N, */N (step), N-M (range), and comma-lists.
    """
    min_val = range_info["min"]
    max_val = range_info["max"]
    result: set[int] = set()

    for part in field.split(","):
        # Wildcard or */N
        step_match = re.match(r"^\*(?:/(\d+))?$", part)
        if step_match:
            step = int(step_match.group(1)) if step_match.group(1) else 1
            if step < 1:
                return None
            for i in range(min_val, max_val + 1, step):
                result.add(i)
            continue

        # N-M or N-M/N
        range_match = re.match(r"^(\d+)-(\d+)(?:/(\d+))?$", part)
        if range_match:
            lo = int(range_match.group(1))
            hi = int(range_match.group(2))
            step = int(range_match.group(3)) if range_match.group(3) else 1
            # dayOfWeek: accept 7 as Sunday alias in ranges
            is_dow = min_val == 0 and max_val == 6
            effective_max = 7 if is_dow else max_val
            if lo > hi or step < 1 or lo < min_val or hi > effective_max:
                return None
            for i in range(lo, hi + 1, step):
                result.add(0 if is_dow and i == 7 else i)
            continue

        # Plain N
        if re.match(r"^\d+$", part):
            n = int(part)
            # dayOfWeek: accept 7 as Sunday alias
            if min_val == 0 and max_val == 6 and n == 7:
                n = 0
            if n < min_val or n > max_val:
                return None
            result.add(n)
            continue

        return None

    if not result:
        return None
    return sorted(result)


def parse_cron_expression(expr: str) -> CronFields | None:
    """Parse a 5-field cron expression into expanded number arrays.

    Returns None if invalid or unsupported syntax.
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        return None

    expanded: list[list[int]] = []
    for i in range(5):
        result = _expand_field(parts[i], FIELD_RANGES[i])
        if result is None:
            return None
        expanded.append(result)

    return CronFields(
        minute=tuple(expanded[0]),
        hour=tuple(expanded[1]),
        day_of_month=tuple(expanded[2]),
        month=tuple(expanded[3]),
        day_of_week=tuple(expanded[4]),
    )


def compute_next_cron_run(fields: CronFields, from_time: datetime) -> datetime | None:
    """Compute the next Date strictly after `from` that matches the cron fields.

    Uses local timezone. Walks forward minute-by-minute, bounded at 366 days.
    Returns None if no match (impossible for valid cron).

    Standard cron semantics: when both dayOfMonth and dayOfWeek are constrained,
    a date matches if EITHER matches.
    """
    minute_set = set(fields.minute)
    hour_set = set(fields.hour)
    dom_set = set(fields.day_of_month)
    month_set = set(fields.month)
    dow_set = set(fields.day_of_week)

    # Is the field wildcarded (full range)?
    dom_wild = len(fields.day_of_month) == 31
    dow_wild = len(fields.day_of_week) == 7

    # Round up to the next whole minute (strictly after from_time)
    t = from_time.replace(second=0, microsecond=0)
    t += timedelta(minutes=1)

    max_iter = 366 * 24 * 60
    for _ in range(max_iter):
        month = t.month
        if month not in month_set:
            # Jump to start of next month
            if t.month == 12:
                t = t.replace(year=t.year + 1, month=1, day=1, hour=0, minute=0)
            else:
                t = t.replace(month=t.month + 1, day=1, hour=0, minute=0)
            continue

        dom = t.day
        dow = t.weekday()  # 0=Monday in Python, but we treat 0=Sunday
        # Convert Python's Monday=0 to Sunday=0 convention
        dow = 6 if dow == 0 else dow - 1

        # When both dom/dow are constrained, either match is sufficient (OR semantics)
        if dom_wild and dow_wild:
            day_matches = True
        elif dom_wild:
            day_matches = dow in dow_set
        elif dow_wild:
            day_matches = dom in dom_set
        else:
            day_matches = dom in dom_set or dow in dow_set

        if not day_matches:
            # Jump to start of next day
            t += timedelta(days=1)
            t = t.replace(hour=0, minute=0)
            continue

        if t.hour not in hour_set:
            t += timedelta(hours=1)
            t = t.replace(minute=0)
            continue

        if t.minute not in minute_set:
            t += timedelta(minutes=1)
            continue

        return t

    return None


# Day names for cronToHuman
DAY_NAMES = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]


def _format_local_time(minute: int, hour: int) -> str:
    """Format time in user's locale."""
    # January 1 — no DST gap anywhere
    d = datetime(2000, 1, 1, hour, minute)
    return d.strftime("%#I:%M %p")  # Windows-compatible format


def _format_utc_time_as_local(minute: int, hour: int) -> str:
    """Create a date in UTC and format in user's local timezone."""
    # For UTC, we just format with timezone indicator
    d = datetime(2000, 1, 1, hour, minute)
    return d.strftime("%#I:%M %p UTC")


def cron_to_human(cron: str, *, utc: bool = False) -> str:
    """Convert cron expression to human-readable string.

    Intentionally narrow: covers common patterns; falls through to the raw
    cron string for anything else. The `utc` option exists for CCR remote
    triggers which run on servers and always use UTC cron strings.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        return cron

    minute, hour, day_of_month, month, day_of_week = parts

    # Every N minutes: */N * * * *
    every_min_match = re.match(r"^\*/(\d+)$", minute)
    if every_min_match and hour == "*" and day_of_month == "*" and month == "*" and day_of_week == "*":
        n = int(every_min_match.group(1))
        return "Every minute" if n == 1 else f"Every {n} minutes"

    # Every hour: 0 * * * *
    if re.match(r"^\d+$", minute) and hour == "*" and day_of_month == "*" and month == "*" and day_of_week == "*":
        m = int(minute)
        if m == 0:
            return "Every hour"
        return f"Every hour at :{m:02d}"

    # Every N hours: 0 */N * * *
    every_hour_match = re.match(r"^\*/(\d+)$", hour)
    if every_hour_match and re.match(r"^\d+$", minute) and day_of_month == "*" and month == "*" and day_of_week == "*":
        n = int(every_hour_match.group(1))
        m = int(minute)
        suffix = "" if m == 0 else f" at :{m:02d}"
        return f"Every hour{suffix}" if n == 1 else f"Every {n} hours{suffix}"

    # Remaining cases need numeric hour+minute
    if not re.match(r"^\d+$", minute) or not re.match(r"^\d+$", hour):
        return cron

    m = int(minute)
    h = int(hour)
    fmt_time = _format_utc_time_as_local if utc else _format_local_time

    # Daily at specific time: M H * * *
    if day_of_month == "*" and month == "*" and day_of_week == "*":
        return f"Every day at {fmt_time(m, h)}"

    # Specific day of week: M H * * D
    if day_of_month == "*" and month == "*" and re.match(r"^\d$", day_of_week):
        day_index = int(day_of_week) % 7  # normalize 7 (Sunday alias) -> 0
        day_name = DAY_NAMES[day_index]
        if day_name:
            return f"Every {day_name} at {fmt_time(m, h)}"

    # Weekdays: M H * * 1-5
    if day_of_month == "*" and month == "*" and day_of_week == "1-5":
        return f"Weekdays at {fmt_time(m, h)}"

    return cron
