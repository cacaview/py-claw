"""
TUI State helpers — bridge between Store and Textual widgets.

Provides reactive state subscription helpers so Textual widgets can:
- Subscribe to TUI state from the global Store
- Publish TUI state changes to the Store
- Coordinate cross-widget TUI state (prompt mode, overlays, vim, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from py_claw.state import get_global_store


@datlass
class TUIStateSnapshot:
    """Snapshot of TUI state at a point in time."""
    prompt_mode: str = "normal"
    vim_mode: str = "INSERT"
    prompt_value: str = ""
    has_suggestions: bool = False
    selected_suggestion_index: int = -1
    suggestion_count: int = 0
    queued_prompts: list[str] = list()
    stashed_prompt: Optional[str] = None
    pasted_content_id: Optional[str] = None
    pasted_content_label: Optional[str] = None
    narrow_terminal: bool = False
    active_overlays: frozenset = frozenset()


class TUIStateSubscriber:
    """
    Subscription helper for TUI state.

    Usage:
        sub = TUIStateSubscriber()
        sub.subscribe(lambda state: print(f"mode changed: {state.prompt_mode}"))
        # Later: sub.unsubscribe()
    """

    def __init__(self) -> None:
        self._callbacks: list[Callable[[TUIStateSnapshot], None]] = []
        self._unsubscribe_store: Callable[[], None] | None = None

    def subscribe(self, callback: Callable[[TUIStateSnapshot], None]) -> None:
        """Subscribe to TUI state changes."""
        self._callbacks.append(callback)

        # Lazy-connect to store
        if self._unsubscribe_store is None:
            store = get_global_store()

            def _on_store_change() -> None:
                snap = _get_tui_snapshot(store.get_state())
                for cb in self._callbacks:
                    try:
                        cb(snap)
                    except Exception:
                        pass

            self._unsubscribe_store = store.subscribe(_on_store_change)

    def unsubscribe(self) -> None:
        """Unsubscribe all callbacks."""
        self._callbacks.clear()
        if self._unsubscribe_store:
            self._unsubscribe_store()
            self._unsubscribe_store = None


# ─── Store update helpers ────────────────────────────────────────────────────


def update_tui_prompt_mode(mode: str) -> None:
    """Update the prompt mode in the global store."""
    store = get_global_store()
    store.update(lambda s: _with_tui(s, lambda t: setattr(t, "prompt_mode", mode)))


def update_tui_vim_mode(vim_mode: str) -> None:
    """Update the vim mode in the global store."""
    store = get_global_store()
    store.update(lambda s: _with_tui(s, lambda t: setattr(t, "vim_mode", vim_mode)))


def update_tui_suggestions(has_suggestions: bool, count: int = 0, selected_index: int = -1) -> None:
    """Update suggestion state in the global store."""
    store = get_global_store()
    def updater(s: Any) -> Any:
        return _with_tui(s, lambda t: (
            setattr(t, "has_suggestions", has_suggestions),
            setattr(t, "suggestion_count", count),
            setattr(t, "selected_suggestion_index", selected_index),
        ))
    store.update(updater)


def update_tui_prompt_value(value: str) -> None:
    """Update the current prompt value in the global store."""
    store = get_global_store()
    store.update(lambda s: _with_tui(s, lambda t: setattr(t, "prompt_value", value)))


def queue_prompt(text: str) -> None:
    """Queue a prompt for later execution."""
    store = get_global_store()
    def updater(s: Any) -> Any:
        def inner(t: Any) -> None:
            t.queued_prompts = list(t.queued_prompts) + [text]
        return _with_tui(s, inner)
    store.update(updater)


def dequeue_prompt() -> str | None:
    """Dequeue the next prompt. Returns (prompt, new_state)."""
    store = get_global_store()
    state = store.get_state()
    tui = state.tui
    if not tui.queued_prompts:
        return None
    prompt = tui.queued_prompts[0]
    store.update(lambda s: _with_tui(s, lambda t: setattr(t, "queued_prompts", list(t.queued_prompts[1:]))))
    return prompt


def stash_prompt(text: str | None) -> None:
    """Stash or unstash the current prompt."""
    store = get_global_store()
    store.update(lambda s: _with_tui(s, lambda t: setattr(t, "stashed_prompt", text)))


def set_pasted_content(content_id: str | None, label: str | None) -> None:
    """Set pasted content info."""
    store = get_global_store()
    def updater(s: Any) -> Any:
        def inner(t: Any) -> None:
            t.pasted_content_id = content_id
            t.pasted_content_label = label
        return _with_tui(s, inner)
    store.update(updater)


def set_narrow_terminal(narrow: bool) -> None:
    """Set narrow terminal mode."""
    store = get_global_store()
    store.update(lambda s: _with_tui(s, lambda t: setattr(t, "narrow_terminal", narrow)))


def add_active_overlay(overlay_id: str) -> None:
    """Add an active overlay to the global store."""
    store = get_global_store()
    store.update(lambda s: _with_overlay_add(s, overlay_id))


def remove_active_overlay(overlay_id: str) -> None:
    """Remove an active overlay from the global store."""
    store = get_global_store()
    store.update(lambda s: _with_overlay_remove(s, overlay_id))


# ─── Internal helpers ──────────────────────────────────────────────────────


def _get_tui_snapshot(state: Any) -> TUIStateSnapshot:
    """Extract TUI snapshot from AppState."""
    tui = state.tui
    return TUIStateSnapshot(
        prompt_mode=tui.prompt_mode,
        vim_mode=tui.vim_mode,
        prompt_value=tui.prompt_value,
        has_suggestions=tui.has_suggestions,
        selected_suggestion_index=tui.selected_suggestion_index,
        suggestion_count=tui.suggestion_count,
        queued_prompts=list(tui.queued_prompts),
        stashed_prompt=tui.stashed_prompt,
        pasted_content_id=tui.pasted_content_id,
        pasted_content_label=tui.pasted_content_label,
        narrow_terminal=tui.narrow_terminal,
        active_overlays=frozenset(state.active_overlays),
    )


def _with_tui(state: Any, fn: Callable[[Any], None]) -> Any:
    """Apply fn to state.tui and return new state."""
    new_tui = _copy_tui(state.tui)
    fn(new_tui)
    return _replace_tui(state, new_tui)


def _copy_tui(tui: Any) -> Any:
    """Create a shallow copy of TUIState."""
    from dataclasses import replace
    return replace(tui)


def _replace_tui(state: Any, new_tui: Any) -> Any:
    """Replace state.tui in the AppState."""
    import dataclasses
    return dataclasses.replace(state, tui=new_tui)


def _with_overlay_add(state: Any, overlay_id: str) -> Any:
    """Add an overlay to state.active_overlays."""
    import dataclasses
    new_overlays = set(state.active_overlays) | {overlay_id}
    return dataclasses.replace(state, active_overlays=new_overlays)


def _with_overlay_remove(state: Any, overlay_id: str) -> Any:
    """Remove an overlay from state.active_overlays."""
    import dataclasses
    new_overlays = set(state.active_overlays) - {overlay_id}
    return dataclasses.replace(state, active_overlays=new_overlays)
