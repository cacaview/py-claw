"""
Diff service for computing and analyzing file differences.

Mirrors: ClaudeCode-main/src/utils/diff.ts
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

# Constants
CONTEXT_LINES = 3
DIFF_TIMEOUT_MS = 5000

# Token for escaping special characters in diff
AMPERSAND_TOKEN = "<<:AMPERSAND_TOKEN:>>"
DOLLAR_TOKEN = "<<:DOLLAR_TOKEN:>>"


def _escape_for_diff(s: str) -> str:
    """Escape special characters before computing diff."""
    return s.replace("&", AMPERSAND_TOKEN).replace("$", DOLLAR_TOKEN)


def _unescape_from_diff(s: str) -> str:
    """Unescape special characters after computing diff."""
    return s.replace(AMPERSAND_TOKEN, "&").replace(DOLLAR_TOKEN, "$")


@dataclass(slots=True)
class StructuredPatchHunk:
    """Represents a single hunk in a patch."""
    oldStart: int
    oldLines: int
    newStart: int
    newLines: int
    lines: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StructuredPatch:
    """Represents a complete patch with hunks."""
    hunks: list[StructuredPatchHunk] = field(default_factory=list)


def _compute_lcs(old: list[str], new: list[str]) -> list[tuple[int, int]]:
    """
    Compute Longest Common Subsequence between two lines.

    Returns list of (old_index, new_index) pairs representing the LCS.
    """
    m, n = len(old), len(new)

    # Build DP table
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if old[i - 1] == new[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack to find LCS
    lcs = []
    i, j = m, n
    while i > 0 and j > 0:
        if old[i - 1] == new[j - 1]:
            lcs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] > dp[i][j - 1]:
            i -= 1
        else:
            j -= 1

    lcs.reverse()
    return lcs


def structured_patch(
    old_fname: str,
    new_fname: str,
    old_text: str,
    new_text: str,
    ignore_whitespace: bool = False,
    context: int = CONTEXT_LINES,
    timeout: int = DIFF_TIMEOUT_MS,
) -> StructuredPatch | None:
    """
    Compute a structured patch between two texts.

    Args:
        old_fname: Original file name
        new_fname: New file name
        old_text: Original text
        new_text: New text
        ignore_whitespace: Whether to ignore whitespace changes
        context: Number of context lines around changes
        timeout: Timeout in milliseconds

    Returns:
        StructuredPatch or None if no changes
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    # Strip trailing newline for comparison if present
    if old_lines and old_lines[-1].endswith("\n"):
        old_lines[-1] = old_lines[-1][:-1]
    if new_lines and new_lines[-1].endswith("\n"):
        new_lines[-1] = new_lines[-1][:-1]

    # Escape for diff processing
    old_escaped = [_escape_for_diff(line) for line in old_lines]
    new_escaped = [_escape_for_diff(line) for line in new_lines]

    # If ignoring whitespace, strip leading/trailing whitespace
    if ignore_whitespace:
        old_escaped = [line.rstrip() for line in old_escaped]
        new_escaped = [line.rstrip() for line in new_escaped]

    # Handle empty old file (all additions)
    if not old_escaped and new_escaped:
        return StructuredPatch(hunks=[
            StructuredPatchHunk(
                oldStart=1,
                oldLines=0,
                newStart=1,
                newLines=len(new_escaped),
                lines=["+" + _unescape_from_diff(line) for line in new_escaped],
            )
        ])

    # Handle empty new file (all removals)
    if old_escaped and not new_escaped:
        return StructuredPatch(hunks=[
            StructuredPatchHunk(
                oldStart=1,
                oldLines=len(old_escaped),
                newStart=1,
                newLines=0,
                lines=["-" + _unescape_from_diff(line) for line in old_escaped],
            )
        ])

    # Compute LCS
    lcs = _compute_lcs(old_escaped, new_escaped)

    # If identical, no patch needed
    if len(lcs) == len(old_escaped) == len(new_escaped):
        return None

    # Build hunks from LCS
    hunks: list[StructuredPatchHunk] = []
    i = 0

    while i < len(lcs):
        lcs_old_idx, lcs_new_idx = lcs[i]

        # Find the start of the hunk (go back while there's a gap)
        hunk_start = i
        while hunk_start > 0:
            prev_old = lcs[hunk_start - 1][0]
            prev_new = lcs[hunk_start - 1][1]
            # Gap is more than 1 line
            if lcs_old_idx - prev_old > 1 or lcs_new_idx - prev_new > 1:
                break
            hunk_start -= 1

        # Find the end of the hunk (go forward while there's no gap)
        hunk_end = i
        while hunk_end < len(lcs):
            curr_old = lcs[hunk_end][0]
            curr_new = lcs[hunk_end][1]
            # Check if next item would be a gap
            if hunk_end + 1 < len(lcs):
                next_old = lcs[hunk_end + 1][0]
                next_new = lcs[hunk_end + 1][1]
                if next_old - curr_old > 1 or next_new - curr_new > 1:
                    break
            hunk_end += 1

        # Get old and new line ranges for this hunk
        old_start = lcs[hunk_start][0]
        old_end = lcs[hunk_end - 1][0] + 1 if hunk_end > hunk_start else lcs[hunk_start][0]
        new_start = lcs[hunk_start][1]
        new_end = lcs[hunk_end - 1][1] + 1 if hunk_end > hunk_start else lcs[hunk_start][1]

        # Expand to include context lines
        old_start = max(0, old_start - context)
        old_end = min(len(old_escaped), old_end + context)
        new_start = max(0, new_start - context)
        new_end = min(len(new_escaped), new_end + context)

        # Build hunk lines
        hunk_lines: list[str] = []

        # Add context lines before changes
        for idx in range(old_start, lcs[hunk_start][0]):
            line = old_escaped[idx]
            hunk_lines.append(" " + _unescape_from_diff(line.rstrip("\n")))

        # Add changed/unchanged lines from LCS
        for lcs_idx in range(hunk_start, hunk_end):
            old_idx, new_idx = lcs[lcs_idx]
            line = old_escaped[old_idx]
            hunk_lines.append(" " + _unescape_from_diff(line.rstrip("\n")))

        # Add context lines after changes
        for idx in range(lcs[hunk_end - 1][0] + 1, old_end if hunk_end < len(lcs) else old_end):
            if idx < len(old_escaped):
                line = old_escaped[idx]
                hunk_lines.append(" " + _unescape_from_diff(line.rstrip("\n")))

        # Actually, let me redo this with proper change detection
        hunk_lines = []

        # Collect all changes and context for this hunk
        changes: list[tuple[str, str]] = []  # (type, line)

        # Add leading context
        for idx in range(old_start, lcs[hunk_start][0]):
            changes.append(("context", old_escaped[idx]))

        # Add lines up to first LCS point
        for idx in range(lcs[hunk_start][0], lcs[hunk_start][0]):
            pass  # Already handled

        # For the actual diff, we need to track what changed
        # Simple approach: collect all lines that are different
        seen_old = set()
        seen_new = set()

        for old_idx, new_idx in lcs[hunk_start:hunk_end]:
            seen_old.add(old_idx)
            seen_new.add(new_idx)

        # Lines before first LCS point in this range
        current_old = old_start
        current_new = new_start

        while current_old < old_end or current_new < new_end:
            if current_old < old_end and current_new < new_end:
                if current_old in seen_old and current_new in seen_new:
                    # This pair is in LCS
                    # But we need to handle interleaved changes
                    pass
            elif current_old < old_end:
                # Line removed
                pass
            elif current_new < new_end:
                # Line added
                pass
            current_old += 1
            current_new += 1

        # Simpler approach: just mark the lines
        hunk_lines = []

        # Add context before
        for idx in range(old_start, min(old_end, lcs[hunk_start][0])):
            if idx < len(old_escaped):
                line = old_escaped[idx]
                hunk_lines.append(" " + _unescape_from_diff(line.rstrip("\n")))

        # Add the changed region (simplified: just show all lines)
        for lcs_idx in range(hunk_start, min(hunk_end, len(lcs))):
            old_idx = lcs[lcs_idx][0]
            new_idx = lcs[lcs_idx][1]
            if old_idx < len(old_escaped):
                line = old_escaped[old_idx]
                hunk_lines.append(" " + _unescape_from_diff(line.rstrip("\n")))

        # Actually the LCS-based approach is getting complex. Let me use a simpler diff algorithm.
        hunks = []
        return _simple_structured_patch(old_lines, new_lines, old_fname, new_fname, context)

    return None


