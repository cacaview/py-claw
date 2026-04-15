"""
ExtractMemories configuration.

Service for extracting memories from conversations using forked subagent.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractMemoriesConfig:
    """Configuration for ExtractMemories service."""

    enabled: bool = False
    # Minimum messages before extraction triggers
    min_messages: int = 20
    # Minimum token count before extraction triggers
    min_tokens: int = 10000
    # Whether to run in forked subagent mode
    use_forked_agent: bool = True
    # Extraction prompt template
    prompt_template: str | None = None
    # Output file path for memories
    output_path: str | None = None

    @classmethod
    def from_settings(cls, settings: dict) -> ExtractMemoriesConfig:
        """Create config from settings dictionary."""
        em_settings = settings.get("extractMemories", {})
        return cls(
            enabled=em_settings.get("enabled", False),
            min_messages=em_settings.get("minMessages", 20),
            min_tokens=em_settings.get("minTokens", 10000),
            use_forked_agent=em_settings.get("useForkedAgent", True),
            prompt_template=em_settings.get("promptTemplate"),
            output_path=em_settings.get("outputPath"),
        )


# Global config instance
_config: ExtractMemoriesConfig | None = None


def get_extract_memories_config() -> ExtractMemoriesConfig:
    """Get the current ExtractMemories configuration."""
    global _config
    if _config is None:
        _config = ExtractMemoriesConfig()
    return _config


def set_extract_memories_config(config: ExtractMemoriesConfig) -> None:
    """Set the ExtractMemories configuration."""
    global _config
    _config = config


# Default extraction prompt
DEFAULT_EXTRACTION_PROMPT = """You are extracting key memories from a conversation. Analyze the conversation and identify:

1. Key decisions made and their rationale
2. Important facts or information shared
3. User preferences and requirements
4. Technical approaches or solutions used
5. Any unresolved issues or follow-ups
6. Lessons learned or patterns observed

Format the output as a structured memory file that can be referenced in future sessions.

Be concise but comprehensive. Focus on information that would be valuable to remember for future interactions."""
