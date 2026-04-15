"""Feedback — Feedback submission component.

Re-implements ClaudeCode-main/src/components/design-system/Feedback.tsx
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Horizontal
from textual.widgets import Button, Input, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.themed_text import ThemedText


class StarRating(Static):
    """Star rating display component."""

    def __init__(
        self,
        rating: float = 0.0,  # 0.0 to 5.0
        max_stars: int = 5,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._rating = max(0.0, min(float(max_stars), rating))
        self._max_stars = max_stars
        super().__init__(id=id, classes=classes)

    def on_mount(self) -> None:
        """Render the star rating."""
        full_stars = int(self._rating)
        partial_star = self._rating - full_stars
        empty_stars = self._max_stars - full_stars - (1 if partial_star > 0 else 0)

        stars = "★" * full_stars
        if partial_star > 0:
            stars += "⯪"  # Half star approximation
        stars += "☆" * empty_stars

        self.update(stars)


class FeedbackDialog(Dialog):
    """Feedback submission dialog.

    Allows users to submit feedback with rating and comments.
    """

    def __init__(
        self,
        on_submit: Callable[[dict], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self._rating = 0
        super().__init__(
            title="Submit Feedback",
            body="Help us improve Claude Code",
            confirm_label="Submit",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the feedback form."""
        # Rating section
        yield ThemedText("How would you rate your experience?", variant="normal")

        # Star rating (1-5)
        with Horizontal(id="rating-stars"):
            for i in range(1, 6):
                yield Button(f"{'★' * i}{'☆' * (5 - i)}", id=f"star-{i}", variant="default")

        # Comment section
        yield ThemedText("Comments (optional):", variant="normal")
        yield Input(placeholder="Share your thoughts...", id="feedback-comment-input", classes="feedback-input")

        # Category selection
        yield ThemedText("Category:", variant="normal")
        yield Input(placeholder="e.g., UI, Performance, Features", id="feedback-category-input")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle star rating selection."""
        button_id = event.button.id
        if button_id.startswith("star-"):
            star_index = int(button_id.split("-")[1])
            self._rating = star_index

            # Update star button styles
            for i in range(1, 6):
                star_btn = self.query_one(f"#star-{i}", Button)
                if i <= star_index:
                    star_btn.variant = "primary"
                else:
                    star_btn.variant = "default"

    def confirm(self) -> None:
        """Handle submit."""
        comment_input = self.query_one("#feedback-comment-input", Input)
        category_input = self.query_one("#feedback-category-input", Input)

        feedback_data = {
            "rating": self._rating,
            "comment": comment_input.value,
            "category": category_input.value,
        }

        if self._on_submit:
            self._on_submit(feedback_data)
