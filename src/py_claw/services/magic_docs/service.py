"""
MagicDocs service.

Automatically maintains markdown files marked with # MAGIC DOC: header.
Scans directories for files with this marker and keeps them updated
based on recent changes and context.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from py_claw.services.magic_docs.config import (
    MAGIC_DOC_HEADER,
    get_magic_docs_config,
)

from .types import MagicDoc, MagicDocStats, MagicDocUpdate

if TYPE_CHECKING:
    from collections.abc import Iterator


def scan_for_magic_docs(
    directories: list[str] | None = None,
    include_patterns: list[str] | None = None,
) -> list[MagicDoc]:
    """Scan directories for magic doc files.

    Args:
        directories: List of directories to scan (defaults to config)
        include_patterns: Glob patterns for files to include

    Returns:
        List of MagicDoc objects for found files
    """
    config = get_magic_docs_config()

    if directories is None:
        directories = config.scan_directories
    if include_patterns is None:
        include_patterns = config.include_patterns

    magic_docs: list[MagicDoc] = []

    for directory in directories:
        dir_path = Path(directory)
        if not dir_path.exists():
            continue

        for pattern in include_patterns:
            for file_path in dir_path.glob(pattern):
                if not file_path.is_file():
                    continue

                # Check if it's a magic doc
                doc = parse_magic_doc(file_path)
                if doc is not None:
                    magic_docs.append(doc)

    return magic_docs


def parse_magic_doc(file_path: Path) -> MagicDoc | None:
    """Parse a magic doc file.

    Returns None if the file is not a magic doc (missing header).
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        # Find the magic doc header
        header_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith(MAGIC_DOC_HEADER):
                header_line = i
                break

        if header_line is None:
            return None

        # Extract title (first heading after header)
        title = f"Magic Doc: {file_path.name}"
        for line in lines[header_line:]:
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break

        # Get file stats
        stat = file_path.stat()

        # Calculate content hash
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        # Parse last updated from file or use mtime
        last_updated = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        return MagicDoc(
            path=file_path,
            title=title,
            last_updated=last_updated,
            size_bytes=stat.st_size,
            content_hash=content_hash,
        )

    except (OSError, IOError):
        return None


def update_magic_doc(
    file_path: Path,
    new_content: str,
) -> MagicDocUpdate:
    """Update a magic doc file with new content.

    Args:
        file_path: Path to the magic doc file
        new_content: New content to write

    Returns:
        MagicDocUpdate with result details
    """
    try:
        old_content = file_path.read_text(encoding="utf-8")
        old_lines = old_content.split("\n")
        new_lines = new_content.split("\n")

        # Find the magic doc header
        header_index = -1
        for i, line in enumerate(old_lines):
            if line.strip().startswith(MAGIC_DOC_HEADER):
                header_index = i
                break

        if header_index == -1:
            return MagicDocUpdate(
                path=file_path,
                success=False,
                message="File is not a magic doc",
                error="Missing MAGIC DOC: header",
            )

        # Preserve the header and everything before it
        preserved_lines = old_lines[:header_index]

        # Combine preserved with new content
        combined_lines = preserved_lines + ["\n"] + new_lines.split("\n")
        combined_content = "\n".join(combined_lines)

        # Write the updated content
        file_path.write_text(combined_content, encoding="utf-8")

        lines_added = len(new_lines)
        lines_removed = len(old_lines)

        return MagicDocUpdate(
            path=file_path,
            success=True,
            message="Magic doc updated successfully",
            lines_added=lines_added,
            lines_removed=lines_removed,
        )

    except Exception as e:
        return MagicDocUpdate(
            path=file_path,
            success=False,
            message=f"Failed to update magic doc: {e}",
            error=str(e),
        )


def get_magic_docs_stats() -> MagicDocsStats:
    """Get statistics about magic docs."""
    docs = scan_for_magic_docs()

    total_size = sum(doc.size_bytes for doc in docs)
    last_scan = datetime.now(timezone.utc)

    return MagicDocsStats(
        total_docs=len(docs),
        total_size_bytes=total_size,
        last_scan=last_scan,
        updates_count=0,  # Would need state tracking
        errors_count=0,
    )


def is_magic_doc(file_path: Path) -> bool:
    """Check if a file is a magic doc.

    Args:
        file_path: Path to check

    Returns:
        True if the file has MAGIC DOC: header
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith(MAGIC_DOC_HEADER):
                    return True
                # Stop after first few lines
                if line.startswith("#"):
                    continue
                break
    except (OSError, IOError):
        pass

    return False
