from __future__ import annotations

import logging
from dataclasses import dataclass
from time import time
from typing import Any

from py_claw.cli.runtime import RuntimeState
from py_claw.query import QueryRuntime
from py_claw.schemas.common import SDKUserMessage
from py_claw.ui.screens.repl import REPLScreen
from py_claw.ui.typeahead import CommandItem, Suggestion, SuggestionEngine, SuggestionType
from py_claw.utils.suggestions.command_suggestions import (
    get_best_command_match,
    is_command_input,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TuiRunResult:
    exit_code: int = 0


DEFAULT_PROMPT_HINT = "Type a prompt or /command"

_TOOL_DETAIL_KEYS = ("command", "file_path", "pattern", "path", "query", "url", "description")


def _format_tool_detail(output: object) -> str:
    """Build a short 'what ran / what it returned' line for the tool log."""
    tool_input = getattr(output, "tool_input", None) or {}
    detail = ""
    for key in _TOOL_DETAIL_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            detail = value.strip().replace("\n", " ")
            break
    response = (getattr(output, "tool_response", None) or "").strip()
    if len(response) > 120:
        response = response[:119] + "…"
    if len(detail) > 80:
        detail = detail[:79] + "…"
    if detail and response:
        return f"{detail} → {response}"
    return detail or response


def _prompt_suggestion_item(suggestion: str) -> Suggestion:
    return Suggestion(
        type=SuggestionType.PROMPT,
        id="prompt-suggestion",
        display_text=suggestion,
        description="next prompt suggestion",
        tag="prompt",
        metadata={"source": "prompt_suggestion", "created_at": int(time() * 1000)},
    )


def _build_command_items(state: RuntimeState) -> list[CommandItem]:
    registry = state.build_command_registry(settings_skills=None)
    commands = registry.slash_commands()
    command_items: list[CommandItem] = []
    for command in commands:
        name = str(command.get("name", "")).strip()
        if not name:
            continue
        command_items.append(CommandItem.from_dict(command))
    return command_items


def _format_prompt_hint(text: str, engine: SuggestionEngine) -> str:
    """Format the hint text shown below the prompt input."""
    if not text:
        return DEFAULT_PROMPT_HINT

    from py_claw.ui.typeahead import SuggestionType

    sug_type = engine.detect_type(text, len(text))
    if sug_type == SuggestionType.SHELL_HISTORY:
        return "shell history — ↑↓ to navigate"
    if sug_type == SuggestionType.PATH:
        return "path — Tab to complete"
    if sug_type == SuggestionType.MID_INPUT_SLASH:
        return "mid-input /command — Tab to complete"
    if not is_command_input(text):
        return DEFAULT_PROMPT_HINT

    from py_claw.utils.suggestions.command_suggestions import generate_command_suggestions

    commands = engine._command_items  # noqa: SLF001 — engine internal access
    suggestions = generate_command_suggestions(text, commands)
    if not suggestions:
        return f"No slash commands match {text!r}"

    best = suggestions[0]
    metadata = best.metadata if isinstance(best.metadata, dict) else {}
    name = str(metadata.get("name") or best.display_text.strip())
    description = str(metadata.get("description") or best.description or "").strip()
    argument_hint = str(metadata.get("argumentHint") or "").strip()

    best_match = get_best_command_match(text[1:].strip(), commands)
    suffix = f" (+{best_match[0]})" if best_match and best_match[0] else ""

    parts = [name + suffix]
    if argument_hint:
        parts.append(argument_hint)
    if description:
        parts.append(f"— {description}")

    extra = []
    for suggestion in suggestions[1:4]:
        extra_name = suggestion.display_text.strip()
        extra.append(extra_name)
    if extra:
        parts.append("| next: " + ", ".join(extra))

    return " ".join(part for part in parts if part)


def run_textual_ui(state: RuntimeState, query_runtime: QueryRuntime, *, prompt: str | None = None) -> int:
    try:
        from textual import work
        from textual.app import App, ComposeResult
        from textual.worker import get_current_worker
    except ImportError as exc:  # pragma: no cover - exercised in manual smoke testing
        raise SystemExit("Textual is required for --tui mode. Install the 'textual' package first.") from exc

    # TUI renders incremental assistant text from partial stream events.
    state.include_partial_messages = True

    command_items = _build_command_items(state)
    engine = SuggestionEngine(command_items=command_items)

    class PyClawApp(App):
        TITLE = "py-claw"
        SUB_TITLE = "Terminal UI"
        # Textual injects a priority ctrl+p -> command_palette binding unless
        # this is disabled, which hijacks py-claw's Quick Open shortcut.
        ENABLE_COMMAND_PALETTE = False

        CSS = """
        Screen {
            layout: vertical;
        }
        /* No max-height cap here: capping the log (e.g. max-height: 60%)
           leaves the leftover space as a blank band *below* the footer, and
           shrinks the visible message area. As the last 1fr child it should
           absorb all remaining vertical space so the prompt+footer sit at
           the bottom edge. */
        #repl-message-log {
            height: 1fr;
        }
        /* Belt-and-suspenders: the canonical rules live in
           MessageList.DEFAULT_CSS (widgets/messages.py) — a plain Vertical
           defaults to height: 1fr, which squeezes overflowing content instead
           of letting #repl-message-log scroll. */
        #message-list-content {
            height: auto;
        }
        #repl-prompt-input {
            height: auto;
        }

        /* Narrow terminal adaptations (applied via add_class) */
        Screen.narrow #repl-message-log {
            height: 1fr;
        }
        Screen.narrow #repl-prompt-input {
            margin: 0;
        }
        Screen.narrow #repl-footer {
            display: block;
        }

        /* Short terminal adaptations (height < 20 rows) */
        Screen.short #repl-prompt-input {
            margin: 0;
        }
        Screen.short #repl-footer {
            display: block;
        }
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

        def compose(self) -> ComposeResult:
            yield REPLScreen(
                model=state.model,
                status="ready",
                prompt_hint=DEFAULT_PROMPT_HINT,
                on_submit=self._handle_submit,
                on_interrupt=self._handle_interrupt,
                on_input_change=self._handle_input_change,
                on_model_change=self._handle_model_change,
                suggestion_engine=engine,
                command_items=command_items,
            )

        def on_mount(self) -> None:
            self._pending_permission_dialog = None
            self._pending_prompt_dialog = None
            self._pending_elicitation_dialog = None
            self._current_worker = None
            state.permission_ask_callback = self._handle_permission_ask
            state.ask_user_callback = self._handle_prompt_ask
            self._register_elicitation_prompter()
            self._focus_prompt()
            self._update_narrow_mode()
            if prompt:
                self.call_after_refresh(self._submit_prompt, prompt)
            # Register speculation state callback
            self._register_speculation_callback()

        def on_resize(self, event: object) -> None:
            """Update narrow terminal class on resize."""
            self._update_narrow_mode()

        def _update_narrow_mode(self) -> None:
            """Apply or remove narrow/short terminal class based on dimensions."""
            width = self.size.width
            height = self.size.height
            is_narrow = width < 80
            is_short = height < 20
            if is_narrow:
                self.screen.add_class("narrow")
            else:
                self.screen.remove_class("narrow")
            if is_short:
                self.screen.add_class("short")
            else:
                self.screen.remove_class("short")

            compact_mode = "full"
            if is_narrow and is_short:
                compact_mode = "tight"
            elif is_short:
                compact_mode = "short"
            elif is_narrow:
                compact_mode = "narrow"
            self._screen().set_compact_mode(compact_mode)

            try:
                from py_claw.state.tui_state import set_narrow_terminal
                set_narrow_terminal(is_narrow)
            except Exception:
                pass

        def _screen(self) -> REPLScreen:
            return self.query_one(REPLScreen)

        def _focus_prompt(self) -> None:
            self._screen().focus_prompt()

        def _append_message(self, role: str, text: str) -> None:
            self._screen().append_message(role, text)

        def _update_last_message(self, text: str, append: bool = False) -> None:
            self._screen().update_last_message(text, append)

        def _append_tool_progress(self, tool_name: str, elapsed: float, detail: str = "") -> None:
            self._screen().append_tool_progress(tool_name, elapsed, detail)

        def _start_assistant_message(self) -> object:
            return self._screen().start_assistant_message()

        def _update_message_item(self, item: object, text: str) -> None:
            self._screen().update_message_item(item, text)

        def _set_status(self, text: str) -> None:
            self._screen().set_status(text)

        def _set_hint(self, text: str) -> None:
            self._screen().set_prompt_hint(text)

        def _set_suggestions(self, items: list[object]) -> None:
            self._screen().set_suggestion_items(items)

        def _set_prompt_suggestion(self, suggestion: str | None) -> None:
            items = [_prompt_suggestion_item(suggestion)] if suggestion else []
            self._set_suggestions(items)

        def _clear_prompt_suggestions(self) -> None:
            prompt = self._screen().get_prompt_value().strip()
            if prompt:
                return
            current = self._screen().get_suggestion_items()
            if any(getattr(item, "type", None) == SuggestionType.PROMPT for item in current):
                self._set_suggestions([])

        def _submit_prompt(self, text: str) -> None:
            self._screen().set_prompt_value(text)
            self._handle_submit(text)

        def _handle_prompt_ask(self, arguments: Any) -> tuple[str, dict[str, Any] | None]:
            import threading
            result_box: list[tuple[str, dict[str, Any] | None]] = []
            event = threading.Event()
            
            def handle_accept(answers: dict[str, str], annotations: dict) -> None:
                result_box.append(("accept", {"answers": answers, "annotations": annotations}))
                self._screen()._unregister_overlay("prompt-dialog")
                dialog.remove()
                event.set()
                
            def handle_decline() -> None:
                result_box.append(("decline", None))
                self._screen()._unregister_overlay("prompt-dialog")
                dialog.remove()
                event.set()

            from py_claw.ui.dialogs.prompt import PromptDialog
            
            dialog = PromptDialog(
                arguments=arguments,
                on_accept=handle_accept,
                on_decline=handle_decline,
                id="overlay-prompt"
            )
            self._pending_prompt_dialog = dialog
            
            def mount_dialog() -> None:
                self._screen()._register_overlay("prompt-dialog")
                self._screen().mount(dialog)
                try:
                    dialog.query_one("#btn-confirm").focus()
                except Exception:
                    dialog.focus()

            self.call_from_thread(mount_dialog)
            event.wait()
            self._pending_prompt_dialog = None
            return result_box[0]

        def _handle_permission_ask(self, tool_use_id: str, tool_name: str, tool_input: dict[str, Any], content: str | None) -> tuple[str, dict[str, Any] | None, str | None]:
            import threading

            result_box: list[tuple[str, dict[str, Any] | None, str | None]] = []
            event = threading.Event()

            def resolve(result: tuple[str, dict[str, Any] | None, str | None]) -> None:
                if not result_box:
                    result_box.append(result)
                self._screen()._unregister_overlay("permission-dialog")
                try:
                    dialog.remove()
                except Exception:
                    pass
                event.set()

            def handle_allow() -> None:
                resolve(("allow", None, None))

            def handle_always_allow() -> None:
                # Remember this tool for the rest of the session so later
                # calls skip the dialog.
                state.session_allowed_tools.add(tool_name)
                resolve(("allow", None, None))

            def handle_deny() -> None:
                resolve(("deny", None, "User denied permission"))

            from py_claw.ui.dialogs.permission import PermissionDialog

            dialog = PermissionDialog(
                tool_name=tool_name,
                message=content or f"{tool_name} requires permission",
                params=tool_input,
                on_allow=handle_allow,
                on_always_allow=handle_always_allow,
                on_deny=handle_deny,
                id="overlay-permission",
            )
            self._pending_permission_dialog = dialog

            def mount_dialog() -> None:
                self._screen()._register_overlay("permission-dialog")
                self._screen().mount(dialog)
                try:
                    dialog.query_one("#btn-confirm").focus()
                except Exception:
                    dialog.focus()

            self.call_from_thread(mount_dialog)
            event.wait()
            self._pending_permission_dialog = None
            return result_box[0]

        def _register_elicitation_prompter(self) -> None:
            """Register the TUI as the UI for MCP server elicitations."""
            try:
                from py_claw.services.mcp_auth.elicitation import set_elicitation_ui_prompter

                set_elicitation_ui_prompter(self._handle_elicitation_ask)
            except Exception:
                logger.debug("Failed to register elicitation UI prompter", exc_info=True)

        def _handle_elicitation_ask(
            self,
            server_name: str,
            params: dict[str, Any],
            event: Any,
            timeout: float | None,
        ) -> dict[str, Any] | None:
            """Blocking UI prompter for MCP elicitation requests.

            Runs on a worker thread (ElicitationHandler dispatches it via
            asyncio.to_thread) while the Textual loop keeps running. Mounts
            a minimal dialog on the UI thread and blocks until the user
            answers — the dialog callbacks push the answer back into the
            shared ElicitationRequestEvent via event.resolve(). The server's
            'complete' notification (url mode) resolves the same event
            out-of-band. Returns None if the dialog could not be shown.
            """
            from py_claw.ui.dialogs.elicitation import ElicitationDialog

            def resolve_and_close(result: dict[str, Any]) -> None:
                try:
                    event.resolve(result)
                except Exception:
                    pass
                try:
                    self._screen()._unregister_overlay("elicitation-dialog")
                except Exception:
                    pass
                try:
                    dialog.remove()
                except Exception:
                    pass

            dialog = ElicitationDialog(
                server_name=server_name,
                message=str(params.get("message") or ""),
                mode=str(params.get("mode") or "form"),
                url=params.get("url") if isinstance(params.get("url"), str) else None,
                requested_schema=params.get("requestedSchema")
                if isinstance(params.get("requestedSchema"), dict)
                else None,
                on_accept=lambda content: resolve_and_close(
                    {"action": "accept", "content": content}
                ),
                on_decline=lambda: resolve_and_close({"action": "decline"}),
                on_cancel=lambda: resolve_and_close({"action": "cancel"}),
                id="overlay-elicitation",
            )
            self._pending_elicitation_dialog = dialog

            def mount_dialog() -> None:
                self._screen()._register_overlay("elicitation-dialog")
                self._screen().mount(dialog)
                try:
                    dialog.query_one("#btn-confirm").focus()
                except Exception:
                    dialog.focus()

            try:
                self.call_from_thread(mount_dialog)
            except RuntimeError:
                # App is stopped/stopping: cannot present the dialog. The
                # handler degrades to a cancel so the MCP call never hangs.
                self._pending_elicitation_dialog = None
                return None

            result = event.wait_for_result(timeout)
            self._pending_elicitation_dialog = None
            if result is not None:
                # The answer may have arrived out-of-band (e.g. the server's
                # 'complete' notification) without the dialog's own buttons
                # closing it — make sure the dialog is gone either way.
                def close_if_mounted() -> None:
                    try:
                        self._screen()._unregister_overlay("elicitation-dialog")
                    except Exception:
                        pass
                    try:
                        if dialog.is_mounted:
                            dialog.remove()
                    except Exception:
                        pass

                try:
                    self.call_from_thread(close_if_mounted)
                except RuntimeError:
                    pass
            return result

        def _handle_input_change(self, text: str) -> None:
            self._set_hint(_format_prompt_hint(text, engine))
            if text.strip():
                self._clear_prompt_suggestions()
            # Compute suggestions via unified engine and update list
            items = engine.get_suggestions(text, len(text))
            self._set_suggestions(items)

        @work(thread=True)
        def _run_prompt(self, text: str) -> None:
            worker = get_current_worker()
            if worker.is_cancelled:
                return

            message = SDKUserMessage(type="user", message={"role": "user", "content": text}, parent_tool_use_id=None)
            try:
                outputs = query_runtime.handle_user_message(message)
            except Exception as exc:
                self.call_from_thread(self._append_message, "system", f"error: {exc}")
                self.call_from_thread(self._set_status, "failed")
                self.call_from_thread(self._focus_prompt)
                return

            assistant_item = None
            for output in outputs:
                if worker.is_cancelled:
                    return
                output_type = getattr(output, "type", None)
                if output_type == "system" and getattr(output, "subtype", None) == "session_state_changed":
                    self.call_from_thread(self._set_status, str(output.state))
                    continue
                if output_type == "stream_event":
                    event = getattr(output, "event", None)
                    if isinstance(event, dict):
                        event_type = event.get("type")
                        if event_type == "stream_request_start":
                            assistant_item = self.call_from_thread(self._start_assistant_message)
                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                # Partial messages carry the full accumulated
                                # text so far — replace, don't append.
                                accumulated = delta.get("text", "")
                                if accumulated and assistant_item is not None:
                                    self.call_from_thread(self._update_message_item, assistant_item, accumulated)
                    continue
                if output_type == "tool_progress":
                    detail = _format_tool_detail(output)
                    self.call_from_thread(
                        self._append_tool_progress,
                        output.tool_name,
                        output.elapsed_time_seconds,
                        detail,
                    )
                    # Text after a tool result belongs to a new assistant message.
                    assistant_item = None
                    continue
                if output_type == "prompt_suggestion":
                    self.call_from_thread(self._set_prompt_suggestion, str(output.suggestion))
                    continue
                if output_type == "result":
                    payload = output.model_dump(by_alias=True, exclude_none=True)
                    if payload.get("subtype") == "error_during_execution" and payload.get("errors"):
                        self.call_from_thread(self._append_message, "system", f"error: {payload['errors'][0]}")
                    else:
                        result_text = payload.get("result")
                        if result_text:
                            if assistant_item is not None:
                                self.call_from_thread(self._update_message_item, assistant_item, str(result_text))
                            else:
                                self.call_from_thread(self._append_message, "assistant", str(result_text))
                    assistant_item = None

            state.interrupt_event.clear()
            self.call_from_thread(self._set_status, "idle")
            self.call_from_thread(self._set_hint, DEFAULT_PROMPT_HINT)
            self.call_from_thread(self._focus_prompt)

        def _handle_submit(self, text: str) -> None:
            value = text.strip()
            if not value:
                return
            self._set_suggestions([])
            self._set_status("running")
            self._append_message("user", value)
            self._current_worker = self._run_prompt(value)

        def _handle_interrupt(self) -> None:
            # Actually cancel the in-flight turn, not just the status text.
            try:
                query_runtime.interrupt()
            except Exception:
                pass
            worker = getattr(self, "_current_worker", None)
            if worker is not None:
                try:
                    worker.cancel()
                except Exception:
                    pass
                self._current_worker = None
            # Unblock any worker thread waiting on a blocking dialog; for
            # permission prompts Esc has always meant "deny".
            for pending in (
                getattr(self, "_pending_permission_dialog", None),
                getattr(self, "_pending_prompt_dialog", None),
                getattr(self, "_pending_elicitation_dialog", None),
            ):
                if pending is not None:
                    try:
                        if pending.is_mounted:
                            pending.deny()
                        else:
                            pending.deny()
                    except Exception:
                        pass
            self._set_status("interrupted")
            self._set_hint("Cancelled current prompt")

        def _handle_model_change(self, model: str) -> None:
            """Handle model change from model picker."""
            self._set_hint(f"Model: {model}")

        def _register_speculation_callback(self) -> None:
            """Register speculation state change callback with SpeculationService."""
            try:
                from py_claw.services.speculation import get_speculation_service
                service = get_speculation_service()

                def on_state_change(spec_state: Any) -> None:
                    status = spec_state.status
                    boundary = ""
                    if spec_state.boundary is not None:
                        boundary = spec_state.boundary.get("type", "") if hasattr(spec_state.boundary, "get") else str(spec_state.boundary)
                    tool_count = spec_state.tool_use_count
                    self.call_from_thread(
                        self._screen().set_speculation_state,
                        status,
                        boundary,
                        tool_count,
                    )

                service.set_state_callback(on_state_change)
            except Exception:
                pass  # Speculation not available

        def action_quit(self) -> None:
            if state.active_worktree_session:
                from py_claw.ui.dialogs.worktree import WorktreeExitDialog
                
                wt = state.active_worktree_session
                dialog: WorktreeExitDialog | None = None
                
                def on_keep() -> None:
                    if dialog:
                        dialog.remove()
                    self.exit()
                    
                def on_remove() -> None:
                    if dialog:
                        dialog.remove()
                    try:
                        from py_claw.services.worktree import remove_agent_worktree
                        remove_agent_worktree(
                            worktree_path=wt.worktree_path,
                            worktree_branch=wt.worktree_branch,
                            git_root=wt.repo_root or wt.original_cwd,
                            hook_based=(wt.backend == "hook"),
                        )
                    except Exception:
                        pass
                    self.exit()

                def on_cancel() -> None:
                    if dialog:
                        dialog.remove()
                    self._screen()._unregister_overlay("exit-dialog")
                    self._screen().focus_prompt()
                
                dialog = WorktreeExitDialog(
                    worktree_path=wt.worktree_path,
                    worktree_branch=wt.worktree_branch or "unknown",
                    has_changes=False,
                    commit_count=0,
                    tmux_session_name=None,
                    on_keep=on_keep,
                    on_remove=on_remove,
                    on_cancel=on_cancel,
                    id="overlay-exit"
                )
                self._screen()._register_overlay("exit-dialog")
                self._screen().mount(dialog)
                dialog.focus()
            else:
                self.exit()

        def action_new_session(self) -> None:
            screen = self._screen()
            try:
                query_runtime.clear_session()
            except Exception:
                pass
            state.session_allowed_tools.clear()
            screen.clear_log()
            screen.set_status("idle")
            screen.set_prompt_hint(DEFAULT_PROMPT_HINT)
            screen.focus_prompt()

        def action_clear_log(self) -> None:
            self._screen().clear_log()

        def action_show_history_search(self) -> None:
            self._screen().action_show_history_search()

        def action_show_quick_open(self) -> None:
            self._screen().action_show_quick_open()

        def action_show_model_picker(self) -> None:
            self._screen().action_show_model_picker()

        def action_show_tasks_panel(self) -> None:
            self._screen().action_show_tasks_panel()

    PyClawApp().run()
    # Clear the registered UI prompter so any later non-TUI session in this
    # process degrades elicitations to cancel instead of touching a stopped
    # Textual app.
    try:
        from py_claw.services.mcp_auth.elicitation import set_elicitation_ui_prompter

        set_elicitation_ui_prompter(None)
    except Exception:
        pass
    return 0
