"""
Git output parsers for py-claw runtime.

Based on ClaudeCode-main/src/utils/git.ts
"""
from __future__ import annotations

import re
from typing import Tuple

from .types import (
    GitDiffStats,
    NumstatResult,
    PerFileStats,
    StructuredPatchHunk,
)


def parse_shortstat(stdout: str) -> GitDiffStats:
    """
    Parse git diff --shortstat output.

    Args:
        stdout: Output from git diff --shortstat

    Returns:
        GitDiffStats with files count, lines added, lines removed
    """
    # Format: "X files changed" or "X files changed, Y insertions(+), Z deletions(-)"
    # Or: "X files changed, Y insertions(+)"
    # Or: "X files changed, Z deletions(-)"
    stats = GitDiffStats()

    # Match files changed
    files_match = re.search(r'(\d+) files? changed', stdout)
    if files_match:
        stats.files_count = int(files_match.group(1))

    # Match insertions
    ins_match = re.search(r'(\d+) insertions?\(\+\)', stdout)
    if ins_match:
        stats.lines_added = int(ins_match.group(1))

    # Match deletions
    del_match = re.search(r'(\d+) deletions?\(-)', stdout)
    if del_match:
        stats.lines_removed = int(del_match.group(1))

    return stats


def parse_git_numstat(stdout: str) -> NumstatResult:
    """
    Parse git diff --numstat output.

    Args:
        stdout: Output from git diff --numstat

    Returns:
        NumstatResult with stats and per-file stats
    """
    result = NumstatResult()
    per_file_stats: dict[str, PerFileStats] = {}

    for line in stdout.strip().split('\n'):
        if not line:
            continue

        # Format: <added>\t<removed>\t<path>
        parts = line.split('\t')
        if len(parts) < 3:
            continue

        added_str, removed_str, path = parts[0], parts[1], parts[2]

        # Handle binary files (shown as - for counts)
        is_binary = added_str == '-' and removed_str == '-'
        added = 0 if is_binary else int(added_str)
        removed = 0 if is_binary else int(removed_str)

        per_file_stats[path] = PerFileStats(
            added=added,
            removed=removed,
            is_binary=is_binary,
            is_untracked=False,
        )

        # Update totals
        result.stats.files_count += 1
        result.stats.lines_added += added
        result.stats.lines_removed += removed

    result.per_file_stats = per_file_stats
    return result


def parse_git_diff_hunks(diff_text: str) -> dict[str, list[StructuredPatchHunk]]:
    """
    Parse unified diff into per-file hunks.

    Args:
        diff_text: Output from git diff

    Returns:
        Dict mapping file paths to list of hunks
    """
    hunks: dict[str, list[StructuredPatchHunk]] = {}

    if not diff_text.strip():
        return hunks

    # Split by diff --git marker
    file_blocks = diff_text.split('diff --git ')

    for block in file_blocks:
        if not block.strip():
            continue

        # Parse file path from "a/path b/path" line
        lines = block.split('\n')
        if len(lines) < 2:
            continue

        # Get file path from the "index" or "---" line
        file_path = None

        for line in lines:
            if line.startswith('--- a/') or line.startswith('+++ b/'):
                # Extract path
                path_line = line[4:]  # Remove prefix
                if path_line.startswith('a/'):
                    path_line = path_line[2:]
                if path_line.startswith('b/'):
                    path_line = path_line[2:]
                # Remove possible /dev/null and trailing info
                if '\t' in path_line:
                    path_line = path_line.split('\t')[0]
                path_line = path_line.strip()
                if path_line and path_line != '/dev/null':
                    file_path = path_line
                    break

        if not file_path:
            # Try to extract from the first line
            first_line = lines[0]
            if ' b/' in first_line:
                parts = first_line.split(' b/')
                if len(parts) > 1:
                    file_path = parts[1].strip()

        if not file_path:
            continue

        # Parse hunks in this block
        file_hunks: list[StructuredPatchHunk] = []
        current_hunk: StructuredPatchHunk | None = None
        hunk_lines: list[str] = []

        for line in lines:
            if line.startswith('@@'):
                # Save previous hunk if exists
                if current_hunk is not None:
                    current_hunk.lines = hunk_lines
                    file_hunks.append(current_hunk)

                # Parse hunk header: @@ -old,count +new,count @@ optional
                # Example: @@ -1,5 +1,7 @@
                match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))?', line)
                if match:
                    old_start = int(match.group(1))
                    old_lines = int(match.group(2)) if match.group(2) else 1
                    new_start = int(match.group(3))
                    new_lines = int(match.group(4)) if match.group(4) else 1

                    current_hunk = StructuredPatchHunk(
                        old_start=old_start,
                        old_lines=old_lines,
                        new_start=new_start,
                        new_lines=new_lines,
                    )
                    hunk_lines = []

        # Save last hunk
        if current_hunk is not None:
            current_hunk.lines = hunk_lines
            file_hunks.append(current_hunk)

        if file_hunks:
            hunks[file_path] = file_hunks

    return hunks


def parse_diff_line(line: str) -> Tuple[str, int, int]:
    """
    Parse a single line from diff output.

    Args:
        line: A line from diff output

    Returns:
        Tuple of (prefix, old_line_num, new_line_num)
        prefix is one of: ' ', '+', '-', '\\'
    """
    if not line:
        return ' ', 0, 0

    prefix = line[0]
    content = line[1:]

    if prefix in ('+', '-', ' '):
        # Try to parse line numbers
        old_match = re.match(r'-(\d+)', content)
        new_match = re.match(r'\+(\d+)', content)

        old_line = int(old_match.group(1)) if old_match else 0
        new_line = int(new_match.group(1)) if new_match else 0

        return prefix, old_line, new_line
    elif prefix == '\\':
        # This is a "No newline at end of file" line
        return prefix, 0, 0

    return ' ', 0, 0


def is_binary_file_extension(path: str) -> bool:
    """
    Check if a file has a binary extension.

    Args:
        path: File path to check

    Returns:
        True if binary extension
    """
    import os
    ext = os.path.splitext(path)[1].lower()
    from .types import BINARY_EXTENSIONS
    return ext in BINARY_EXTENSIONS
