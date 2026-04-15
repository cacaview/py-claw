"""REPL Screen — Main REPL interface.

Re-implements ClaudeCode-main/src/screens/REPL.tsx as a standalone screen.
Used exclusively through PyClawApp (textual_app.py) — no standalone shell.
Features:
- Role-based message styling (user/assistant/system/tool)
- Status line with model info and token count
- Keyboard shortcuts (Ctrl+C, Ctrl+G, Ctrl+L, Ctrl+R, Ctrl+P, Ctrl+M, Ctrl+T)
- Tool progress indicators
- Session state display
- Contextual footer with mode hints and help menu
- Overlay dialogs: Help, History Search, Quick Open, Model Picker, Tasks
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Header, RichLog

from py_claw.ui.typeahead import CommandItem
from py_claw.ui.widgets.prompt_input import PromptInput, PromptMode
from py_claw.ui.widgets.prompt_footer import PromptFooter
from py_claw.ui.widgets.status_line import StatusLine


class REPLScreen(Vertical):
    """Main REPL screen component.

    This is a composite screen that includes:
    - Header with app title
    - Status line (model, tokens, shortcuts)
    - Message log with role-based styling
    - Prompt input with hints
    - Contextual footer with mode/loading hints and help menu
    - Overlay dialogs (Help, History Search, Quick Open, Model Picker, Tasks)
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+g", "new_session", "New"),
        ("ctrl+l", "clear_log", "Clear"),
        ("ctrl+r", "show_history_search", "History"),
        ("ctrl+p", "show_quick_open", "Quick Open"),
        ("ctrl+m", "show_model_picker", "Model"),
        ("ctrl+t", "show_tasks_panel", "Tasks"),
    ]

    def __init__(
        self,
        model: str | None = None,
        status: str = "idle",
        shortcuts: str | None = None,
        prompt_hint: str = "Type a prompt or /command",
        on_submit: Callable[[str], None] | None = None,
        on_interrupt: Callable[[], None] | None = None,
        on_input_change: Callable[[str], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_model_change: Callable[[str], None] | None = None,
        suggestion_engine: Any = None,
        command_items: list[CommandItem] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._model = model or "claude-sonnet-4-20250514"
        self._status = status
        self._shortcuts = shortcuts or "?: help · Tab: complete"
        self._prompt_hint = prompt_hint
        self._on_submit = on_submit
        self._on_interrupt = on_interrupt
        self._on_input_change = on_input_change
        self._on_clear = on_clear
        self._on_model_change = on_model_change
        self._engine = suggestion_engine
        self._command_items = list(command_items) if command_items else []
        self._is_loading = False
        self._current_mode = "normal"
        # Overlay tracking
        self._active_overlay: str | None = None
        self._overlay_ids: set[str] = set()
        super().__init__(id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Compose the REPL screen layout."""
        yield Header(show_clock=False)

        yield StatusLine(
            status=self._status,
            model=self._model,
            shortcuts=self._shortcuts,
            id="repl-status",
        )

        yield RichLog(
            id="repl-message-log",
            highlight=False,
            markup=True,
            auto_scroll=True,
        )

        yield PromptInput(
            model=self._model,
            prompt_mode=PromptMode.NORMAL,
            hint=self._prompt_hint,
            placeholder="Type a prompt and press Enter",
            on_submit=self._on_submit,
            on_interrupt=self._on_interrupt,
            on_change=self._on_input_change,
            suggestion_engine=self._engine,
            id="repl-prompt-input",
        )

        # Contextual footer: mode indicator + contextual hints + help shortcut
        yield PromptFooter(
            shortcuts="?: help · Ctrl+R: history · Ctrl+P: files · Ctrl+M: model · Ctrl+T: tasks",
            id="repl-footer",
        )

    # ── overlay management ─────────────────────────────────────────────────────

    def _register_overlay(self, overlay_id: str) -> None:
        """Register that an overlay is now active."""
        self._active_overlay = overlay_id
        self._overlay_ids.add(overlay_id)
        self._update_footer_overlay_state()

    def _unregister_overlay(self, overlay_id: str) -> None:
        """Unregister an overlay. Returns True if this was the active overlay."""
        self._overlay_ids.discard(overlay_id)
        if self._active_overlay == overlay_id:
            self._active_overlay = next(iter(self._overlay_ids), None)
        self._update_footer_overlay_state()

    def _update_footer_overlay_state(self) -> None:
        """Update footer overlay state display."""
        footer = self.query_one("#repl-footer", PromptFooter)
        if self._active_overlay:
            footer.close_help()

    @property
    def _is_overlay_active(self) -> bool:
        """True if any overlay is currently displayed."""
        return self._active_overlay is not None

    # ── overlay actions ───────────────────────────────────────────────────────

    def action_show_history_search(self) -> None:
        """Show the shell history search overlay."""
        if self._is_overlay_active:
            return
        self._show_history_search()

    def action_show_quick_open(self) -> None:
        """Show the quick open (file search) overlay."""
        if self._is_overlay_active:
            return
        self._show_quick_open()

    def action_show_model_picker(self) -> None:
        """Show the model picker overlay."""
        if self._is_overlay_active:
            return
        self._show_model_picker()

    def action_show_tasks_panel(self) -> None:
        """Show the tasks panel overlay."""
        if self._is_overlay_active:
            return
        self._show_tasks_panel()

    # ── overlay show methods ───────────────────────────────────────────────────

    def _show_history_search(self) -> None:
        """Show the shell history search dialog."""
        from py_claw.ui.dialogs.history_search import HistorySearchDialog

        overlay_id = "history-search"

        def on_select(command: str) -> None:
            self.set_prompt_value(command)

        def on_close() -> None:
            self._unregister_overlay(overlay_id)

        dialog = HistorySearchDialog(
            on_select=on_select,
            on_close=on_close,
            id="overlay-history-search",
        )
        self._register_overlay(overlay_id)
        self.app.mount(dialog)
        dialog.focus()

    def _show_quick_open(self) -> None:
        """Show the quick open (file search) dialog."""
        from py_claw.ui.dialogs.quick_open import QuickOpenDialog

        overlay_id = "quick-open"

        def on_select(path: str) -> None:
            # Insert file path into prompt
            self.set_prompt_value(path)

        def on_close() -> None:
            self._unregister_overlay(overlay_id)

        dialog = QuickOpenDialog(
            root_dir=os.getcwd(),
            on_select=on_select,
            on_close=on_close,
            id="overlay-quick-open",
        )
        self._register_overlay(overlay_id)
        self.app.mount(dialog)
        dialog.focus()

    def _show_model_picker(self) -> None:
        """Show the model picker dialog."""
        from py_claw.ui.dialogs.model_picker import ModelPickerDialog

        overlay_id = "model-picker"

        def on_select(model_id: str) -> None:
            self.set_model(model_id)
            if self._on_model_change:
                self._on_model_change(model_id)

        def on_close() -> None:
            self._unregister_overlay(overlay_id)

        dialog = ModelPickerDialog(
            current_model=self._model,
            on_select=on_select,
            on_close=on_close,
            id="overlay-model-picker",
        )
        self._register_overlay(overlay_id)
        self.app.mount(dialog)
        dialog.focus()

    def _show_tasks_panel(self) -> None:
        """Show the tasks panel."""
        from py_claw.ui.dialogs.tasks_panel import TasksPanel, TaskEntry

        overlay_id = "tasks-panel"

        # Gather sample tasks (placeholder — real implementation would query task system)
        tasks: list[TaskEntry] = []

        def on_close() -> None:
            self._unregister_overlay(overlay_id)

        dialog = TasksPanel(
            tasks=tasks,
            on_close=on_close,
            id="overlay-tasks-panel",
        )
        self._register_overlay(overlay_id)
        self.app.mount(dialog)
        dialog.focus()

    # ── message handling ───────────────────────────────────────────────────────

    def on_message(self, event: object) -> None:
        """Handle messages from child widgets and overlays."""
        if hasattr(event, '__class__'):
            cls_name = event.__class__.__qualname__

            # Help menu toggle from PromptInput
            if cls_name == 'PromptInput.HelpToggled':
                event.stop()
                self._show_help_menu()
                return

            # Vim mode changed
            if cls_name == 'PromptInput.VimModeChanged':
                event.stop()
                # Update footer to show new vim mode
                from py_claw.state.tui_state import update_tui_vim_mode
                mode = event.mode.value  # type: ignore[attr-defined]
                update_tui_vim_mode(mode)
                return

            # Suggestion index changed (arrow navigation)
            if cls_name == 'PromptInput.SuggestionIndexChanged':
                event.stop()
                footer = self.query_one("#repl-footer", PromptFooter)
                footer.selected_index = event.index  # type: ignore[attr-defined]
                return

            # History search result
            if cls_name == 'HistorySearchDialog.Selected':
                event.stop()
                cmd = event.command  # type: ignore[attr-defined]
                self.set_prompt_value(cmd)
                return

            # Model picker result
            if cls_name == 'ModelPickerDialog.Selected':
                event.stop()
                model_id = event.model_id  # type: ignore[attr-defined]
                self.set_model(model_id)
                if self._on_model_change:
                    self._on_model_change(model_id)
                return

            # Quick open result
            if cls_name == 'QuickOpenDialog.Selected':
                event.stop()
                path = event.path  # type: ignore[attr-defined]
                self.set_prompt_value(path)
                return

            # History search cancelled
            if cls_name == 'HistorySearchDialog.Cancelled':
                event.stop()
                return

            # Model picker cancelled
            if cls_name == 'ModelPickerDialog.Cancelled':
                event.stop()
                return

            # Quick open cancelled
            if cls_name == 'QuickOpenDialog.Cancelled':
                event.stop()
                return

            # Tasks panel cancelled
            if cls_name == 'TasksPanel.Cancelled':
                event.stop()
                return

        super().on_message(event)

    # ── help menu ──────────────────────────────────────────────────────────────

    def _show_help_menu(self) -> None:
        """Show the help menu dialog."""
        from py_claw.ui.dialogs.help import HelpMenuDialog

        overlay_id = "help-menu"

        def on_close() -> None:
            self._unregister_overlay(overlay_id)

        dialog = HelpMenuDialog(
            commands=self._command_items,
            shortcuts=None,  # Use keybindings service defaults
            on_close=on_close,
            id="overlay-help-menu",
        )
        self._register_overlay(overlay_id)
        self.app.mount(dialog)
        dialog.focus()

    # ── public API ─────────────────────────────────────────────────────────────

    def append_message(self, role: str, content: str, timestamp: str | None = None) -> None:
        """Append a message to the log.

        Args:
            role: Message role (user, assistant, system, tool)
            content: Message content
            timestamp: Optional timestamp string
        """
        log = self.query_one("#repl-message-log", RichLog)

        role_colors = {
            "user": "#3b82f6",
            "assistant": "#22c55e",
            "system": "#f59e0b",
            "tool": "#06b6d4",
        }
        color = role_colors.get(role.lower(), "#ffffff")

        prefix = f"[{color}]{role.upper()}[/{color}]"
        if timestamp:
            prefix += f" [dim]{timestamp}[/dim]"

        log.write(f"{prefix}: {content}")

    def append_tool_progress(self, tool_name: str, elapsed: float) -> None:
        """Append tool progress message."""
        log = self.query_one("#repl-message-log", RichLog)
        log.write(f"[dim]└─ Tool '{tool_name}' completed in {elapsed:.2f}s[/dim]")

    def append_error(self, error: str) -> None:
        """Append error message."""
        log = self.query_one("#repl-message-log", RichLog)
        log.write(f"[red]Error: {error}[/red]")

    def set_status(self, status: str) -> None:
        """Update the status line and footer."""
        self._status = status
        status_line = self.query_one("#repl-status", StatusLine)
        status_line.set_status(status)
        footer = self.query_one("#repl-footer", PromptFooter)
        footer.set_status(status)
        footer.set_loading(status == "running")

    # ── status pills ─────────────────────────────────────────────────────

    def set_bridge_status(self, label: str, color: str) -> None:
        """Set bridge status pill in the footer."""
        footer = self.query_one("#repl-footer", PromptFooter)
        footer.set_bridge_status(label, color)

    def set_agent_count(self, count: int) -> None:
        """Set agent count pill in the footer."""
        footer = self.query_one("#repl-footer", PromptFooter)
        footer.set_agent_count(count)

    def set_task_count(self, count: int) -> None:
        """Set task count pill in the footer."""
        footer = self.query_one("#repl-footer", PromptFooter)
        footer.set_task_count(count)

    def set_team_count(self, count: int) -> None:
        """Set team count pill in the footer."""
        footer = self.query_one("#repl-footer", PromptFooter)
        footer.set_team_count(count)

    def set_model(self, model: str) -> None:
        """Update the model name."""
        self._model = model
        status_line = self.query_one("#repl-status", StatusLine)
        status_line.set_model(model)
        prompt = self.query_one("#repl-prompt-input", PromptInput)
        prompt._model = model

    def set_tokens(self, tokens: str) -> None:
        """Update the token count."""
        status_line = self.query_one("#repl-status", StatusLine)
        status_line.set_tokens(tokens)

    def set_prompt_hint(self, hint: str) -> None:
        """Update the prompt hint area."""
        self._prompt_hint = hint
        self.query_one("#repl-prompt-input", PromptInput).hint = hint

    def set_suggestion_items(self, items: list[object]) -> None:
        """Update the prompt input suggestion items and footer."""
        prompt = self.query_one("#repl-prompt-input", PromptInput)
        prompt.set_suggestion_items(items)
        footer = self.query_one("#repl-footer", PromptFooter)
        # Sync selected_index from prompt to footer
        footer.selected_index = prompt.selected_index
        footer.set_suggestions(items, prompt.selected_index)
        # Publish to global store
        try:
            from py_claw.state.tui_state import update_tui_suggestions
            update_tui_suggestions(has_suggestions=bool(items), count=len(items))
        except Exception:
            pass

    def set_mode(self, mode: str) -> None:
        """Update the current mode (normal/plan/auto/bypass)."""
        self._current_mode = mode
        prompt = self.query_one("#repl-prompt-input", PromptInput)
        prompt.prompt_mode = PromptMode(mode)
        footer = self.query_one("#repl-footer", PromptFooter)
        footer.set_mode(mode)
        # Publish to global store
        try:
            from py_claw.state.tui_state import update_tui_prompt_mode
            update_tui_prompt_mode(mode)
        except Exception:
            pass

    def clear_log(self) -> None:
        """Clear the message log."""
        log = self.query_one("#repl-message-log", RichLog)
        log.clear()

    def focus_prompt(self) -> None:
        """Focus the prompt input."""
        self.query_one("#repl-prompt-input", PromptInput).focus_input()

    def set_prompt_value(self, value: str) -> None:
        """Programmatically update the prompt value."""
        self.query_one("#repl-prompt-input", PromptInput).set_value(value)

    def get_prompt_value(self) -> str:
        """Return the current prompt input value."""
        return self.query_one("#repl-prompt-input", PromptInput).get_value()


