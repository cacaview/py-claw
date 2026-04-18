"""Speculation execution service.

Orchestrates speculation/pipelined suggestions: runs a forked agent in an
isolated overlay directory, enforces read-only constraints, and provides
accept/abort/cancel UI interactions.

Mirrors ClaudeCode-main/src/services/PromptSuggestion/speculation.ts.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from py_claw.state.app_state import SpeculationState
from py_claw.services.analytics.service import get_analytics_service
from py_claw.services.speculation.analytics import log_speculation
from py_claw.services.speculation.constants import (
    MAX_SPECULATION_MESSAGES,
    MAX_SPECULATION_TURNS,
)
from py_claw.services.speculation.overlay import (
    OverlayManager,
    create_overlay,
    remove_overlay,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from py_claw.fork.process import ForkedAgentProcess


# ---------------------------------------------------------------------------
# SpeculationResult
# ---------------------------------------------------------------------------


@dataclass
class SpeculationResult:
    """Result of an accepted speculation.

    Contains the messages to inject and metadata about the speculation run.
    """
    messages: list[dict[str, Any]]
    boundary: dict[str, Any] | None
    time_saved_ms: int
    is_complete: bool


# ---------------------------------------------------------------------------
# SpeculationService
# ---------------------------------------------------------------------------


class SpeculationService:
    """Manages the speculation lifecycle.

    Coordinates:
    - Starting/stopping the speculation forked subprocess
    - Overlay copy-on-write management
    - Accept/abort user actions
    - Pipelined suggestion generation
    - State publishing to AppState and UI

    Thread-safe: all public methods are thread-safe.
    """

    def __init__(
        self,
        get_cwd: Callable[[], str],
        get_session_id: Callable[[], str],
    ) -> None:
        self._get_cwd = get_cwd
        self._get_session_id = get_session_id
        self._process: Optional["ForkedAgentProcess"] = None
        self._overlay_manager: Optional[OverlayManager] = None
        self._abort_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._speculation_id: Optional[str] = None
        self._is_running = False
        self._is_pipelined = False
        self._lock = threading.Lock()

        # State change callback (set by UI layer)
        self._on_state_change: Callable[[SpeculationState], None] | None = None

    # ─── Properties ───────────────────────────────────────────────────────────

    @property
    def is_enabled(self) -> bool:
        """Check if speculation is enabled via feature gate and env."""
        import os

        user_type = os.environ.get("USER_TYPE", "")
        if user_type != "ant":
            return False

        from py_claw.services.analytics.service import get_feature_value

        return get_feature_value("tengu_speculation_enabled", False)

    @property
    def is_active(self) -> bool:
        """Check if speculation is currently running."""
        with self._lock:
            return self._is_running and self._speculation_id is not None

    @property
    def state(self) -> SpeculationState:
        """Return current speculation state for UI consumption."""
        from py_claw.state.app_state import SpeculationState

        with self._lock:
            if not self._speculation_id:
                return SpeculationState(status="idle")

            return SpeculationState(
                status="active" if self._is_running else "idle",
                id=self._speculation_id,
                is_pipelined=self._is_pipelined,
            )

    # ─── Public API ─────────────────────────────────────────────────────────

    def set_state_callback(
        self, callback: Callable[[SpeculationState], None] | None
    ) -> None:
        """Set the state change callback (called from UI layer)."""
        self._on_state_change = callback

    def start_speculation(
        self,
        suggestion_text: str,
        is_pipelined: bool = False,
    ) -> None:
        """Start a new speculation run.

        Fire-and-forget: starts in background thread without blocking.

        Args:
            suggestion_text: The suggested text/prompt to speculate on
            is_pipelined: Whether this is a pipelined (secondary) suggestion
        """
        if not self.is_enabled:
            logger.debug("[Speculation] Not enabled, skipping")
            return

        with self._lock:
            if self._is_running:
                self.abort()

            speculation_id = uuid.uuid4().hex[:8]
            self._speculation_id = speculation_id
            self._is_running = True
            self._is_pipelined = is_pipelined
            self._abort_event = threading.Event()

        overlay_path = create_overlay(speculation_id)
        main_cwd = self._get_cwd()

        self._overlay_manager = OverlayManager(
            overlay_path=overlay_path,
            main_cwd=main_cwd,
        )

        # Update state
        self._update_state(SpeculationState(
            status="active",
            id=speculation_id,
            start_time=int(time.time() * 1000),
            suggestion_length=len(suggestion_text),
            tool_use_count=0,
            is_pipelined=is_pipelined,
            overlay_path=str(overlay_path),
            messages=[],
            written_paths=[],
        ))

        # Start background thread
        self._poll_thread = threading.Thread(
            target=self._run_speculation,
            args=(suggestion_text, overlay_path, main_cwd),
            daemon=True,
            name=f"speculation-{speculation_id}",
        )
        self._poll_thread.start()

    def accept(self) -> SpeculationResult | None:
        """Accept the current speculation.

        Merges overlay files back to main cwd and returns the messages
        to inject into the conversation.

        Returns:
            SpeculationResult with messages and metadata, or None if not active
        """
        with self._lock:
            if not self._speculation_id or not self._is_running:
                return None

        state = self.state
        start_time = int(time.time() * 1000)

        # Abort the subprocess
        self._abort_event.set()
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass

        # Merge overlay files
        if self._overlay_manager:
            self._overlay_manager.copy_all_to_main()
            overlay_path = self._overlay_manager.overlay_path

        # Clean up overlay
        if overlay_path:
            remove_overlay(overlay_path)

        # Calculate time saved
        boundary = state.boundary
        completed_at = boundary.get("completed_at") if boundary else None
        time_saved = (
            (completed_at - (state.start_time or start_time))
            if completed_at and state.start_time
            else 0
        )

        is_complete = (
            boundary is not None and boundary.get("type") == "complete"
        ) or boundary is None

        messages = list(state.messages) if state.messages else []
        written_paths = list(state.written_paths) if state.written_paths else []

        # Log
        log_speculation(
            speculation_id=self._speculation_id or "unknown",
            outcome="accepted",
            duration_ms=time_saved,
            suggestion_length=state.suggestion_length,
            message_count=len(messages),
            boundary_type=boundary.get("type") if boundary else None,
            message_count_result=len(messages),
            time_saved_ms=time_saved,
            is_pipelined=self._is_pipelined,
        )

        # Reset state
        self._reset()

        return SpeculationResult(
            messages=messages,
            boundary=boundary,
            time_saved_ms=time_saved,
            is_complete=is_complete,
        )

    def abort(self) -> None:
        """Abort the current speculation.

        Kills the subprocess and removes the overlay without merging.
        """
        with self._lock:
            if not self._speculation_id:
                return

        speculation_id = self._speculation_id
        start_time = self.state.start_time or int(time.time() * 1000)
        suggestion_length = self.state.suggestion_length
        messages = list(self.state.messages) if self.state.messages else []

        # Signal abort
        self._abort_event.set()

        # Kill subprocess
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass

        # Remove overlay
        if self._overlay_manager:
            try:
                remove_overlay(self._overlay_manager.overlay_path)
            except Exception:
                pass

        # Log
        log_speculation(
            speculation_id=speculation_id or "unknown",
            outcome="aborted",
            duration_ms=int(time.time() * 1000) - start_time,
            suggestion_length=suggestion_length,
            message_count=len(messages),
            boundary_type=None,
            message_count_result=len(messages),
        )

        self._reset()

    # ─── Internal ────────────────────────────────────────────────────────────

    def _reset(self) -> None:
        """Reset service state after accept/abort."""
        with self._lock:
            self._is_running = False
            self._speculation_id = None
            self._process = None
            self._overlay_manager = None
            self._is_pipelined = False

        self._update_state(SpeculationState(status="idle"))

    def _run_speculation(
        self,
        suggestion_text: str,
        overlay_path: Path,
        main_cwd: str,
    ) -> None:
        """Run speculation in background thread.

        Spawns a ForkedAgentProcess, sends it the suggestion, and polls
        for messages while updating state.
        """
        from py_claw.fork.process import ForkedAgentProcess

        session_id = self._get_session_id()
        speculation_id = self._speculation_id

        try:
            self._process = ForkedAgentProcess(
                session_id=f"speculation-{session_id}-{speculation_id}",
                system_prompt="",
                cwd=main_cwd,
            )
            self._process.spawn()
            self._process.send_init()

            # Start speculation turn (fire-and-forget)
            self._process.start_speculation(
                query_text=suggestion_text,
                turn_count=0,
                overlay_path=str(overlay_path),
                main_cwd=main_cwd,
                max_turns=MAX_SPECULATION_TURNS,
            )

            messages: list[dict] = []
            tool_use_count = 0
            current_boundary: dict | None = None

            while not self._abort_event.is_set():
                msgs = self._process.iter_messages(timeout=1.0)

                for msg in msgs:
                    msg_type = msg.get("type")

                    if msg_type == "result":
                        current_boundary = msg.get("boundary")

                        # Count tool results
                        for tc in msg.get("tool_calls", []):
                            if tc.get("type") == "tool_result" and not tc.get("is_error"):
                                tool_use_count += 1

                        # Update state with boundary
                        if current_boundary is not None:
                            self._update_state(SpeculationState(
                                status="active",
                                id=speculation_id,
                                start_time=self.state.start_time,
                                boundary=current_boundary,
                                suggestion_length=len(suggestion_text),
                                tool_use_count=tool_use_count,
                                is_pipelined=self._is_pipelined,
                                messages=messages,
                                written_paths=list(self._overlay_manager.written_paths) if self._overlay_manager else [],
                                overlay_path=str(overlay_path),
                            ))

                        if current_boundary is None or current_boundary.get("type") == "complete":
                            # Speculation completed - log
                            boundary_type = current_boundary.get("type") if current_boundary else None
                            completed_at = current_boundary.get("completedAt") if current_boundary else None
                            start_time = self.state.start_time or int(time.time() * 1000)
                            duration_ms = (
                                (completed_at - start_time)
                                if completed_at and start_time
                                else int(time.time() * 1000) - start_time
                            )

                            log_speculation(
                                speculation_id=speculation_id or "unknown",
                                outcome="completed",
                                duration_ms=duration_ms,
                                suggestion_length=len(suggestion_text),
                                message_count=len(messages),
                                boundary_type=boundary_type,
                            )

                            # If complete, stay active with boundary set (UI shows completion)
                            # User can now accept or abort
                            if current_boundary and current_boundary.get("type") == "complete":
                                self._is_running = False  # Stop polling but keep state
                            else:
                                self._is_running = False
                                self._update_state(SpeculationState(status="idle"))
                            return

                    elif msg_type in ("assistant", "user"):
                        if len(messages) < MAX_SPECULATION_MESSAGES:
                            messages.append(msg)

                        # Count tool results in user messages
                        if msg_type == "user":
                            content = msg.get("message", {}).get("content", [])
                            if isinstance(content, list):
                                for block in content:
                                    if block.get("type") == "tool_result" and not block.get("is_error"):
                                        tool_use_count += 1

                        self._update_state(SpeculationState(
                            status="active",
                            id=speculation_id,
                            start_time=self.state.start_time,
                            boundary=current_boundary,
                            suggestion_length=len(suggestion_text),
                            tool_use_count=tool_use_count,
                            is_pipelined=self._is_pipelined,
                            messages=list(messages),
                            written_paths=list(self._overlay_manager.written_paths) if self._overlay_manager else [],
                            overlay_path=str(overlay_path),
                        ))

                    elif msg_type == "error":
                        logger.error("[Speculation] Error from subprocess: %s", msg.get("message"))
                        self._is_running = False
                        self._update_state(SpeculationState(status="idle"))
                        return

                # Check if process exited
                if self._process and not self._process.is_running:
                    if not msgs:
                        self._is_running = False
                        self._update_state(SpeculationState(status="idle"))
                        return

        except Exception as exc:
            logger.exception("[Speculation] Exception in speculation thread: %s", exc)
            log_speculation(
                speculation_id=speculation_id or "unknown",
                outcome="error",
                duration_ms=0,
                suggestion_length=len(suggestion_text) if suggestion_text else 0,
                message_count=0,
                boundary_type=None,
                error_type=type(exc).__name__,
                error_message=str(exc)[:200],
            )
            self._is_running = False
            self._update_state(SpeculationState(status="idle"))

    def _update_state(self, state: SpeculationState) -> None:
        """Update speculation state and notify callback."""
        with self._lock:
            # Update overlay manager written paths if available
            if self._overlay_manager and state.status == "active":
                # Keep in sync
                pass

        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_speculation_service: SpeculationService | None = None


def get_speculation_service() -> SpeculationService:
    """Get the global SpeculationService instance."""
    global _speculation_service
    if _speculation_service is None:
        import os
        _speculation_service = SpeculationService(
            get_cwd=lambda: os.getcwd(),
            get_session_id=lambda: os.environ.get("CLAUDE_SESSION_ID", "unknown"),
        )
    return _speculation_service
