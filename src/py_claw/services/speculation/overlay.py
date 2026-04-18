"""Overlay manager for speculation copy-on-write isolation.

Mirrors ClaudeCode-main/src/services/PromptSuggestion/speculation.ts overlay logic.

When a forked agent speculates, file writes go to an isolated overlay
directory. On accept, files are merged back into the main working directory.
On abort, the overlay is discarded.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Set

# ---------------------------------------------------------------------------
# Overlay directory management
# ---------------------------------------------------------------------------


def get_overlay_base() -> Path:
    """Return the base overlay directory for the current process.

    Returns:
        <temp>/py_claw_speculation/<pid>/
    """
    return Path(tempfile.gettempdir()) / "py_claw_speculation" / str(os.getpid())


def create_overlay(overlay_id: str) -> Path:
    """Create an overlay directory for a speculation session.

    Args:
        overlay_id: Unique speculation identifier

    Returns:
        Path to the created overlay directory
    """
    overlay_path = get_overlay_base() / overlay_id
    overlay_path.mkdir(parents=True, exist_ok=True)
    return overlay_path


def remove_overlay(overlay_path: Path) -> None:
    """Recursively remove an overlay directory.

    Args:
        overlay_path: Path to the overlay directory to remove
    """
    shutil.rmtree(overlay_path, ignore_errors=True)


# ---------------------------------------------------------------------------
# OverlayManager
# ---------------------------------------------------------------------------


class OverlayManager:
    """Manages copy-on-write overlay for speculation.

    Copy-on-write semantics:
    - Writes: copy original from main cwd to overlay first, then write to overlay
    - Reads: if file was previously written to overlay, read from overlay;
             otherwise read from main cwd
    - Accept: copy all written overlay files back to main cwd
    - Abort: discard overlay

    Paths are stored internally as posix (forward-slash) strings for
    cross-platform safety when serializing across process boundaries.
    """

    def __init__(self, overlay_path: Path, main_cwd: str) -> None:
        self.overlay_path = overlay_path
        self.main_cwd = Path(main_cwd).resolve()
        self._written_paths: Set[str] = set()

    def resolve_write_path(self, rel_path: str) -> Path:
        """Resolve a write operation to the overlay.

        Copies the original file to overlay if it exists and hasn't been
        copied yet. Returns the overlay path where the write should occur.

        Args:
            rel_path: Path relative to main cwd (forward or backward slash)

        Returns:
            Absolute path in overlay where the write should go
        """
        # Normalize to forward-slash for internal tracking
        rel = Path(rel_path).as_posix()

        if rel not in self._written_paths:
            src = self.main_cwd / rel_path
            dst = self.overlay_path / rel
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
            self._written_paths.add(rel)

        return self.overlay_path / rel

    def resolve_read_path(self, rel_path: str) -> Path:
        """Resolve a read operation to either overlay or main cwd.

        Args:
            rel_path: Path relative to main cwd

        Returns:
            Absolute path to read from (overlay if previously written)
        """
        rel = Path(rel_path).as_posix()
        if rel in self._written_paths:
            return self.overlay_path / rel
        return self.main_cwd / rel_path

    def mark_written(self, rel_path: str) -> None:
        """Mark a path as written to overlay.

        Args:
            rel_path: Path relative to main cwd
        """
        self._written_paths.add(Path(rel_path).as_posix())

    def copy_all_to_main(self) -> bool:
        """Copy all written overlay files back to main cwd.

        Returns:
            True if all copies succeeded, False if any failed
        """
        all_ok = True
        for rel in self._written_paths:
            src = self.overlay_path / rel
            dst = self.main_cwd / rel
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            except Exception:
                all_ok = False
        return all_ok

    @property
    def written_paths(self) -> Set[str]:
        """Return a copy of the set of paths written to overlay."""
        return self._written_paths.copy()
