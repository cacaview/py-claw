"""WorktreeExitDialog — Worktree exit confirmation dialog.

Re-implements ClaudeCode-main/src/components/WorktreeExitDialog.tsx

Shown when exiting a worktree session, allowing the user to keep
or remove the worktree, with options for associated tmux sessions.
"""
from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.spinner import Spinner


class WorktreeExitDialog(Dialog):
    """Dialog for exiting a worktree session.

    Shows options to keep or remove the worktree, with optional
    tmux session management.
    """

    # Dialog states
    STATE_LOADING = "loading"
    STATE_ASKING = "asking"
    STATE_KEEPING = "keeping"
    STATE_REMOVING = "removing"
    STATE_DONE = "done"

    def __init__(
        self,
        worktree_path: str,
        worktree_branch: str,
        has_changes: bool = False,
        commit_count: int = 0,
        tmux_session_name: str | None = None,
        on_keep: Callable[[], None] | None = None,
        on_remove: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """
        Initialize worktree exit dialog.

        Args:
            worktree_path: Path to the worktree
            worktree_branch: Branch name in the worktree
            has_changes: Whether there are uncommitted changes
            commit_count: Number of commits on the worktree branch
            tmux_session_name: Name of associated tmux session (if any)
            on_keep: Callback when user chooses to keep worktree
            on_remove: Callback when user chooses to remove worktree
            on_cancel: Callback when user cancels
            id: Optional dialog ID
            classes: Optional CSS classes
        """
        self._worktree_path = worktree_path
        self._worktree_branch = worktree_branch
        self._has_changes = has_changes
        self._commit_count = commit_count
        self._tmux_session_name = tmux_session_name
        self._on_keep = on_keep
        self._on_remove = on_remove
        self._on_cancel = on_cancel
        self._state = self.STATE_ASKING

        subtitle = self._build_subtitle()

        super().__init__(
            title="Exiting worktree session",
            subtitle=subtitle,
            show_confirm_deny=False,
            id=id,
            classes=classes,
        )

    def _build_subtitle(self) -> str:
        """Build subtitle based on worktree state."""
        parts = []

        if self._has_changes and self._commit_count > 0:
            file_word = "file" if self._changes_count == 1 else "files"
            parts.append(
                f"You have {self._changes_count} uncommitted {file_word} "
                f"and {self._commit_count} commits on {self._worktree_branch}. "
                "All will be lost if you remove."
            )
        elif self._has_changes:
            file_word = "file" if self._changes_count == 1 else "files"
            parts.append(
                f"You have {self._changes_count} uncommitted {file_word}. "
                "These will be lost if you remove the worktree."
            )
        elif self._commit_count > 0:
            parts.append(
                f"You have {self._commit_count} commits on {self._worktree_branch}. "
                "The branch will be deleted if you remove the worktree."
            )
        else:
            parts.append(
                "You are working in a worktree. Keep it to continue working there, "
                "or remove it to clean up."
            )

        return " ".join(parts)

    def compose(self) -> ComposeResult:
        """Compose the dialog layout."""
        yield Pane(title=self.title)

        if self._state == self.STATE_KEEPING:
            with Horizontal(id="worktree-status"):
                yield Spinner()
                yield Static("Keeping worktree...")

        elif self._state == self.STATE_REMOVING:
            with Horizontal(id="worktree-status"):
                yield Spinner()
                yield Static("Removing worktree...")

        else:
            # Build options based on tmux session
            options = []

            if self._tmux_session_name:
                options.extend([
                    ("keep-with-tmux", "Keep worktree and tmux session"),
                    ("keep-kill-tmux", "Keep worktree, kill tmux session"),
                    ("remove-with-tmux", "Remove worktree and tmux session"),
                ])
            else:
                options.extend([
                    ("keep", "Keep worktree"),
                    ("remove", "Remove worktree"),
                ])

            with Vertical(id="worktree-options"):
                for value, label in options:
                    description = self._get_option_description(value)
                    yield Button(label, id=f"btn-{value}", variant="default")
                    if description:
                        yield Static(description, classes="dim")

    def _get_option_description(self, value: str) -> str:
        """Get description for an option."""
        if value == "keep":
            return f"Stays at {self._worktree_path}"
        elif value == "remove":
            if self._has_changes or self._commit_count > 0:
                return "All changes and commits will be lost."
            return "Clean up the worktree directory."
        elif value == "keep-with-tmux":
            return f"Stays at {self._worktree_path}. Reattach with: tmux attach -t {self._tmux_session_name}"
        elif value == "keep-kill-tmux":
            return f"Keeps worktree at {self._worktree_path}, terminates tmux session."
        elif value == "remove-with-tmux":
            tmux_note = " Tmux session terminated." if self._tmux_session_name else ""
            if self._has_changes or self._commit_count > 0:
                return f"All changes and commits will be lost.{tmux_note}"
            return f"Clean up the worktree directory.{tmux_note}"
        return ""

    def keep(self) -> None:
        """Handle keep option."""
        self._state = self.STATE_KEEPING
        self._exit_state = ExitState.CONFIRMED
        if self._on_keep:
            self._on_keep()

    def remove(self) -> None:
        """Handle remove option."""
        self._state = self.STATE_REMOVING
        self._exit_state = ExitState.CONFIRMED
        if self._on_remove:
            self._on_remove()

    def cancel(self) -> None:
        """Handle cancel."""
        self._exit_state = ExitState.CANCELLED
        if self._on_cancel:
            self._on_cancel()
