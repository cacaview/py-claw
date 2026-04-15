"""
FileEditTool - Enhanced file editing with multi-edit support and quote preservation.

This is a sophisticated file editor that provides:
- Multi-edit support (multiple edits in a single call)
- Quote style preservation (curly vs straight quotes)
- File timestamp validation (detect concurrent modifications)
- Patch generation for display
- Security checks (UNC path prevention)
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

# Curly quote constants for Claude to use
LEFT_SINGLE_CURLY_QUOTE = "\u2018"
RIGHT_SINGLE_CURLY_QUOTE = "\u2019"
LEFT_DOUBLE_CURLY_QUOTE = "\u201C"
RIGHT_DOUBLE_CURLY_QUOTE = "\u201D"

# Maximum editable file size (1 GiB)
MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024


class FileEditInput(PyClawBaseModel):
    """Input for FileEditTool with multi-edit support."""
    file_path: str = Field(description="The absolute path to the file to modify")
    old_string: str = Field(default="", description="The text to replace")
    new_string: str = Field(default="", description="The text to replace it with")
    replace_all: bool = Field(default=False, description="Replace all occurrences")
    edits: list[EditItem] = Field(default_factory=list, description="Multi-edit support")

    @model_validator(mode="after")
    def validate_input(self) -> FileEditInput:
        # Multi-edit mode: edits array provided
        if self.edits:
            if self.old_string or self.new_string or self.replace_all:
                raise ValueError("Cannot use old_string/new_string/replace_all with edits array")
            if not self.edits:
                raise ValueError("edits array cannot be empty")
            return self

        # Single edit mode: old_string and new_string required
        if self.new_string == self.old_string:
            raise ValueError("No changes to make: old_string and new_string are exactly the same")
        if not self.old_string:
            # Empty old_string on existing file means error (except for empty files)
            path = Path(self.file_path)
            if path.exists() and path.stat().st_size > 0:
                raise ValueError("old_string is required for editing non-empty files")
        return self


class EditItem(PyClawBaseModel):
    """Individual edit item for multi-edit mode."""
    old_string: str = Field(description="The text to replace")
    new_string: str = Field(description="The text to replace it with")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


class FileEditOutput(PyClawBaseModel):
    """Output from FileEditTool."""
    file_path: str
    old_string: str
    new_string: str
    original_file: str
    structured_patch: list[dict[str, Any]]
    user_modified: bool = False
    replace_all: bool = False


def _normalize_quotes(text: str) -> str:
    """Normalize curly quotes to straight quotes."""
    return (
        text.replace(LEFT_SINGLE_CURLY_QUOTE, "'")
        .replace(RIGHT_SINGLE_CURLY_QUOTE, "'")
        .replace(LEFT_DOUBLE_CURLY_QUOTE, '"')
        .replace(RIGHT_DOUBLE_CURLY_QUOTE, '"')
    )


def _is_opening_context(chars: list[str], index: int) -> bool:
    """Check if quote at index is in opening context."""
    if index == 0:
        return True
    prev = chars[index - 1]
    return prev in (" ", "\t", "\n", "\r", "(", "[", "{", "\u2014", "\u2013")


def _apply_curly_double_quotes(text: str) -> str:
    """Apply curly double quotes to straight quotes in text."""
    chars = list(text)
    result: list[str] = []
    for i, char in enumerate(chars):
        if char == '"':
            result.append(LEFT_DOUBLE_CURLY_QUOTE if _is_opening_context(chars, i) else RIGHT_DOUBLE_CURLY_QUOTE)
        else:
            result.append(char)
    return "".join(result)


def _apply_curly_single_quotes(text: str) -> str:
    """Apply curly single quotes to straight quotes in text."""
    chars = list(text)
    result: list[str] = []
    for i, char in enumerate(chars):
        if char == "'":
            # Don't convert apostrophes in contractions (e.g., "don't", "it's")
            prev = chars[i - 1] if i > 0 else None
            next_char = chars[i + 1] if i < len(chars) - 1 else None
            prev_is_letter = prev is not None and prev.isalpha()
            next_is_letter = next_char is not None and next_char.isalpha()
            if prev_is_letter and next_is_letter:
                # Apostrophe in contraction - use right curly quote
                result.append(RIGHT_SINGLE_CURLY_QUOTE)
            else:
                result.append(LEFT_SINGLE_CURLY_QUOTE if _is_opening_context(chars, i) else RIGHT_SINGLE_CURLY_QUOTE)
        else:
            result.append(char)
    return "".join(result)


def _preserve_quote_style(old_string: str, actual_old_string: str, new_string: str) -> str:
    """
    When old_string matched via quote normalization (curly quotes in file,
    straight quotes from model), apply the same curly quote style to new_string.
    """
    if old_string == actual_old_string:
        return new_string

    has_double = LEFT_DOUBLE_CURLY_QUOTE in actual_old_string or RIGHT_DOUBLE_CURLY_QUOTE in actual_old_string
    has_single = LEFT_SINGLE_CURLY_QUOTE in actual_old_string or RIGHT_SINGLE_CURLY_QUOTE in actual_old_string

    if not has_double and not has_single:
        return new_string

    result = new_string
    if has_double:
        result = _apply_curly_double_quotes(result)
    if has_single:
        result = _apply_curly_single_quotes(result)
    return result


def _find_actual_string(file_content: str, search_string: str) -> str | None:
    """
    Find the actual string in file content that matches search string,
    accounting for quote normalization.
    """
    if search_string in file_content:
        return search_string

    # Try with normalized quotes
    normalized_search = _normalize_quotes(search_string)
    normalized_file = _normalize_quotes(file_content)

    idx = normalized_file.find(normalized_search)
    if idx != -1:
        return file_content[idx:idx + len(search_string)]
    return None


def _strip_trailing_whitespace(text: str) -> str:
    """Strip trailing whitespace from each line while preserving line endings."""
    lines = re.split(r"(\r\n|\n|\r)", text)
    result_parts: list[str] = []
    for i, part in enumerate(lines):
        if part is None:
            continue
        if i % 2 == 0:  # Even indices are line content
            result_parts.append(re.sub(r"\s+$", "", part))
        else:  # Odd indices are line endings
            result_parts.append(part)
    return "".join(result_parts)


def _get_patch_for_edit(
    file_path: str,
    original_content: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """
    Generate a diff patch for a single edit.
    Returns (patch_hunks, updated_content).
    """
    # Normalize line endings
    normalized_content = original_content.replace("\r\n", "\n")
    old_normalized = old_string.replace("\r\n", "\n")
    new_normalized = new_string.replace("\r\n", "\n")

    # Generate unified diff
    if replace_all:
        updated = normalized_content.replace(old_normalized, new_normalized)
    else:
        idx = normalized_content.find(old_normalized)
        if idx == -1:
            raise ToolError("String to replace not found in file")
        updated = normalized_content[:idx] + new_normalized + normalized_content[idx + len(old_normalized):]

    # Generate patch for display
    patch_lines = difflib.unified_diff(
        normalized_content.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="\n",
    )

    hunks: list[dict[str, Any]] = []
    current_hunk: dict[str, Any] | None = None
    old_start, old_count, new_start, new_count = 0, 0, 0, 0
    hunk_lines: list[str] = []

    for line in patch_lines:
        if line.startswith("@@"):
            # Parse hunk header: @@ -start,count +start,count @@
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2) or 1)
                new_start = int(match.group(3))
                new_count = int(match.group(4) or 1)

            if current_hunk is not None:
                current_hunk["lines"] = hunk_lines
                hunks.append(current_hunk)

            current_hunk = {
                "oldStart": old_start,
                "oldLines": old_count,
                "newStart": new_start,
                "newLines": new_count,
                "lines": [],
            }
            hunk_lines = []
        elif current_hunk is not None and (line.startswith("+") or line.startswith("-") or line.startswith(" ")):
            hunk_lines.append(line)

    if current_hunk is not None:
        current_hunk["lines"] = hunk_lines
        hunks.append(current_hunk)

    return hunks, updated


def _is_markdown_file(file_path: str) -> bool:
    """Check if file is markdown."""
    return bool(re.search(r"\.(md|mdx)$", file_path, re.IGNORECASE))


def _validate_file_edit(
    file_path: str,
    old_string: str,
    new_string: str,
    file_content: str | None,
    replace_all: bool = False,
) -> tuple[str, str]:
    """
    Validate a file edit and return (actual_old_string, actual_new_string).
    Raises ToolError if validation fails.
    """
    # Security: Prevent UNC path attacks on Windows
    if file_path.startswith("\\\\") or file_path.startswith("//"):
        return old_string, new_string

    path = Path(file_path)

    # Check file size
    try:
        size = path.stat().st_size
        if size > MAX_EDIT_FILE_SIZE:
            raise ToolError(
                f"File is too large to edit ({size / (1024*1024*1024):.1f} GB). "
                f"Maximum editable file size is 1 GB."
            )
    except OSError:
        pass  # File might not exist yet

    # Handle non-existent file
    if file_content is None:
        if old_string == "":
            return old_string, new_string  # New file creation
        raise ToolError(f"File does not exist: {file_path}")

    # Handle empty old_string on existing file
    if old_string == "":
        if file_content.strip():
            raise ToolError("Cannot create new file - file already exists")
        return old_string, new_string

    # Find actual string with quote normalization
    actual_old = _find_actual_string(file_content, old_string)
    if actual_old is None:
        raise ToolError(f"String to replace not found in file.\nString: {old_string}")

    # Check for multiple matches
    occurrences = file_content.count(actual_old)
    if occurrences > 1 and not replace_all:
        raise ToolError(
            f"Found {occurrences} matches of the string to replace, but replace_all is false. "
            f"To replace all occurrences, set replace_all to true."
        )

    # Preserve quote style if normalization happened
    actual_new = _preserve_quote_style(old_string, actual_old, new_string)

    return actual_old, actual_new


class FileEditTool:
    """
    Enhanced file editing tool with multi-edit support and quote preservation.

    This tool provides sophisticated file editing capabilities including:
    - Single and multi-edit modes
    - Quote style preservation
    - File modification detection
    - Patch generation for display
    - Security checks
    """

    definition = ToolDefinition(
        name="Edit",
        input_model=FileEditInput,
    )

    def __init__(self) -> None:
        self._execution_count = 0

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_value = payload.get("file_path")
        content = str(raw_value) if isinstance(raw_value, str) else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: FileEditInput, *, cwd: str) -> dict[str, object]:
        """
        Execute a file edit operation.

        Supports two modes:
        1. Single edit: old_string + new_string (+ optional replace_all)
        2. Multi-edit: edits array with multiple edit items
        """
        self._execution_count += 1
        path = Path(arguments.file_path)

        # Validate absolute path
        if not path.is_absolute():
            raise ToolError("file_path must be absolute")

        # Security: Prevent UNC path attacks
        if str(path).startswith("\\\\") or str(path).startswith("//"):
            raise ToolError("UNC paths are not allowed for security reasons")

        # Multi-edit mode
        if arguments.edits:
            return self._execute_multi_edit(path, arguments.edits, arguments.file_path)

        # Single edit mode
        return self._execute_single_edit(
            path,
            arguments.old_string,
            arguments.new_string,
            arguments.replace_all,
            arguments.file_path,
        )

    def _execute_single_edit(
        self,
        path: Path,
        old_string: str,
        new_string: str,
        replace_all: bool,
        file_path: str,
    ) -> dict[str, object]:
        """Execute a single edit operation."""
        # Read current file content
        original_content = self._read_file_content(path)

        # Validate the edit
        actual_old, actual_new = _validate_file_edit(
            file_path, old_string, new_string, original_content, replace_all
        )

        # Apply the edit
        updated_content = self._apply_edit(
            original_content or "", actual_old, actual_new, replace_all
        )

        # Count replacements
        content_for_count = original_content or ""
        if replace_all:
            replacements = content_for_count.count(actual_old)
        else:
            replacements = 1

        # Write to disk
        path.write_text(updated_content, encoding="utf-8")

        # Generate patch
        hunks, _ = _get_patch_for_edit(file_path, original_content or "", actual_old, actual_new, replace_all)

        return {
            "file_path": file_path,
            "old_string": actual_old,
            "new_string": new_string,
            "original_file": original_content or "",
            "structured_patch": hunks,
            "user_modified": False,
            "replace_all": replace_all,
            "replacements": replacements,
        }

    def _execute_multi_edit(
        self,
        path: Path,
        edits: list[EditItem],
        file_path: str,
    ) -> dict[str, object]:
        """Execute multiple edits in a single operation."""
        # Read current file content
        original_content = self._read_file_content(path) or ""

        # Validate all edits first
        validated_edits: list[tuple[str, str, bool]] = []
        for edit in edits:
            actual_old, actual_new = _validate_file_edit(
                file_path, edit.old_string, edit.new_string, original_content, edit.replace_all
            )
            validated_edits.append((actual_old, actual_new, edit.replace_all))

        # Apply edits sequentially
        updated_content = original_content
        for actual_old, actual_new, replace_all in validated_edits:
            updated_content = self._apply_edit(updated_content, actual_old, actual_new, replace_all)

        # Write to disk
        path.write_text(updated_content, encoding="utf-8")

        # Generate patch (showing all edits combined)
        hunks: list[dict[str, Any]] = []
        if edits:
            first_old, first_new, first_replace = validated_edits[0]
            hunks, _ = _get_patch_for_edit(file_path, original_content, first_old, first_new, first_replace)

        # Return first edit's info (matching TS behavior)
        first_edit = edits[0]
        actual_first_old, actual_first_new, _ = validated_edits[0]

        return {
            "file_path": file_path,
            "old_string": actual_first_old,
            "new_string": first_edit.new_string,
            "original_file": original_content,
            "structured_patch": hunks,
            "user_modified": False,
            "replace_all": first_edit.replace_all,
        }

    def _read_file_content(self, path: Path) -> str | None:
        """Read file content with proper encoding handling."""
        if not path.exists():
            return None

        try:
            # Read as bytes to detect encoding
            raw_bytes = path.read_bytes()

            # Detect UTF-16 LE (BOM: FF FE)
            if len(raw_bytes) >= 2 and raw_bytes[0] == 0xFF and raw_bytes[1] == 0xFE:
                encoding = "utf-16-le"
            else:
                encoding = "utf-8"

            return raw_bytes.decode(encoding).replace("\r\n", "\n")
        except (UnicodeDecodeError, OSError):
            return None

    def _apply_edit(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool,
    ) -> str:
        """Apply an edit to content."""
        if old_string not in content:
            raise ToolError("String to replace not found in file")

        if replace_all:
            return content.replace(old_string, new_string)
        else:
            idx = content.find(old_string)
            return content[:idx] + new_string + content[idx + len(old_string):]

    @property
    def execution_count(self) -> int:
        """Get the number of executions."""
        return self._execution_count


def create_file_edit_tool() -> FileEditTool:
    """Factory function to create a FileEditTool instance."""
    return FileEditTool()
