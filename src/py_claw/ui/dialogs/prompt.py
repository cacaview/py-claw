"""PromptDialog - Ask user logic.

Re-implements ClaudeCode-main/src/components/PromptDialog.tsx
"""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.themed_text import ThemedText
from py_claw.tools.ask_user_question_tool import AskUserQuestionToolInput


class PromptDialog(Dialog):
    """Dialog for User Questions."""

    def __init__(
        self,
        arguments: AskUserQuestionToolInput,
        on_accept: Callable[[dict[str, str], dict], None] | None = None,
        on_decline: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._arguments = arguments
        self._on_accept = on_accept
        self._on_decline = on_decline
        first_q = arguments.questions[0].question if arguments.questions else "Question?"
        
        super().__init__(
            title="Question",
            body=first_q,
            confirm_label="Accept",
            deny_label="Decline",
            id=id,
            classes=classes,
        )

    def confirm(self) -> None:
        """Handle allow (simplified mock of full form)."""
        self._exit_state = ExitState.CONFIRMED
        if self._on_accept:
            # We mock the simplest case: user picking first option of first question.
            answers = {}
            if self._arguments.questions and self._arguments.questions[0].options:
                answers[self._arguments.questions[0].header] = self._arguments.questions[0].options[0].label
            self._on_accept(answers, {})

    def deny(self) -> None:
        """Handle deny."""
        self._exit_state = ExitState.DENIED
        if self._on_decline:
            self._on_decline()