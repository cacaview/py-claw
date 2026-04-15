"""SkillsDialog — Skills management dialog.

Re-implements skills viewing and management dialog.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Button, Input

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.fuzzy_picker import FuzzyPicker
from py_claw.ui.widgets.list_item import ListItem
from py_claw.ui.widgets.themed_text import ThemedText


class SkillsDialog(Dialog):
    """Skills management dialog.

    Shows available skills, allows enabling/disabling,
    and viewing skill details.
    """

    def __init__(
        self,
        skills: list[dict],  # list of {id, name, description, enabled, ...}
        on_toggle: Callable[[str, bool], None] | None = None,
        on_view: Callable[[str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._skills = skills
        self._on_toggle = on_toggle
        self._on_view = on_view
        self._on_cancel = on_cancel
        super().__init__(
            title="Skills",
            confirm_label="Done",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the skills dialog."""
        # Search filter
        yield Input(placeholder="Filter skills...", id="skill-filter-input")

        # Skills list
        with ScrollableContainer(id="skills-list"):
            with Vertical():
                for skill in self._skills:
                    skill_id = skill.get("id", "")
                    skill_name = skill.get("name", "Unnamed")
                    skill_desc = skill.get("description", "")
                    skill_enabled = skill.get("enabled", True)
                    icon = "✓" if skill_enabled else "○"
                    yield ListItem(
                        item_id=skill_id,
                        label=f"{icon} {skill_name}",
                        description=skill_desc,
                    )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle skill filtering."""
        query = event.value.lower()
        list_container = self.query_one("#skills-list", ScrollableContainer)

        for i, child in enumerate(list_container.children):
            if hasattr(child, "item_id"):
                # ListItem
                visible = query in child._label.lower() or query in (child._description or "").lower()
                child.display = visible if query else True


class SkillDetailDialog(Dialog):
    """Skill detail view dialog."""

    def __init__(
        self,
        skill: dict,
        on_close: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._skill = skill
        self._on_close = on_close
        super().__init__(
            title=f"Skill: {skill.get('name', 'Unknown')}",
            confirm_label="Close",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the skill detail view."""
        skill = self._skill

        yield ThemedText(f"ID: {skill.get('id', 'N/A')}", variant="muted")
        yield ThemedText(f"Name: {skill.get('name', 'N/A')}", variant="normal")
        yield ThemedText(f"Description: {skill.get('description', 'N/A')}", variant="normal")
        yield ThemedText(f"Enabled: {skill.get('enabled', True)}", variant="normal")

        if skill.get("command"):
            yield ThemedText(f"Command: {skill['command']}", variant="normal")

        if skill.get("args"):
            yield ThemedText(f"Args: {', '.join(skill['args'])}", variant="normal")
