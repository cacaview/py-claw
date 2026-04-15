"""
Thinkback service for Claude Code Year in Review animation.

Based on ClaudeCode-main/src/commands/thinkback/
"""
from py_claw.services.thinkback.service import (
    check_installation,
    find_thinkback_skill_dir,
    get_skill_directories,
    get_thinkback_info,
    play_animation,
    show_menu,
)
from py_claw.services.thinkback.types import (
    AnimationResult,
    MenuAction,
    ThinkbackPhase,
    ThinkbackResult,
)


__all__ = [
    "find_thinkback_skill_dir",
    "get_skill_directories",
    "check_installation",
    "play_animation",
    "show_menu",
    "get_thinkback_info",
    "ThinkbackPhase",
    "MenuAction",
    "AnimationResult",
    "ThinkbackResult",
]
