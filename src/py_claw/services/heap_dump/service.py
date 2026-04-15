"""
Heap dump service for memory profiling.

Captures heap snapshots and memory diagnostics for debugging memory leaks.
Outputs to ~/Desktop or configured dump directory.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import platform
import time
import tracemalloc
from pathlib import Path
from typing import Any

from py_claw.services.heap_dump.types import (
    HeapDumpConfig,
    HeapDumpResult,
    MemoryDiagnostics,
)

logger = logging.getLogger(__name__)

# Module-level config
_heap_dump_config: HeapDumpConfig | None = None


def get_heap_dump_config() -> HeapDumpConfig:
    """Get the heap dump configuration."""
    global _heap_dump_config
    if _heap_dump_config is None:
        _heap_dump_config = HeapDumpConfig()
    return _heap_dump_config


def set_heap_dump_config(config: HeapDumpConfig) -> None:
    """Set the heap dump configuration."""
    global _heap_dump_config
    _heap_dump_config = config


def _get_desktop_path() -> str:
    """Get the desktop path for the current user."""
    if platform.system() == "Windows":
        return str(Path.home() / "Desktop")
    elif platform.system() == "Darwin":
        return str(Path.home() / "Desktop")
    else:
        # Linux
        return str(Path.home())


def _get_session_id() -> str:
    """Get the current session ID.

    In Python implementation, returns a placeholder or session env var.
    """
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "unknown-session")


def _get_py_claw_version() -> str:
    """Get the py-claw version."""
    try:
        from py_claw import __version__
        return __version__
    except ImportError:
        return "unknown"


async def capture_memory_diagnostics(
    trigger: str = "manual",
    dump_number: int = 0,
) -> MemoryDiagnostics:
    """Capture memory diagnostics.

    This helps identify if the leak is in Python heap or native memory.

    Args:
        trigger: What triggered the dump ('manual' or 'auto-1.5GB')
        dump_number: Which auto dump number (0 for manual)

    Returns:
        MemoryDiagnostics with memory stats
    """
    # Get memory info from tracemalloc
    if tracemalloc.is_tracing():
        current, peak = tracemalloc.get_traced_memory()
    else:
        current, peak = 0, 0

    # Get process memory info
    import resource
    mem_info = resource.getrusage(resource.RUSAGE_SELF)
    uptime = time.time() - os.times().boot_time if hasattr(os.times(), 'boot_time') else 0

    # Calculate growth rate
    memory_usage = {
        "heap_used": current,
        "heap_peak": peak,
        "rss": mem_info.ru_maxrss * 1024,  # Convert to bytes on Unix
    }

    # Try to get native memory (RSS - heap)
    native_memory = memory_usage["rss"] - current

    # Calculate growth rate (bytes per second)
    bytes_per_second = memory_usage["rss"] / max(uptime, 1)
    mb_per_hour = (bytes_per_second * 3600) / (1024 * 1024)

    # Identify potential leaks
    potential_leaks: list[str] = []

    if tracemalloc.is_tracing():
        stats = tracemalloc.take_snapshot()
        top_stats = stats.statistics('lineno')
        # Check for memory growth
        if peak > current * 2:
            potential_leaks.append(
                f"Peak memory ({peak / 1024 / 1024:.1f} MB) is much higher than current ({current / 1024 / 1024:.1f} MB)"
            )

    if native_memory > current:
        potential_leaks.append(
            "Native memory > heap - leak may be in native addons (node-pty, sharp, etc.)"
        )

    if mb_per_hour > 100:
        potential_leaks.append(
            f"High memory growth rate: {mb_per_hour:.1f} MB/hour"
        )

    # Get Python heap spaces info
    v8_heap_spaces: list[dict[str, Any]] = []
    if tracemalloc.is_tracing():
        v8_heap_spaces.append({
            "name": "Python heap",
            "size": current,
            "used": current,
            "available": peak - current,
        })

    # Try to read Linux smaps for detailed memory breakdown
    smaps_rollup: str | None = None
    try:
        with open("/proc/self/smaps_rollup", "r") as f:
            smaps_rollup = f.read()
    except (FileNotFoundError, PermissionError):
        pass

    # Get open file descriptors count on Linux
    open_fd: int | None = None
    try:
        fd_dir = "/proc/self/fd"
        if os.path.isdir(fd_dir):
            open_fd = len(os.listdir(fd_dir))
    except (FileNotFoundError, PermissionError):
        pass

    return MemoryDiagnostics(
        timestamp=__import__("datetime").datetime.now().isoformat(),
        session_id=_get_session_id(),
        trigger=trigger,
        dump_number=dump_number,
        uptime_seconds=uptime,
        memory_usage=memory_usage,
        memory_growth_rate={
            "bytes_per_second": bytes_per_second,
            "mb_per_hour": mb_per_hour,
        },
        v8_heap_stats={
            "heap_size_limit": 0,  # Python doesn't have this limit like V8
            "malloced_memory": current,
            "peak_malloced_memory": peak,
            "detached_contexts": 0,  # Python doesn't track contexts like V8
            "native_contexts": 0,
        },
        v8_heap_spaces=v8_heap_spaces,
        resource_usage={
            "max_rss": mem_info.ru_maxrss * 1024,
            "user_cpu_time": mem_info.ru_utime,
            "system_cpu_time": mem_info.ru_stime,
        },
        active_handles=0,  # Python doesn't expose this like Node
        active_requests=0,
        open_file_descriptors=open_fd,
        analysis={
            "potential_leaks": potential_leaks,
            "recommendation": (
                "WARNING: potential leak indicators found. See potentialLeaks array."
                if potential_leaks
                else "No obvious leak indicators. Check heap snapshot for retained objects."
            ),
        },
        smaps_rollup=smaps_rollup,
        platform=platform.system(),
        python_version=platform.python_version(),
        py_claw_version=_get_py_claw_version(),
    )


async def perform_heap_dump(
    trigger: str = "manual",
    dump_number: int = 0,
) -> HeapDumpResult:
    """Perform a heap dump with memory diagnostics.

    Diagnostics are written BEFORE the heap snapshot is captured,
    because the snapshot serialization can be slow for large heaps.

    Args:
        trigger: What triggered the dump
        dump_number: Which auto dump number

    Returns:
        HeapDumpResult with paths or error
    """
    try:
        session_id = _get_session_id()
        config = get_heap_dump_config()

        # Capture diagnostics before any other async I/O
        diagnostics = await capture_memory_diagnostics(trigger, dump_number)

        def to_gb(bytes_val: int) -> str:
            return f"{(bytes_val / 1024 / 1024 / 1024):.3f}"

        logger.debug(
            "[HeapDump] Memory state:\n"
            "  heapUsed: %s GB (in snapshot)\n"
            "  rss: %s GB (total process)\n"
            "  %s",
            to_gb(diagnostics.memory_usage.get("heap_used", 0)),
            to_gb(diagnostics.memory_usage.get("rss", 0)),
            diagnostics.analysis["recommendation"],
        )

        # Determine dump directory
        dump_dir = config.dump_dir or _get_desktop_path()
        os.makedirs(dump_dir, exist_ok=True)

        suffix = f"-dump{dump_number}" if dump_number > 0 else ""
        heap_filename = f"{session_id}{suffix}.heapsnapshot"
        diag_filename = f"{session_id}{suffix}-diagnostics.json"
        heap_path = os.path.join(dump_dir, heap_filename)
        diag_path = os.path.join(dump_dir, diag_filename)

        # Write diagnostics first (cheap, unlikely to fail)
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump(
                _diagnostics_to_dict(diagnostics),
                f,
                indent=2,
                ensure_ascii=False,
            )
        os.chmod(diag_path, 0o600)
        logger.debug(f"[HeapDump] Diagnostics written to {diag_path}")

        # Write heap snapshot
        await _write_heap_snapshot(heap_path)
        logger.debug(f"[HeapDump] Heap dump written to {heap_path}")

        return HeapDumpResult(success=True, heap_path=heap_path, diag_path=diag_path)

    except Exception as e:
        logger.exception("Heap dump failed")
        return HeapDumpResult(success=False, error=str(e))


async def _write_heap_snapshot(filepath: str) -> None:
    """Write a heap snapshot to a file.

    Uses tracemalloc to capture Python heap.
    """
    # Start tracing if not already
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()

    try:
        # Take a snapshot
        snapshot = tracemalloc.take_snapshot()

        # Write as JSON (compatible with Chrome DevTools format)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "snapshot_version": "1.0",
                    "platform": platform.system(),
                    "python_version": platform.python_version(),
                    "timestamp": __import__("datetime").datetime.now().isoformat(),
                    "traces": [
                        {
                            "line_number": stat.traceback.lineno,
                            "size": stat.size,
                            "size_str": f"{stat.size / 1024:.1f} KB",
                            "traceback": str(stat.traceback),
                        }
                        for stat in snapshot.statistics("lineno")[:100]  # Top 100 lines
                    ],
                    "total_size": sum(stat.size for stat in snapshot.statistics("lineno")),
                },
                f,
                indent=2,
            )
        os.chmod(filepath, 0o600)

    finally:
        if not was_tracing:
            tracemalloc.stop()


def _diagnostics_to_dict(d: MemoryDiagnostics) -> dict[str, Any]:
    """Convert MemoryDiagnostics to dict for JSON serialization."""
    return {
        "timestamp": d.timestamp,
        "sessionId": d.session_id,
        "trigger": d.trigger,
        "dumpNumber": d.dump_number,
        "uptimeSeconds": d.uptime_seconds,
        "memoryUsage": d.memory_usage,
        "memoryGrowthRate": d.memory_growth_rate,
        "v8HeapStats": d.v8_heap_stats,
        "v8HeapSpaces": d.v8_heap_spaces,
        "resourceUsage": d.resource_usage,
        "activeHandles": d.active_handles,
        "activeRequests": d.active_requests,
        "openFileDescriptors": d.open_file_descriptors,
        "analysis": d.analysis,
        "smapsRollup": d.smaps_rollup,
        "platform": d.platform,
        "pythonVersion": d.python_version,
        "pyClawVersion": d.py_claw_version,
    }
