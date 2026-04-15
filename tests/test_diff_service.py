"""
Tests for diff service (M9).
Mirrors: ClaudeCode-main/src/utils/diff.ts
"""
from __future__ import annotations

import pytest
from py_claw.services.diff import (
    StructuredPatch,
    StructuredPatchHunk,
    CONTEXT_LINES,
    DIFF_TIMEOUT_MS,
    structured_patch,
    get_patch_from_contents,
    count_lines_changed,
    adjust_hunk_line_numbers,
)


class TestStructuredPatchHunk:
    def test_create_hunk(self):
        hunk = StructuredPatchHunk(
            oldStart=1,
            oldLines=3,
            newStart=1,
            newLines=3,
            lines=[" hello", " world", " goodbye"],
        )
        assert hunk.oldStart == 1
        assert hunk.oldLines == 3
        assert len(hunk.lines) == 3


class TestStructuredPatch:
    def test_create_patch(self):
        hunk = StructuredPatchHunk(
            oldStart=1,
            oldLines=2,
            newStart=1,
            newLines=2,
            lines=[" hello", " world"],
        )
        patch = StructuredPatch(hunks=[hunk])
        assert len(patch.hunks) == 1


class TestConstants:
    def test_context_lines_default(self):
        assert CONTEXT_LINES == 3

    def test_diff_timeout_default(self):
        assert DIFF_TIMEOUT_MS == 5000


class TestGetPatchFromContents:
    def test_no_changes(self):
        content = "line1\nline2\nline3"
        hunks = get_patch_from_contents("test.txt", content, content)
        assert hunks == []

    def test_simple_addition(self):
        old = "line1\nline2"
        new = "line1\nline2\nline3"
        hunks = get_patch_from_contents("test.txt", old, new)
        assert len(hunks) >= 1

    def test_simple_removal(self):
        old = "line1\nline2\nline3"
        new = "line1\nline3"
        hunks = get_patch_from_contents("test.txt", old, new)
        assert len(hunks) >= 1

    def test_simple_modification(self):
        old = "line1\nline2\nline3"
        new = "line1\nmodified\nline3"
        hunks = get_patch_from_contents("test.txt", old, new)
        assert len(hunks) >= 1

    def test_new_file(self):
        new = "line1\nline2"
        hunks = get_patch_from_contents("new.txt", "", new)
        assert len(hunks) >= 1


class TestCountLinesChanged:
    def test_no_changes(self):
        hunks = []
        added, removed = count_lines_changed(hunks)
        assert added == 0
        assert removed == 0

    def test_additions_only(self):
        hunk = StructuredPatchHunk(
            oldStart=1,
            oldLines=0,
            newStart=1,
            newLines=2,
            lines=["+line1", "+line2"],
        )
        added, removed = count_lines_changed([hunk])
        assert added == 2
        assert removed == 0

    def test_removals_only(self):
        hunk = StructuredPatchHunk(
            oldStart=1,
            oldLines=2,
            newStart=1,
            newLines=0,
            lines=["-line1", "-line2"],
        )
        added, removed = count_lines_changed([hunk])
        assert added == 0
        assert removed == 2

    def test_mixed_changes(self):
        hunk = StructuredPatchHunk(
            oldStart=1,
            oldLines=3,
            newStart=1,
            newLines=3,
            lines=[" line0", "-old", "+new", " line3"],
        )
        added, removed = count_lines_changed([hunk])
        assert added == 1
        assert removed == 1

    def test_new_file_content(self):
        hunks = []
        content = "line1\nline2\nline3"
        added, removed = count_lines_changed(hunks, new_file_content=content)
        assert added == 3
        assert removed == 0


class TestAdjustHunkLineNumbers:
    def test_no_offset(self):
        hunks = [
            StructuredPatchHunk(
                oldStart=10,
                oldLines=5,
                newStart=10,
                newLines=5,
                lines=[" test"],
            )
        ]
        adjusted = adjust_hunk_line_numbers(hunks, 0)
        assert adjusted[0].oldStart == 10
        assert adjusted[0].newStart == 10

    def test_with_offset(self):
        hunks = [
            StructuredPatchHunk(
                oldStart=10,
                oldLines=5,
                newStart=10,
                newLines=5,
                lines=[" test"],
            )
        ]
        adjusted = adjust_hunk_line_numbers(hunks, 5)
        assert adjusted[0].oldStart == 15
        assert adjusted[0].newStart == 15

    def test_multiple_hunks(self):
        hunks = [
            StructuredPatchHunk(oldStart=1, oldLines=2, newStart=1, newLines=2, lines=[]),
            StructuredPatchHunk(oldStart=10, oldLines=3, newStart=10, newLines=3, lines=[]),
        ]
        adjusted = adjust_hunk_line_numbers(hunks, 20)
        assert adjusted[0].oldStart == 21
        assert adjusted[1].oldStart == 30


class TestStructuredPatchFunction:
    def test_identical_texts(self):
        text = "line1\nline2\nline3"
        result = structured_patch("a.txt", "b.txt", text, text)
        assert result is None

    def test_different_texts(self):
        old = "line1\nline2"
        new = "line1\nmodified\nline3"
        result = structured_patch("a.txt", "b.txt", old, new)
        assert result is not None
        assert len(result.hunks) >= 1

    def test_empty_old(self):
        old = ""
        new = "line1\nline2"
        result = structured_patch("a.txt", "b.txt", old, new)
        assert result is not None

    def test_empty_new(self):
        old = "line1\nline2"
        new = ""
        result = structured_patch("a.txt", "b.txt", old, new)
        assert result is not None

    def test_both_empty(self):
        result = structured_patch("a.txt", "b.txt", "", "")
        assert result is None
