"""
YAML parsing utilities.

Thin wrapper around PyYAML's safe_load for consistent API surface.

Reference: ClaudeCode-main/src/utils/yaml.ts
"""
from __future__ import annotations

from typing import Any


def parse_yaml(input: str) -> Any:
    """
    Parse a YAML string and return the resulting Python object.

    Uses PyYAML's safe_load to avoid arbitrary code execution.

    Args:
        input: YAML string to parse

    Returns:
        Parsed Python object (dict, list, str, int, float, bool, or None)

    Raises:
        yaml.YAMLError: If the input is not valid YAML
    """
    import yaml  # lazy import — only loaded when needed
    return yaml.safe_load(input)
