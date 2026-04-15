"""Usage tracking for command suggestions - persists across sessions.

Tracks command usage frequency and recency to boost frequently-used commands
in the suggestion list.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

# Usage data directory and file
_USAGE_DIR = Path.home() / ".claude" / "data"
_USAGE_FILE = _USAGE_DIR / "command_usage.json"


@dataclass
class CommandUsageEntry:
    """A command usage record."""
    count: int
    last_used: float  # Unix timestamp


class CommandUsageTracker:
    """Tracks command usage frequency across sessions."""

    def __init__(self) -> None:
        self._usage: dict[str, CommandUsageEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load usage data from disk."""
        if not _USAGE_FILE.exists():
            return
        try:
            with open(_USAGE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for cmd_name, entry in data.items():
                self._usage[cmd_name] = CommandUsageEntry(
                    count=entry["count"],
                    last_used=entry["last_used"],
                )
        except (json.JSONDecodeError, IOError, KeyError):
            pass

    def _save(self) -> None:
        """Save usage data to disk."""
        _USAGE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            cmd: {"count": e.count, "last_used": e.last_used}
            for cmd, e in self._usage.items()
        }
        try:
            with open(_USAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass

    def record_usage(self, command_name: str) -> None:
        """Record that a command was used."""
        now = time.time()
        if command_name in self._usage:
            entry = self._usage[command_name]
            entry.count += 1
            entry.last_used = now
        else:
            self._usage[command_name] = CommandUsageEntry(count=1, last_used=now)
        self._save()

    def get_frequency_boost(self, command_name: str) -> float:
        """Get a frequency boost score (higher = more frequent).

        Returns a value between 0.0 and 1.0 based on relative usage frequency.
        """
        if not self._usage:
            return 0.0
        entry = self._usage.get(command_name)
        if not entry:
            return 0.0
        max_count = max(e.count for e in self._usage.values())
        if max_count == 0:
            return 0.0
        return entry.count / max_count

    def get_recency_boost(self, command_name: str) -> float:
        """Get a recency boost score (higher = more recent).

        Returns a value between 0.0 and 1.0 based on how recently the command was used.
        Uses a decay curve so recent commands score higher.
        """
        if not self._usage:
            return 0.0
        entry = self._usage.get(command_name)
        if not entry:
            return 0.0
        now = time.time()
        age_seconds = now - entry.last_used
        # Decay: 1.0 at 0 seconds, 0.5 at 6 hours, 0.0 at 12+ hours
        decay_hours = 6.0
        return max(0.0, 1.0 - (age_seconds / (decay_hours * 3600)))


# Global instance
_tracker: CommandUsageTracker | None = None


def get_usage_tracker() -> CommandUsageTracker:
    """Get the global CommandUsageTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = CommandUsageTracker()
    return _tracker
