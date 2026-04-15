"""
Companion sprite widget for Textual UI.

Based on ClaudeCode-main/src/buddy/CompanionSprite.tsx

Renders companion ASCII sprite, speech bubble, and pet animations
in the terminal using Textual widgets.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from textual.widget import Widget
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Label, Static

from py_claw.services.buddy.companion import get_companion
from py_claw.services.buddy.notification import is_buddy_live
from py_claw.services.buddy.service import (
    BuddyConfig,
    get_buddy_config,
)
from py_claw.services.buddy.sprites import (
    render_face,
    render_sprite,
    sprite_frame_count,
)
from py_claw.services.buddy.types import (
    Companion,
    RARITY_COLORS,
)


# Animation constants
TICK_MS = 500
BUBBLE_SHOW = 20  # ticks → ~10s at 500ms
FADE_WINDOW = 6  # last ~3s the bubble dims
PET_BURST_MS = 2500  # how long hearts float after /buddy pet

# Idle sequence: mostly rest (frame 0), occasional fidget (frames 1-2), rare blink.
IDLE_SEQUENCE = [0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0]

# Hearts float up-and-out over 5 ticks (~2.5s)
HEART_FRAMES = [
    "   ♥    ♥   ",
    "  ♥  ♥   ♥  ",
    " ♥   ♥  ♥   ",
    "♥  ♥      ♥ ",
    "·    ·   ·  ",
]


def _wrap_text(text: str, width: int) -> List[str]:
    """Wrap text to specified width."""
    words = text.split(" ")
    lines: List[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        lines.append(cur)
    return lines


def _get_rarity_color(rarity: str) -> str:
    """Map rarity to a Textual color."""
    color_map = {
        "common": "white",
        "uncommon": "green",
        "rare": "cyan",
        "epic": "magenta",
        "legendary": "yellow",
    }
    return color_map.get(rarity, "white")


class SpeechBubble(Widget):
    """Speech bubble widget for companion reactions."""

    def __init__(
        self,
        text: str,
        color: str = "white",
        fading: bool = False,
        tail: str = "right",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.text = text
        self.color = color
        self.fading = fading
        self.tail = tail

    def compose(self) -> ComposeResult:
        lines = _wrap_text(self.text, 30)
        border_color = "dim" if self.fading else self.color
        text_color = "dim" if self.fading else self.color

        # Build bubble lines
        bubble_lines = []
        for line in lines:
            style = f"@{text_color}" if text_color != "white" else ""
            bubble_lines.append(Static(line, markup=True, style=style))

        with Vertical(
            classes="speech-bubble",
            border=("round", border_color),
            padding=1,
        ):
            for bl in bubble_lines:
                yield bl

        # Tail
        if self.tail == "right":
            yield Label("─", markup=True, style=f"@{border_color}")
        elif self.tail == "down":
            yield Label("╲", markup=True, style=f"@{border_color}")


class CompanionSpriteWidget(Widget):
    """
    Main companion sprite widget.

    Displays companion ASCII art, name, and speech bubbles.
    Handles idle animation, reactions, and pet animations.
    """

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        companion_reaction: Optional[str] = None,
        companion_pet_at: Optional[int] = None,
        focused: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.config = config or {}
        self.companion_reaction = companion_reaction
        self.companion_pet_at = companion_pet_at
        self.focused = focused
        self._tick = 0
        self._last_spoke_tick = 0
        self._pet_start_tick = 0

    def on_mount(self) -> None:
        """Set up animation timer on mount."""
        self.set_interval(TICK_MS / 1000.0, self._on_tick)

    def _on_tick(self) -> None:
        """Handle animation tick."""
        self._tick += 1
        # Handle bubble auto-dismiss
        if self.companion_reaction:
            bubble_age = self._tick - self._last_spoke_tick
            if bubble_age >= BUBBLE_SHOW:
                self.companion_reaction = None
        # Handle pet animation
        if self.companion_pet_at:
            pet_age = self._tick - self._pet_start_tick
            if pet_age * TICK_MS >= PET_BURST_MS:
                self.companion_pet_at = None
        self.refresh()

    def _get_frame(self, companion: Companion) -> int:
        """Get current animation frame."""
        frame_count = sprite_frame_count(companion.species)

        # Excited: cycle all fidget frames fast
        if self.companion_reaction or self._is_petting():
            return self._tick % frame_count

        # Idle sequence
        step = IDLE_SEQUENCE[self._tick % len(IDLE_SEQUENCE)]
        if step == -1:
            return 0  # blink
        return step % frame_count

    def _is_petting(self) -> bool:
        """Check if currently in petting animation."""
        if not self.companion_pet_at:
            return False
        pet_age = self._tick - self._pet_start_tick
        return pet_age * TICK_MS < PET_BURST_MS

    def _render_sprite_lines(self, companion: Companion) -> List[str]:
        """Render sprite with current animation frame."""
        frame = self._get_frame(companion)
        lines = render_sprite(companion, frame)

        # Apply blink if needed
        step = IDLE_SEQUENCE[self._tick % len(IDLE_SEQUENCE)]
        if step == -1:
            lines = [line.replace(companion.eye, "-") for line in lines]

        return lines

    def _get_heart_frame(self) -> Optional[str]:
        """Get current heart frame for pet animation."""
        if not self._is_petting():
            return None
        pet_age = self._tick - self._pet_start_tick
        return HEART_FRAMES[pet_age % len(HEART_FRAMES)]

    def set_reaction(self, reaction: Optional[str]) -> None:
        """Set companion reaction and reset timer."""
        if reaction and not self.companion_reaction:
            self._last_spoke_tick = self._tick
        self.companion_reaction = reaction
        self.refresh()

    def set_pet_at(self, timestamp: int) -> None:
        """Set pet timestamp."""
        self.companion_pet_at = timestamp
        self._pet_start_tick = self._tick
        self.refresh()

    def compose(self) -> ComposeResult:
        """Compose the companion sprite UI."""
        if not is_buddy_live():
            return

        companion = get_companion(self.config)
        if not companion or get_buddy_config().companion_muted:
            return

        color = _get_rarity_color(companion.rarity)
        heart_frame = self._get_heart_frame()

        # Render sprite lines
        sprite_lines = self._render_sprite_lines(companion)

        with Horizontal(classes="companion-sprite"):
            # Speech bubble (if speaking and not fullscreen)
            if self.companion_reaction:
                bubble_age = self._tick - self._last_spoke_tick
                fading = bubble_age >= BUBBLE_SHOW - FADE_WINDOW
                yield SpeechBubble(
                    self.companion_reaction,
                    color=color,
                    fading=fading,
                    tail="right",
                    classes="companion-bubble",
                )

            # Sprite column
            with Vertical(classes="sprite-column"):
                # Heart frame (above sprite)
                if heart_frame:
                    yield Label(heart_frame, markup=True, style="@auto_accept")

                # Sprite lines
                for i, line in enumerate(sprite_lines):
                    style = f"@{color}" if i == 0 and heart_frame else None
                    yield Label(line, markup=True, style=style)

                # Name row
                name_label = f" {companion.name} " if self.focused else companion.name
                name_style = f"@{color} bold" if self.focused else f"@{color} dim"
                yield Label(name_label, markup=True, style=name_style)


class CompanionFloatingBubble(Widget):
    """
    Floating bubble overlay for fullscreen mode.

    Mounted in bottomFloat slot so it can extend into scrollback region.
    """

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        companion_reaction: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.config = config or {}
        self.companion_reaction = companion_reaction

    def on_mount(self) -> None:
        """Set up animation timer on mount."""
        self.set_interval(TICK_MS / 1000.0, self._on_tick)

    def _on_tick(self) -> None:
        """Handle animation tick."""
        self.refresh()

    def compose(self) -> ComposeResult:
        """Compose the floating bubble."""
        if not is_buddy_live() or not self.companion_reaction:
            return

        companion = get_companion(self.config)
        if not companion or get_buddy_config().companion_muted:
            return

        color = _get_rarity_color(companion.rarity)
        yield SpeechBubble(
            self.companion_reaction,
            color=color,
            fading=False,
            tail="down",
            classes="floating-bubble",
        )


def get_companion_display_width(companion: Companion) -> int:
    """
    Calculate display width for a companion sprite.

    Args:
        companion: The companion

    Returns:
        Width in characters
    """
    return max(12, len(companion.name) + 2)


__all__ = [
    "CompanionSpriteWidget",
    "CompanionFloatingBubble",
    "SpeechBubble",
    "get_companion_display_width",
]
