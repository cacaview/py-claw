"""
Cron expression parsing and next-run calculation.

Supports the standard 5-field cron subset:
  minute hour day-of-month month day-of-week

Field syntax: wildcard, N, step (star-slash-N), range (N-M), list (N,M,...).
All times are interpreted in the process's local timezone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CronFields:
    """Parsed cron fields as sorted integer arrays."""

    minute: tuple[int, ...]
    hour: tuple[int, ...]
    day_of_month: tuple[int, ...]
    month: tuple[int, ...]
    day_of_week: tuple[int, ...]


# Field ranges: (min, max)
FIELD_RANGES: list[tuple[int, int]] = [
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # dayOfMonth
    (1, 12),  # month
    (0, 6),  # dayOfWeek (0=Sunday; 7 accepted as Sunday alias)
]


def _expand_field(field: str, field_index: int) -> list[int] | None:
    """
    Parse a single cron field into a sorted list of matching values.

    Supports: wildcard, N, star-slash-N (step), N-M (range), and comma-lists.
    Returns None if invalid.
    """
    min_val, max_val = FIELD_RANGES[field_index]
    out: set[int] = set()

    for part in field.split(","):
        # wildcard or star-slash-N
        step_match = re.match(r"^\*(?:/(\d+))?$", part)
        if step_match:
            step = int(step_match.group(1)) if step_match.group(1) else 1
            if step < 1:
                return None
            for i in range(min_val, max_val + 1, step):
                out.add(i)
            continue

        # N-M or N-M/S
        range_match = re.match(r"^(\d+)-(\d+)(?:/(\d+))?$", part)
        if range_match:
            lo = int(range_match.group(1))
            hi = int(range_match.group(2))
            step = int(range_match.group(3)) if range_match.group(3) else 1
            # dayOfWeek: accept 7 as Sunday alias in ranges
            is_dow = field_index == 4
            eff_max = 7 if is_dow else max_val
            if lo > hi or step < 1 or lo < min_val or hi > eff_max:
                return None
            for i in range(lo, hi + 1, step):
                out.add(0 if is_dow and i == 7 else i)
            continue

        # plain N
        if part.isdigit():
            n = int(part)
            # dayOfWeek: accept 7 as Sunday alias -> 0
            if field_index == 4 and n == 7:
                n = 0
            if n < min_val or n > max_val:
                return None
            out.add(n)
            continue

        return None

    if not out:
        return None
    return sorted(out)


def parse_cron_expression(expr: str) -> CronFields | None:
    """
    Parse a 5-field cron expression into expanded number arrays.

    Returns None if invalid or unsupported syntax.
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        return None

    expanded: list[list[int]] = []
    for i, part in enumerate(parts):
        result = _expand_field(part, i)
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
    """
    Compute the next datetime strictly after ``from_time`` that matches the cron fields.

    Uses the process's local timezone. Walks forward minute-by-minute, bounded at 366 days.
    Returns None if no match found.

    Standard cron semantics: when both dayOfMonth and dayOfWeek are constrained,
    a date matches if EITHER matches (OR semantics).
    """
    minute_set = set(fields.minute)
    hour_set = set(fields.hour)
    dom_set = set(fields.day_of_month)
    month_set = set(fields.month)
    dow_set = set(fields.day_of_week)

    # Is the field wildcarded (full range)?
    dom_wild = len(fields.day_of_month) == 31
    dow_wild = len(fields.day_of_week) == 7

    # Round up to the next whole minute (strictly after `from`)
    t = from_time.replace(second=0, microsecond=0)
    t += timedelta(minutes=1)

    max_iter = 366 * 24 * 60
    for _ in range(max_iter):
        month = t.month
        if month not in month_set:
            # Jump to start of next month
            if t.month == 12:
                t = t.replace(year=t.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                t = t.replace(month=t.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
            continue

        dom = t.day
        dow = t.weekday()  # 0=Monday in Python; convert cron-style (0=Sunday)
        dow_cron = 6 if dow == 6 else dow + 1  # convert to cron: Mon=1, Sun=0

        # When both dom/dow are constrained, either match is sufficient
        if dom_wild and dow_wild:
            day_matches = True
        elif dom_wild:
            day_matches = dow_cron in dow_set
        elif dow_wild:
            day_matches = dom in dom_set
        else:
            day_matches = dom in dom_set or dow_cron in dow_set

        if not day_matches:
            # Jump to start of next day
            t += timedelta(days=1)
            t = t.replace(hour=0, minute=0, second=0, microsecond=0)
            continue

        if t.hour not in hour_set:
            t += timedelta(hours=1)
            t = t.replace(minute=0, second=0, microsecond=0)
            continue

        if t.minute not in minute_set:
            t += timedelta(minutes=1)
            continue

        return t

    return None


# --- cronToHuman -----------------------------------------------------------

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
    """Format time using January 1 (no DST issues) in local timezone."""
    d = datetime(2000, 1, 1, hour, minute)
    return d.strftime("%#I:%M %p")  # Windows-friendly


def cron_to_human(cron: str, *, utc: bool = False) -> str:
    """
    Convert a cron expression to a human-readable string.

    Intentionally narrow: covers common patterns; falls through to raw cron
    string for anything else.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        return cron

    minute, hour, day_of_month, month, day_of_week = parts

    # Every N minutes: step/N * * * *
    every_min_match = re.match(r"^\*/(\d+)$", minute) if isinstance(minute, str) else None
    if every_min_match:
        n = int(minute[2:]) if minute.startswith("*/") else 0
        if hour == "*" and day_of_month == "*" and month == "*" and day_of_week == "*":
            n = int(minute[2:])
            return "Every minute" if n == 1 else f"Every {n} minutes"

    # Every hour: 0 * * * *
    if (
        minute.isdigit()
        and hour == "*"
        and day_of_month == "*"
        and month == "*"
        and day_of_week == "*"
    ):
        m = int(minute)
        if m == 0:
            return "Every hour"
        return f"Every hour at :{m:02d}"

    # Every N hours: 0 step/N * * *
    if minute.isdigit() and not hour.isdigit():
        if (
            day_of_month == "*"
            and month == "*"
            and day_of_week == "*"
        ):
            m = int(minute)
            return f"Every hour at :{m:02d}"

    if not minute.isdigit() or not hour.isdigit():
        return cron

    m = int(minute)
    h = int(hour)

    # Daily at specific time: M H * * *
    if day_of_month == "*" and month == "*" and day_of_week == "*":
        return f"Every day at {_format_local_time(m, h)}"

    # Specific day of week: M H * * D
    if day_of_month == "*" and month == "*" and day_of_week.isdigit():
        day_index = int(day_of_week) % 7
        day_name = DAY_NAMES[day_index] if 0 <= day_index < 7 else None
        if day_name:
            return f"Every {day_name} at {_format_local_time(m, h)}"

    # Weekdays: M H * * 1-5
    if day_of_month == "*" and month == "*" and day_of_week == "1-5":
        return f"Weekdays at {_format_local_time(m, h)}"

    return cron
