"""PromptDialog - Ask user logic.

Re-implements ClaudeCode-main/src/components/PromptDialog.tsx
"""

from __future__ import annotations

from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.tools.ask_user_question_tool import AskUserQuestionToolInput


class PromptDialog(Dialog):
    """Dialog for User Questions.

    Registers its own ``@on(Button.Pressed, ...)`` handlers rather than
    relying on the inherited ``Dialog.confirm`` — a plain override would
    shadow the decorated base handler and the buttons would never act.
    """

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

    @on(Button.Pressed, "#btn-confirm")
    def _confirm_pressed(self) -> None:
        self.confirm()

    @on(Button.Pressed, "#btn-deny")
    def _deny_pressed(self) -> None:
        self.deny()

    def confirm(self) -> None:
        """Handle accept (simplified mock of full form)."""
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

    def action_cancel(self) -> None:
        """Escape while a question is pending means decline."""
        if not self._cancel_enabled:
            return
        self.deny()
