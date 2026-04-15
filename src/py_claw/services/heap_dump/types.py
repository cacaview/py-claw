"""
Types for heap dump service.
"""
from __future__ import annotations

import tracemalloc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HeapDumpResult:
    """Result of a heap dump operation."""
    success: bool
    heap_path: str | None = None
    diag_path: str | None = None
    error: str | None = None


@dataclass
class MemoryDiagnostics:
    """Memory diagnostics captured alongside heap dump."""
    timestamp: str
    session_id: str
    trigger: str  # 'manual' | 'auto-1.5GB'
    dump_number: int  # 0 for manual, 1+ for auto
    uptime_seconds: float
    memory_usage: dict[str, int] = field(default_factory=dict)
    memory_growth_rate: dict[str, float] = field(default_factory=dict)
    v8_heap_stats: dict[str, int] = field(default_factory=dict)
    v8_heap_spaces: list[dict[str, Any]] = field(default_factory=list)
    resource_usage: dict[str, float] = field(default_factory=dict)
    active_handles: int = 0
    active_requests: int = 0
    open_file_descriptors: int | None = None
    analysis: dict[str, Any] = field(default_factory=dict)
    smaps_rollup: str | None = None
    platform: str = ""
    python_version: str = ""
    py_claw_version: str = ""


@dataclass
class HeapDumpConfig:
    """Configuration for heap dump service."""
    enabled: bool = True
    dump_dir: str | None = None  # None = use desktop path
    auto_dump_threshold_gb: float = 1.5  # Auto dump at 1.5GB RSS
