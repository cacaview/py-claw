"""
ExtractMemories service.

Extracts key memories from conversations using forked subagent.
"""
from py_claw.services.extract_memories.config import (
    DEFAULT_EXTRACTION_PROMPT,
    ExtractMemoriesConfig,
    get_extract_memories_config,
    set_extract_memories_config,
)
from py_claw.services.extract_memories.service import (
    check_and_extract_memories,
    extract_memories,
    get_extraction_stats,
    should_extract_memories,
)
from py_claw.services.extract_memories.types import (
    ExtractionResult,
    ExtractionState,
    ExtractionStatus,
    get_extraction_state,
)


__all__ = [
    "ExtractMemoriesConfig",
    "ExtractionResult",
    "ExtractionState",
    "ExtractionStatus",
    "DEFAULT_EXTRACTION_PROMPT",
    "get_extract_memories_config",
    "set_extract_memories_config",
    "should_extract_memories",
    "extract_memories",
    "check_and_extract_memories",
    "get_extraction_stats",
    "get_extraction_state",
]
