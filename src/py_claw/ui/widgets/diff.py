"""StructuredDiff — Structured diff display component.

Re-implements ClaudeCode-main/src/components/design-system/StructuredDiff.tsx
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from py_claw.ui.theme import get_theme
from py_claw.ui.widgets.themed_text import ThemedText


class DiffType(Enum):
    """Type of diff line."""

    CONTEXT = "context"
    ADDED = "added"
    REMOVED = "removed"
    HEADER = "header"


@dataclass(slots=True)
class DiffLine:
    """A single diff line."""

    type: DiffType
    content: str
    old_line_no: int | None = None
    new_line_no: int | None = None


class StructuredDiff(Vertical):
    """A structured diff display.

    Shows file differences with:
    - Line numbers (old and new)
    - Color-coded additions/deletions/context
    - Collapsible sections for large diffs
    - Unified or side-by-side view mode
    """

    def __init__(
        self,
        diff_lines: list[DiffLine] | None = None,
        file_path: str | None = None,
        old_path: str | None = None,
        view_mode: str = "unified",  # "unified" | "side-by-side"
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._diff_lines = diff_lines or []
        self._file_path = file_path
        self._old_path = old_path
        self._view_mode = view_mode
        super().__init__(id=id, classes=classes)

    def on_mount(self) -> None:
        """Compose the diff view."""
        theme = get_theme()

        # File header
        if self._file_path:
            self.mount(
                ThemedText(f"--- {self._file_path}", variant="normal")
            )
        if self._old_path:
            self.mount(
                ThemedText(f"+++ {self._old_path}", variant="normal")
            )

        # Diff content
        for diff_line in self._diff_lines:
            self.mount(self._make_line_widget(diff_line))

    def _make_line_widget(self, diff_line: DiffLine) -> Horizontal:
        """Create a widget for a diff line."""
        theme = get_theme()

        # Line number column
        old_no = f"{diff_line.old_line_no:4d}" if diff_line.old_line_no else "    "
        new_no = f"{diff_line.new_line_no:4d}" if diff_line.new_line_no else "    "

        # Content prefix
        prefixes = {
            DiffType.CONTEXT: " ",
            DiffType.ADDED: "+",
            DiffType.REMOVED: "-",
            DiffType.HEADER: "=",
        }
        prefix = prefixes.get(diff_line.type, " ")

        # Color based on type
        colors = {
            DiffType.CONTEXT: theme.colors.get("text", "#ffffff"),
            DiffType.ADDED: theme.colors.get("success", "#22c55e"),
            DiffType.REMOVED: theme.colors.get("error", "#ef4444"),
            DiffType.HEADER: theme.colors.get("warning", "#f59e0b"),
        }
        color = colors.get(diff_line.type, theme.colors.get("text", "#ffffff"))

        line_content = f"[{color}]{prefix} {old_no} {new_no} {diff_line.content}[/{color}]"

        return Horizontal(
            ThemedText(line_content, variant="normal"),
            classes="diff-line",
        )

    @staticmethod
    def from_unified_diff(
        old_lines: list[str],
        new_lines: list[str],
        old_path: str = "a",
        new_path: str = "b",
    ) -> "StructuredDiff":
        """Create a StructuredDiff from old and new file contents.

        Performs a simple line-by-line diff.
        """
        diff_lines: list[DiffLine] = []

        old_line_no = 1
        new_line_no = 1

        i = 0
        j = 0

        while i < len(old_lines) or j < len(new_lines):
            if i >= len(old_lines):
                # Remaining lines are additions
                diff_lines.append(
                    DiffLine(
                        type=DiffType.ADDED,
                        content=new_lines[j],
                        new_line_no=new_line_no,
                    )
                )
                new_line_no += 1
                j += 1
            elif j >= len(new_lines):
                # Remaining lines are removals
                diff_lines.append(
                    DiffLine(
                        type=DiffType.REMOVED,
                        content=old_lines[i],
                        old_line_no=old_line_no,
                    )
                )
                old_line_no += 1
                i += 1
            elif old_lines[i] == new_lines[j]:
                # Unchanged line
                diff_lines.append(
                    DiffLine(
                        type=DiffType.CONTEXT,
                        content=old_lines[i],
                        old_line_no=old_line_no,
                        new_line_no=new_line_no,
                    )
                )
                old_line_no += 1
                new_line_no += 1
                i += 1
                j += 1
            else:
                # Lines differ - mark as removed then added
                diff_lines.append(
                    DiffLine(
                        type=DiffType.REMOVED,
                        content=old_lines[i],
                        old_line_no=old_line_no,
                    )
                )
                diff_lines.append(
                    DiffLine(
                        type=DiffType.ADDED,
                        content=new_lines[j],
                        new_line_no=new_line_no,
                    )
                )
                old_line_no += 1
                new_line_no += 1
                i += 1
                j += 1

        return StructuredDiff(
            diff_lines=diff_lines,
            old_path=old_path,
            file_path=new_path,
        )
