"""MCPServerDialog — MCP server management dialog.

Re-implements ClaudeCode-main/src/components/agents/MCPServerDialog.tsx
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.fuzzy_picker import FuzzyPicker
from py_claw.ui.widgets.list_item import ListItem
from py_claw.ui.widgets.themed_text import ThemedText


class MCPServerDialog(Dialog):
    """MCP Server management dialog.

    Allows adding, removing, and configuring MCP servers.
    """

    def __init__(
        self,
        servers: list[dict],  # list of MCP server configs
        on_add: Callable[[dict], None] | None = None,
        on_remove: Callable[[str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._servers = servers
        self._on_add = on_add
        self._on_remove = on_remove
        self._on_cancel = on_cancel
        super().__init__(
            title="MCP Servers",
            confirm_label="Done",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the MCP server dialog."""
        # Server list
        yield ThemedText("Configured Servers:", variant="normal")

        with Vertical(id="mcp-server-list"):
            for server in self._servers:
                server_name = server.get("name", "Unnamed")
                server_command = server.get("command", "")
                yield ListItem(
                    item_id=server_name,
                    label=server_name,
                    description=server_command,
                    icon="🔌",
                )

        # Add server section
        yield ThemedText("Add Server:", variant="normal")

        yield Input(placeholder="Server name", id="mcp-name-input")
        yield Input(placeholder="Command (e.g., npx @anthropic/mcp-server)", id="mcp-command-input")
        yield Input(placeholder="Args (comma separated)", id="mcp-args-input")

        yield Button("Add Server", id="btn-add-server", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-add-server":
            name_input = self.query_one("#mcp-name-input", Input)
            command_input = self.query_one("#mcp-command-input", Input)
            args_input = self.query_one("#mcp-args-input", Input)

            server_config = {
                "name": name_input.value,
                "command": command_input.value,
                "args": [a.strip() for a in args_input.value.split(",") if a.strip()],
            }

            if self._on_add:
                self._on_add(server_config)


class MCPServerTestDialog(Dialog):
    """Dialog for testing MCP server connection."""

    def __init__(
        self,
        server_name: str,
        on_test: Callable[[], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._server_name = server_name
        self._on_test = on_test
        self._on_cancel = on_cancel
        super().__init__(
            title=f"Test: {server_name}",
            body="Click 'Test' to verify the MCP server connection.",
            confirm_label="Test",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def confirm(self) -> None:
        """Handle test."""
        if self._on_test:
            self._on_test()
