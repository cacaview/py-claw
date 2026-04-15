"""WorkflowMultiselectDialog — GitHub workflow selection dialog.

Re-implements ClaudeCode-main/src/components/WorkflowMultiselectDialog.tsx

Allows users to select one or more GitHub workflows to install
for their repository.
"""
from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Checkbox, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.pane import Pane


class WorkflowOption:
    """Represents a workflow option."""

    def __init__(self, value: str, label: str) -> None:
        self.value = value
        self.label = label


# Predefined workflow options
WORKFLOW_OPTIONS = [
    WorkflowOption(
        value="claude",
        label="@Claude Code - Tag @claude in issues and PR comments",
    ),
    WorkflowOption(
        value="claude-review",
        label="Claude Code Review - Automated code review on new PRs",
    ),
]


class WorkflowMultiselectDialog(Dialog):
    """Dialog for selecting GitHub workflows to install.

    Shows a list of available workflows with checkboxes,
    requiring at least one selection to proceed.
    """

    def __init__(
        self,
        default_selections: list[str] | None = None,
        on_submit: Callable[[list[str]], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize workflow selection dialog.

        Args:
            default_selections: List of workflow values to pre-select
            on_submit: Callback with list of selected workflow values
            on_cancel: Callback when dialog is cancelled
            id: Optional dialog ID
            classes: Optional CSS classes
        """
        self._default_selections = set(default_selections or [])
        self._selected = set(self._default_selections)
        self._on_submit = on_submit
        self._show_error = False

        super().__init__(
            title="Select GitHub workflows to install",
            subtitle="We'll create a workflow file in your repository for each one you select.",
            body="",  # Built dynamically with checkboxes
            show_confirm_deny=False,
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the dialog layout."""
        yield Pane(title=self.title)

        yield Static(
            "More workflow examples (issue triage, CI fixes, etc.) at: "
            "https://github.com/anthropics/claude-code-action/blob/main/examples/",
            id="workflow-link",
            classes="dim",
        )

        with Vertical(id="workflow-options"):
            for option in WORKFLOW_OPTIONS:
                checked = option.value in self._selected
                yield Checkbox(
                    option.label,
                    value=checked,
                    id=f"workflow-{option.value}",
                )

        if self._show_error:
            yield Static(
                "[error]You must select at least one workflow to continue[/error]",
                id="workflow-error",
            )

        yield Static(
            "↑↓ navigate · Space toggle · Enter confirm · Esc cancel",
            id="workflow-input-guide",
            classes="dim",
        )

    def toggle_option(self, value: str) -> None:
        """Toggle a workflow option."""
        if value in self._selected:
            self._selected.discard(value)
        else:
            self._selected.add(value)
        self._show_error = False

    def submit(self) -> None:
        """Handle submission."""
        if len(self._selected) == 0:
            self._show_error = True
            self.refresh()
            return

        self._exit_state = ExitState.CONFIRMED
        if self._on_submit:
            self._on_submit(list(self._selected))

    def cancel(self) -> None:
        """Handle cancellation."""
        self._exit_state = ExitState.CANCELLED
        if self._on_cancel:
            self._on_cancel()
