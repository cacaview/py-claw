"""AgentDialog — Agent management dialogs.

Re-implements ClaudeCode-main/src/components/agents/AgentsMenu.tsx
and ClaudeCode-main/src/components/agents/AgentEditor.tsx
"""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.fuzzy_picker import FuzzyPicker
from py_claw.ui.widgets.list_item import ListItem
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.tabs import Tabs
from py_claw.ui.widgets.themed_text import ThemedText
from py_claw.ui.theme import get_theme


class AgentsMenu(Vertical):
    """Agent management menu.

    Shows agent list, source grouping, and detail view.
    """

    def __init__(
        self,
        agents: list[dict],  # list of agent definition dicts
        on_select: Callable[[str], None] | None = None,
        on_create: Callable[[], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._agents = agents
        self._on_select = on_select
        self._on_create = on_create
        self._on_delete = on_delete
        self._selected_agent_id: str | None = None
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the agents menu."""
        theme = get_theme()

        yield ThemedText("Agents", variant="normal")

        # Agent list
        with Vertical(id="agent-list"):
            for agent in self._agents:
                agent_id = agent.get("id", "")
                agent_name = agent.get("name", "Unnamed")
                agent_source = agent.get("source", "unknown")
                yield ListItem(
                    item_id=agent_id,
                    label=agent_name,
                    description=f"Source: {agent_source}",
                    icon="🤖",
                )

        # Action buttons
        with Horizontal(id="agent-actions"):
            yield Button("Create New", id="btn-create", variant="primary")
            yield Button("Edit Selected", id="btn-edit", variant="default")
            yield Button("Delete Selected", id="btn-delete", variant="error")

    def on_list_item_selected(self, event: ListItem.Selected) -> None:
        """Handle agent selection."""
        self._selected_agent_id = event.item_id
        if self._on_select:
            self._on_select(event.item_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "btn-create" and self._on_create:
            self._on_create()
        elif button_id == "btn-edit" and self._selected_agent_id:
            # TODO: Open editor for selected agent
            pass
        elif button_id == "btn-delete" and self._selected_agent_id:
            if self._on_delete:
                self._on_delete(self._selected_agent_id)


class AgentEditor(Dialog):
    """Agent editor dialog.

    Allows creating/editing agent definitions.
    """

    def __init__(
        self,
        agent: dict | None = None,  # None for create, dict for edit
        on_save: Callable[[dict], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._agent = agent
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._is_edit = agent is not None
        title = "Edit Agent" if self._is_edit else "Create Agent"
        super().__init__(
            title=title,
            confirm_label="Save",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the agent editor form."""
        theme = get_theme()

        # Agent name
        yield ThemedText("Name:", variant="normal")
        name_input = Input(
            value=self._agent.get("name", "") if self._agent else "",
            placeholder="Agent name",
            id="agent-name-input",
        )
        yield name_input

        # Agent description
        yield ThemedText("Description:", variant="normal")
        desc_input = Input(
            value=self._agent.get("description", "") if self._agent else "",
            placeholder="Agent description",
            id="agent-desc-input",
        )
        yield desc_input

        # Agent model
        yield ThemedText("Model:", variant="normal")
        model_input = Input(
            value=self._agent.get("model", "claude-sonnet-4-20250514") if self._agent else "",
            placeholder="claude-sonnet-4-20250514",
            id="agent-model-input",
        )
        yield model_input

        # System prompt
        yield ThemedText("System Prompt:", variant="normal")
        prompt_input = Input(
            value=self._agent.get("systemPrompt", "") if self._agent else "",
            placeholder="You are a helpful assistant...",
            id="agent-prompt-input",
        )
        yield prompt_input

    def confirm(self) -> None:
        """Handle save."""
        name_input = self.query_one("#agent-name-input", Input)
        desc_input = self.query_one("#agent-desc-input", Input)
        model_input = self.query_one("#agent-model-input", Input)
        prompt_input = self.query_one("#agent-prompt-input", Input)

        agent_data = {
            "name": name_input.value,
            "description": desc_input.value,
            "model": model_input.value,
            "systemPrompt": prompt_input.value,
        }

        if self._is_edit and self._agent:
            agent_data["id"] = self._agent.get("id")

        if self._on_save:
            self._on_save(agent_data)

    def cancel(self) -> None:
        """Handle cancel."""
        if self._on_cancel:
            self._on_cancel()


class AgentDeleteConfirm(Dialog):
    """Confirmation dialog for agent deletion."""

    def __init__(
        self,
        agent_name: str,
        on_confirm: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._agent_name = agent_name
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        super().__init__(
            title="Delete Agent",
            body=f"Are you sure you want to delete '{agent_name}'?",
            confirm_label="Delete",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def set_callbacks(
        self,
        on_confirm: Callable[[], None] | None = None,
        on_deny: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Set callbacks."""
        self._on_confirm = on_confirm
        self._on_deny = on_deny
        self._on_cancel = on_cancel

    def confirm(self) -> None:
        """Handle confirm delete."""
        self._exit_state = ExitState.CONFIRMED
        if self._on_confirm:
            self._on_confirm()

    def deny(self) -> None:
        """Handle cancel delete."""
        self._exit_state = ExitState.DENIED
        if self._on_deny:
            self._on_deny()
