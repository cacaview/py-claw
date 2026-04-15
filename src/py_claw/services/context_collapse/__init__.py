"""
Context Collapse service.

Collapses context windows while preserving key information.
"""
from py_claw.services.context_collapse.config import (
    ContextCollapseConfig,
    get_context_collapse_config,
    set_context_collapse_config,
)
from py_claw.services.context_collapse.service import (
    collapse_context_by_boundary,
    collapse_context_by_importance,
    collapse_context_hybrid,
    execute_context_collapse,
    get_collapse_stats,
    should_collapse_context,
)
from py_claw.services.context_collapse.types import (
    CollapseStrategy,
    CollapsedChunk,
    CollapseResult,
    CollapseState,
    CollapseStatus,
    get_collapse_state,
)


__all__ = [
    "CollapseStrategy",
    "ContextCollapseConfig",
    "CollapsedChunk",
    "CollapseResult",
    "CollapseState",
    "CollapseStatus",
    "get_context_collapse_config",
    "set_context_collapse_config",
    "should_collapse_context",
    "collapse_context_by_boundary",
    "collapse_context_by_importance",
    "collapse_context_hybrid",
    "execute_context_collapse",
    "get_collapse_stats",
    "get_collapse_state",
]