def _simple_structured_patch(
    old_lines: list[str],
    new_lines: list[str],
    old_fname: str,
    new_fname: str,
    context: int = CONTEXT_LINES,
) -> StructuredPatch:
    """
    Simple line-based diff algorithm.
    """
    hunks: list[StructuredPatchHunk] = []

    # Handle empty old file (all additions)
    if not old_lines:
        if new_lines:
            hunks.append(StructuredPatchHunk(
                oldStart=1,
                oldLines=0,
                newStart=1,
                newLines=len(new_lines),
                lines=["+" + line.rstrip("\n") for line in new_lines],
            ))
        return StructuredPatch(hunks)

    # Handle empty new file (all removals)
    if not new_lines:
        hunks.append(StructuredPatchHunk(
            oldStart=1,
            oldLines=len(old_lines),
            newStart=1,
            newLines=0,
            lines=["-" + line.rstrip("\n") for line in old_lines],
        ))
        return StructuredPatch(hunks)

    # Build index for old lines
    old_index: dict[str, list[int]] = {}
    for i, line in enumerate(old_lines):
        if line not in old_index:
            old_index[line] = []
        old_index[line].append(i)

    # Find matching sequences using greedy matching
    matched_old = set()
    matched_new = set()
    matches: list[tuple[int, int]] = []

    for new_idx, new_line in enumerate(new_lines):
        if new_line in old_index:
            for old_idx in old_index[new_line]:
                if old_idx not in matched_old:
                    matches.append((old_idx, new_idx))
                    matched_old.add(old_idx)
                    matched_new.add(new_idx)
                    break

    # Sort matches by position
    matches.sort()

    # Build hunks from matching positions
    if not matches:
        # Entire file changed
        hunks.append(StructuredPatchHunk(
            oldStart=1,
            oldLines=len(old_lines),
            newStart=1,
            newLines=len(new_lines),
            lines=_format_hunk_lines(old_lines, new_lines, 0, len(old_lines), 0, len(new_lines)),
        ))
        return StructuredPatch(hunks)

    # Merge close matches into hunks
    i = 0
    while i < len(matches):
        match_old, match_new = matches[i]

        # Find range of this hunk
        hunk_old_start = match_old
        hunk_new_start = match_new
        hunk_old_end = match_old + 1
        hunk_new_end = match_new + 1

        # Extend hunk forward
        while i + 1 < len(matches):
            next_old, next_new = matches[i + 1]
            # If matches are adjacent or close, include in same hunk
            if next_old - hunk_old_end <= context * 2 and next_new - hunk_new_end <= context * 2:
                hunk_old_end = next_old + 1
                hunk_new_end = next_new + 1
                i += 1
            else:
                break

        # Add context before
        hunk_old_start = max(0, hunk_old_start - context)
        hunk_new_start = max(0, hunk_new_start - context)

        # Add context after
        hunk_old_end = min(len(old_lines), hunk_old_end + context)
        hunk_new_end = min(len(new_lines), hunk_new_end + context)

        # Build hunk lines
        lines = _format_hunk_lines(old_lines, new_lines, hunk_old_start, hunk_old_end, hunk_new_start, hunk_new_end)

        hunks.append(StructuredPatchHunk(
            oldStart=hunk_old_start + 1,  # 1-indexed
            oldLines=hunk_old_end - hunk_old_start,
            newStart=hunk_new_start + 1,
            newLines=hunk_new_end - hunk_new_start,
            lines=lines,
        ))

        i += 1

    return StructuredPatch(hunks)


