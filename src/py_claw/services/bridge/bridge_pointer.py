"""Crash-recovery pointer for Remote Control sessions.

Written immediately after a bridge session is created, periodically
refreshed during the session, and cleared on clean shutdown. If the
process dies unclean, the pointer persists for crash recovery.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

# TTL for bridge pointer (4 hours)
BRIDGE_POINTER_TTL_MS = 4 * 60 * 60 * 1000


@dataclass
class BridgePointer:
    """Bridge pointer for crash recovery."""

    session_id: str
    environment_id: str
    source: Literal["standalone", "repl"]


@dataclass
class BridgePointerWithAge:
    """Bridge pointer with age information."""

    session_id: str
    environment_id: str
    source: Literal["standalone", "repl"]
    age_ms: int


def get_bridge_pointer_path(dir: str) -> Path:
    """Get the path to the bridge pointer file.

    Args:
        dir: Working directory path.

    Returns:
        Path to bridge-pointer.json file.
    """
    # Use a project-specific location alongside transcript files
    projects_dir = os.environ.get(
        "CLAUDE_PROJECTS_DIR",
        os.path.expanduser("~/.claude/projects"),
    )
    safe_dir = dir.replace(":", "").replace("\\", "/").replace("//", "/").strip("/")
    return Path(projects_dir) / safe_dir / "bridge-pointer.json"


async def write_bridge_pointer(
    dir: str,
    pointer: BridgePointer,
) -> None:
    """Write the bridge pointer.

    Also used to refresh mtime during long sessions.

    Args:
        dir: Working directory.
        pointer: Bridge pointer data.
    """
    import logging

    logger = logging.getLogger("py_claw.bridge")
    path = get_bridge_pointer_path(dir)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pointer.__dict__), encoding="utf-8")
        logger.debug(f"[bridge:pointer] wrote {path}")
    except Exception as e:
        logger.warning(f"[bridge:pointer] write failed: {e}")


async def read_bridge_pointer(
    dir: str,
) -> BridgePointerWithAge | None:
    """Read the bridge pointer and its age.

    Handles errors gracefully - returns None on any failure.
    Stale pointers (>4h old) are deleted.

    Args:
        dir: Working directory.

    Returns:
        BridgePointerWithAge if valid, None otherwise.
    """
    import logging

    logger = logging.getLogger("py_claw.bridge")
    path = get_bridge_pointer_path(dir)

    try:
        stat = path.stat()
        mtime_ms = int(stat.st_mtime * 1000)
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.debug(f"[bridge:pointer] read failed: {e}")
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.debug(f"[bridge:pointer] invalid JSON, clearing: {path}")
        await clear_bridge_pointer(dir)
        return None

    # Validate required fields
    if not all(k in data for k in ("session_id", "environment_id", "source")):
        logger.debug(f"[bridge:pointer] invalid schema, clearing: {path}")
        await clear_bridge_pointer(dir)
        return None

    age_ms = max(0, int(datetime.now().timestamp() * 1000) - mtime_ms)
    if age_ms > BRIDGE_POINTER_TTL_MS:
        logger.debug(f"[bridge:pointer] stale (>4h mtime), clearing: {path}")
        await clear_bridge_pointer(dir)
        return None

    return BridgePointerWithAge(
        session_id=data["session_id"],
        environment_id=data["environment_id"],
        source=data["source"],
        age_ms=age_ms,
    )


async def read_bridge_pointer_across_worktrees(
    dir: str,
) -> tuple[BridgePointerWithAge, str] | None:
    """Worktree-aware read for --continue.

    Checks current dir first, then fans out to git worktree siblings
    to find the freshest pointer.

    Args:
        dir: Working directory.

    Returns:
        Tuple of (pointer, dir it was found in), or None.
    """
    import logging

    logger = logging.getLogger("py_claw.bridge")

    # Fast path: current dir
    pointer = await read_bridge_pointer(dir)
    if pointer:
        return (pointer, dir)

    # Fanout: scan worktree siblings
    worktrees = await _get_worktree_paths(dir)
    if len(worktrees) <= 1:
        return None

    # Dedupe against current dir
    candidates = [wt for wt in worktrees if wt != dir]

    # Parallel read
    results = []
    for wt in candidates:
        p = await read_bridge_pointer(wt)
        if p:
            results.append((p, wt))

    if not results:
        return None

    # Pick freshest (lowest ageMs)
    freshest = min(results, key=lambda x: x[0].age_ms)
    logger.debug(
        f"[bridge:pointer] fanout found pointer in {freshest[1]} (ageMs={freshest[0].age_ms})"
    )
    return freshest


async def _get_worktree_paths(dir: str) -> list[str]:
    """Get list of git worktree paths.

    Args:
        dir: Working directory.

    Returns:
        List of worktree paths, or empty list on error.
    """
    import asyncio
    import subprocess

    try:
        result = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "git", "worktree", "list", "--porcelain",
                cwd=dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            ),
            timeout=5.0,
        )
        output, _ = await result.communicate()
        if result.returncode != 0:
            return []

        lines = output.decode().split("\n")
        paths = []
        for line in lines:
            line = line.strip()
            if line.startswith("worktree "):
                paths.append(line[len("worktree ") :])
        return paths
    except Exception:
        return []


async def clear_bridge_pointer(dir: str) -> None:
    """Delete the bridge pointer.

    Idempotent - ENOENT is expected.

    Args:
        dir: Working directory.
    """
    import logging

    logger = logging.getLogger("py_claw.bridge")
    path = get_bridge_pointer_path(dir)

    try:
        path.unlink()
        logger.debug(f"[bridge:pointer] cleared {path}")
    except FileNotFoundError:
        pass
    except Exception as e:
        if "ENOENT" not in str(e):
            logger.warning(f"[bridge:pointer] clear failed: {e}")
