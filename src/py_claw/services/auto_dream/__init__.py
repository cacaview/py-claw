"""
AutoDream service.

Background memory consolidation service that triggers /dream prompt.
"""
from py_claw.services.auto_dream.config import (
    DEFAULT_DREAM_PROMPT,
    AutoDreamConfig,
    get_auto_dream_config,
    set_auto_dream_config,
)
from py_claw.services.auto_dream.service import (
    check_and_trigger_dream,
    get_dream_stats,
    should_trigger_dream,
    trigger_dream,
)
from py_claw.services.auto_dream.types import DreamResult, DreamState, DreamStatus, get_dream_state


__all__ = [
    "AutoDreamConfig",
    "DreamResult",
    "DreamState",
    "DreamStatus",
    "DEFAULT_DREAM_PROMPT",
    "get_auto_dream_config",
    "set_auto_dream_config",
    "should_trigger_dream",
    "trigger_dream",
    "check_and_trigger_dream",
    "get_dream_stats",
    "get_dream_state",
]
