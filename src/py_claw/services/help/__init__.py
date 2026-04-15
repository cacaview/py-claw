"""
Help service for displaying help and documentation.

Based on ClaudeCode-main/src/services/help/
"""
from py_claw.services.help.service import (
    format_help_text,
    get_help_categories,
    get_help_config,
    get_topic,
    search_help,
)
from py_claw.services.help.types import HelpCategory, HelpConfig, HelpTopic


__all__ = [
    "get_help_config",
    "get_help_categories",
    "get_topic",
    "search_help",
    "format_help_text",
    "HelpCategory",
    "HelpConfig",
    "HelpTopic",
]
