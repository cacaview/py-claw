"""
Perfetto tracing service for agent hierarchy visualization.

Registers forked agents in a trace hierarchy for debugging and
performance analysis with Perfetto.

Trace data is stored in:
  ~/.claude/traces/<session_id>/<agent_id>.json
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────────


# Environment variable to enable Perfetto tracing
PERFETTO_ENABLED_ENV = "PY_CLAW_PERFETTO_TRACING"
PERFETTO_TRACE_DIR_ENV = "PY_CLAW_PERFETTO_TRACE_DIR"


def _is_tracing_enabled() -> bool:
    """Check if Perfetto tracing is enabled via environment."""
    return os.environ.get(PERFETTO_ENABLED_ENV, "").lower() in ("1", "true", "yes")


def _get_trace_dir() -> Path:
    """Get the trace output directory."""
    custom_dir = os.environ.get(PERFETTO_TRACE_DIR_ENV)
    if custom_dir:
        return Path(custom_dir)
    return Path.home() / ".claude" / "traces"


# ─── Trace Registry ────────────────────────────────────────────────────────────


@dataclass
class TraceSpan:
    """A trace span for a forked agent."""

    agent_id: str
    agent_type: str
    parent_id: str
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["start_time"] = self.start_time.isoformat()
        if self.end_time:
            result["end_time"] = self.end_time.isoformat()
        return result


class _TraceRegistry:
    """Thread-safe registry of active agent traces."""

    def __init__(self) -> None:
        self._spans: dict[str, TraceSpan] = {}
        self._lock = threading.Lock()

    def register(self, span: TraceSpan) -> None:
        with self._lock:
            self._spans[span.agent_id] = span

    def unregister(self, agent_id: str) -> None:
        with self._lock:
            span = self._spans.pop(agent_id, None)
            if span and span.end_time is None:
                span.end_time = datetime.now(timezone.utc)

    def get(self, agent_id: str) -> TraceSpan | None:
        with self._lock:
            return self._spans.get(agent_id)

    def get_all(self) -> list[TraceSpan]:
        with self._lock:
            return list(self._spans.values())

    def finalize(self, agent_id: str) -> None:
        """Finalize a span with end_time."""
        with self._lock:
            span = self._spans.get(agent_id)
            if span:
                span.end_time = datetime.now(timezone.utc)


# Global trace registry
_trace_registry = _TraceRegistry()


# ─── Perfetto Tracing Service ──────────────────────────────────────────────────


class PerfettoTracingService:
    """Service for Perfetto trace management of forked agents.

    Provides:
    - is_enabled(): Check if tracing is active
    - register_agent(): Register an agent in the trace hierarchy
    - unregister_agent(): Remove an agent from the trace
    """

    @staticmethod
    def is_enabled() -> bool:
        """Check if Perfetto tracing is enabled."""
        return _is_tracing_enabled()

    @staticmethod
    def register_agent(
        agent_id: str,
        agent_type: str,
        parent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register an agent in the trace hierarchy.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (e.g., "Explore", "Plan")
            parent_id: Parent session or agent ID
            metadata: Optional additional metadata
        """
        if not _is_tracing_enabled():
            return

        span = TraceSpan(
            agent_id=agent_id,
            agent_type=agent_type,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        _trace_registry.register(span)

        # Write initial trace file
        _write_trace_file(span)

        logger.debug(
            "Registered agent %s (type=%s) in Perfetto trace",
            agent_id,
            agent_type,
        )

    @staticmethod
    def unregister_agent(agent_id: str) -> None:
        """Remove an agent from the trace and finalize its span.

        Args:
            agent_id: Agent identifier to unregister
        """
        if not _is_tracing_enabled():
            return

        _trace_registry.finalize(agent_id)
        span = _trace_registry.get(agent_id)
        if span:
            _write_trace_file(span)

        logger.debug("Unregistered agent %s from Perfetto trace", agent_id)

    @staticmethod
    def update_metadata(agent_id: str, metadata: dict[str, Any]) -> None:
        """Update metadata for a registered agent.

        Args:
            agent_id: Agent identifier
            metadata: Metadata to merge
        """
        if not _is_tracing_enabled():
            return

        span = _trace_registry.get(agent_id)
        if span:
            span.metadata.update(metadata)
            _write_trace_file(span)

    @staticmethod
    def get_active_traces() -> list[TraceSpan]:
        """Get all active trace spans."""
        return _trace_registry.get_all()


# ─── Trace File Output ─────────────────────────────────────────────────────────


def _write_trace_file(span: TraceSpan) -> None:
    """Write a trace span to the trace file.

    Args:
        span: Trace span to write
    """
    try:
        trace_dir = _get_trace_dir()
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_dir / f"{span.agent_id}.json"

        # Build Perfetto trace JSON (simplified)
        perfetto_trace = {
            "traceEvents": [
                {
                    "name": f"agent:{span.agent_type}",
                    "cat": "agent",
                    "ts": _datetime_to_us(span.start_time),
                    "dur": (
                        _datetime_to_us(span.end_time) - _datetime_to_us(span.start_time)
                        if span.end_time
                        else 0
                    ),
                    "pid": span.parent_id,
                    "tid": span.agent_id,
                    "args": span.metadata,
                }
            ],
            "metadata": {
                "agent_id": span.agent_id,
                "agent_type": span.agent_type,
                "parent_id": span.parent_id,
            },
        }

        trace_file.write_text(json.dumps(perfetto_trace, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("Failed to write trace file for %s: %s", span.agent_id, exc)


def _datetime_to_us(dt: datetime) -> int:
    """Convert datetime to microseconds since epoch."""
    return int(dt.timestamp() * 1_000_000)