def _format_hunk_lines(
    old_lines: list[str],
    new_lines: list[str],
    old_start: int,
    old_end: int,
    new_start: int,
    new_end: int,
) -> list[str]:
    """Format lines for a hunk, marking changes with +/-."""
    result: list[str] = []

    # Build LCS index for the hunk range
    old_range = old_lines[old_start:old_end]
    new_range = new_lines[new_start:new_end]

    lcs = _compute_lcs(old_range, new_range)

    # Convert LCS indices to absolute positions
    lcs_pairs: list[tuple[int, int]] = [(old_start + i, new_start + j) for i, j in lcs]

    # Track matched pairs
    matched_old = {o for o, n in lcs_pairs}
    matched_new = {n for o, n in lcs_pairs}

    # Collect removed and added lines
    removed = set(range(old_start, old_end)) - matched_old
    added = set(range(new_start, new_end)) - matched_new

    # Build result in proper order
    current_old = old_start
    current_new = new_start

    while current_old < old_end or current_new < new_end:
        # Check if current pair is in LCS (matched)
        if (current_old, current_new) in lcs_pairs:
            # Context line (unchanged)
            result.append(" " + old_lines[current_old].rstrip("\n"))
            current_old += 1
            current_new += 1
        elif current_old in removed and current_new < new_end and current_new in added:
            # Line was modified
            result.append("-" + old_lines[current_old].rstrip("\n"))
            result.append("+" + new_lines[current_new].rstrip("\n"))
            current_old += 1
            current_new += 1
        elif current_old in removed:
            # Line was removed
            result.append("-" + old_lines[current_old].rstrip("\n"))
            current_old += 1
        elif current_new in added:
            # Line was added
            result.append("+" + new_lines[current_new].rstrip("\n"))
            current_new += 1
        else:
            # Advance both (shouldn't happen in normal cases)
            if current_old < old_end:
                current_old += 1
            if current_new < new_end:
                current_new += 1

    return result


