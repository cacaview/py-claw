"""
Thinkback play service - hidden command to play thinkback animation.

Based on ClaudeCode-main/src/commands/thinkback-play/
"""
from py_claw.services.thinkback_play.service import play
from py_claw.services.thinkback_play.types import ThinkbackPlayResult


__all__ = [
    "play",
    "ThinkbackPlayResult",
]
