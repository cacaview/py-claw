"""
Shared utilities for expanding environment variables in MCP server configurations.

Mirrors: ClaudeCode-main/src/services/mcp/envExpansion.ts
"""
from __future__ import annotations

import os
import re
from typing import Any


def expand_env_vars_in_string(value: str) -> dict[str, Any]:
    """
    Expand environment variables in a string value.

    Handles ${VAR} and ${VAR:-default} syntax.

    Args:
        value: String that may contain environment variable references

    Returns:
        Dict with 'expanded' (the expanded string) and 'missing_vars' (list of missing variable names)
    """
    missing_vars: list[str] = []

    def replace_var(match: re.Match[str]) -> str:
        var_content = match.group(1)
        # Split on :- to support default values (limit to 2 parts to preserve :- in defaults)
        parts = var_content.split(":-", 1)
        var_name = parts[0]
        default_value = parts[1] if len(parts) > 1 else None

        env_value = os.environ.get(var_name)
        if env_value is not None:
            return env_value
        if default_value is not None:
            return default_value

        # Track missing variable for error reporting
        missing_vars.append(var_name)
        # Return original if not found (allows debugging but will be reported as error)
        return match.group(0)

    expanded = re.sub(r'\$\{([^}]+)\}', replace_var, value)

    return {
        "expanded": expanded,
        "missing_vars": missing_vars,
    }


def expand_env_vars_in_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Expand environment variables in an MCP server config.

    Args:
        config: MCP server config dict

    Returns:
        Dict with 'expanded' (expanded config) and 'missing_vars' (all missing variable names)
    """
    all_missing_vars: list[str] = []

    def expand_value(val: Any) -> Any:
        if isinstance(val, str):
            result = expand_env_vars_in_string(val)
            all_missing_vars.extend(result["missing_vars"])
            return result["expanded"]
        elif isinstance(val, dict):
            return {k: expand_value(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [expand_value(item) for item in val]
        return val

    expanded = expand_value(config)
    return {
        "expanded": expanded,
        "missing_vars": list(set(all_missing_vars)),
    }
