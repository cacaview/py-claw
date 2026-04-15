"""Doctor screen — Diagnostic display.

Re-implements ClaudeCode-main/src/screens/Doctor.tsx
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.app import App
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Footer, Header, Static

from py_claw.ui.widgets.dialog import Dialog
from py_claw.ui.widgets.divider import Divider
from py_claw.ui.widgets.pane import Pane
from py_claw.ui.widgets.progress_bar import ProgressBar
from py_claw.ui.widgets.status_icon import StatusIcon, StatusType
from py_claw.ui.widgets.themed_text import ThemedText
from py_claw.ui.theme import get_theme


class DoctorScreen(ScrollableContainer):
    """Doctor diagnostic screen.

    Displays system diagnostics:
    - MCP server status
    - Settings paths
    - Configuration status
    """

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the doctor screen layout."""
        theme = get_theme()

        yield Header()

        with Vertical(id="doctor-content"):
            yield Static("System Diagnostics", id="doctor-title")

            yield Divider()

            # MCP Servers section
            yield ThemedText("MCP Servers", variant="normal")
            yield StatusIcon(StatusType.INFO, "Checking MCP configuration...")

            yield Divider()

            # Settings section
            yield ThemedText("Settings", variant="normal")
            yield StatusIcon(StatusType.PENDING, "Loading settings...")

            yield Divider()

            # Config paths
            yield ThemedText("Configuration Paths", variant="muted")
            yield Static("~/.claude/settings.json", id="path-settings")
            yield Static("~/.claude/agents/", id="path-agents")

            yield Divider()

            # Progress indicators
            yield ProgressBar(0.5, "Overall health")

        yield Footer()

    def add_diagnostic(self, category: str, item: str, status: StatusType, detail: str | None = None) -> None:
        """Add a diagnostic item to the list."""
        content = self.query_one("#doctor-content", Vertical)

        icon = StatusIcon(status=status, label=item)
        content.mount(icon)

        if detail:
            content.mount(ThemedText(detail, variant="dim"))


class DoctorApp(App):
    """Standalone Doctor application for testing."""

    CSS = """
    Screen {
        background: $background;
    }
    #doctor-content {
        height: 100%;
        padding: 1;
    }
    #doctor-title {
        text-style: bold;
        color: $text;
    }
    """

    BINDINGS = [("escape", "quit", "Quit"), ("ctrl+c", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        """Compose the app."""
        yield DoctorScreen()

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()