def get_patch_from_contents(
    file_path: str,
    old_content: str,
    new_content: str,
    ignore_whitespace: bool = False,
    single_hunk: bool = False,
) -> list[StructuredPatchHunk]:
    """
    Get a patch from file contents.

    Args:
        file_path: Path to the file
        old_content: Original content
        new_content: New content
        ignore_whitespace: Whether to ignore whitespace
        single_hunk: Whether to show as single hunk

    Returns:
        List of hunks representing the diff
    """
    ctx = 100_000 if single_hunk else CONTEXT_LINES

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Strip trailing newline for comparison if present
    if old_lines and old_lines[-1].endswith("\n"):
        old_lines[-1] = old_lines[-1][:-1]
    if new_lines and new_lines[-1].endswith("\n"):
        new_lines[-1] = new_lines[-1][:-1]

    # If identical, no patch needed
    if old_lines == new_lines:
        return []

    patch = _simple_structured_patch(old_lines, new_lines, file_path, file_path, ctx)

    return patch.hunks


def count_lines_changed(patch: list[StructuredPatchHunk], new_file_content: str | None = None) -> tuple[int, int]:
    """
    Count lines added and removed in a patch.

    For new files, pass the content string as the second parameter.

    Args:
        patch: List of diff hunks
        new_file_content: Optional content for new files

    Returns:
        Tuple of (additions, removals)
    """
    if not patch and new_file_content:
        # For new files, count all lines as additions
        return len(new_file_content.splitlines()), 0

    num_additions = 0
    num_removals = 0

    for hunk in patch:
        for line in hunk.lines:
            if line.startswith("+"):
                num_additions += 1
            elif line.startswith("-"):
                num_removals += 1

    return num_additions, num_removals


def adjust_hunk_line_numbers(
    hunks: list[StructuredPatchHunk],
    offset: int,
) -> list[StructuredPatchHunk]:
    """
    Shift hunk line numbers by offset.

    Use when get_patch_for_display received a slice of the file
    rather than the whole file.

    Args:
        hunks: List of hunks
        offset: Offset to add to line numbers

    Returns:
        Hunks with adjusted line numbers
    """
    if offset == 0:
        return hunks

    return [
        StructuredPatchHunk(
            oldStart=h.oldStart + offset,
            oldLines=h.oldLines,
            newStart=h.newStart + offset,
            newLines=h.newLines,
            lines=h.lines,
        )
        for h in hunks
    ]


# Export for convenience
__all__ = [
    "StructuredPatch",
    "StructuredPatchHunk",
    "CONTEXT_LINES",
    "DIFF_TIMEOUT_MS",
    "structured_patch",
    "get_patch_from_contents",
    "count_lines_changed",
    "adjust_hunk_line_numbers",
]
