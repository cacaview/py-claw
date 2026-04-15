"""Model selection, alias resolution, and model name utilities."""

from __future__ import annotations

import os
import re
from typing import Literal, Optional

# Type aliases matching the TypeScript source
ModelName = str
ModelShortName = str
ModelSetting = Optional[str] | Literal["opusplan", "sonnet", "haiku", "opus", "best"] | None

# Default model strings
 Opus_46 = "claude-opus-4-6-20250514"
SONNET_46 = "claude-sonnet-4-6-20250514"
HAIKU_45 = "claude-haiku-4-5-20241022"
 Opus_45 = "claude-opus-4-5-20241022"
SONNET_45 = "claude-sonnet-4-5-20241022"
SONNET_40 = "claude-sonnet-4-0-20250514"
 Opus_41 = "claude-opus-4-1-20250514"
 Opus_40 = "claude-opus-4-0-20240219"
HAIKU_35 = "claude-haiku-3-5-20241022"
SONNET_37 = "claude-sonnet-3-7-20250514"
SONNET_35 = "claude-sonnet-3-5-20241022"


def _get_env_default(model_env: str | None, default: str) -> str:
    """Get model from environment variable or return default."""
    if model_env:
        return model_env
    return default


def get_small_fast_model() -> ModelName:
    """Get the small fast model for lightweight operations."""
    return os.environ.get("ANTHROPIC_SMALL_FAST_MODEL") or get_default_haiku_model()


def get_default_opus_model() -> ModelName:
    """Get the default Opus model."""
    env = os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    if env:
        return env
    # Default to Opus 4.6
    return Opus_46


def get_default_sonnet_model() -> ModelName:
    """Get the default Sonnet model."""
    env = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
    if env:
        return env
    # Default to Sonnet 4.6
    return SONNET_46


def get_default_haiku_model() -> ModelName:
    """Get the default Haiku model."""
    env = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")
    if env:
        return env
    # Haiku 4.5 is available on all platforms
    return HAIKU_45


def get_main_loop_model() -> ModelName:
    """Get the main loop model based on user settings and defaults."""
    specified = _get_user_specified_model()
    if specified is not None:
        return parse_user_specified_model(specified)
    return _get_default_main_loop_model()


def _get_user_specified_model() -> ModelSetting | None:
    """Get the user-specified model from settings or environment."""
    # TODO: integrate with settings loader
    model_override = os.environ.get("ANTHROPIC_MODEL")
    if model_override:
        return model_override
    return None


def _get_default_main_loop_model() -> ModelName:
    """Get the default main loop model based on subscription type."""
    # For now, return Sonnet 4.6 as the default
    return get_default_sonnet_model()


def parse_user_specified_model(model_input: str) -> ModelName:
    """
    Parse user-specified model input and resolve to canonical model name.

    Supports:
    - Model aliases: 'opus', 'sonnet', 'haiku', 'opusplan', 'best'
    - [1m] suffix for 1M context window
    - Legacy Opus model remapping
    """
    model_input = model_input.strip()
    normalized = model_input.lower()

    # Check for 1M context suffix
    has_1m_tag = "[1m]" in normalized
    model_str = normalized.replace("[1m]", "").strip() if has_1m_tag else normalized

    # Resolve aliases
    alias_resolvers = {
        "opusplan": get_default_sonnet_model,
        "sonnet": get_default_sonnet_model,
        "haiku": get_default_haiku_model,
        "opus": get_default_opus_model,
        "best": get_default_opus_model,
    }

    if model_str in alias_resolvers:
        resolved = alias_resolvers[model_str]()
        return resolved + "[1m]" if has_1m_tag else resolved

    # Legacy Opus remapping for first-party
    if _is_legacy_opus_first_party(model_str) and _is_legacy_model_remap_enabled():
        resolved = get_default_opus_model()
        return resolved + "[1m]" if has_1m_tag else resolved

    # Preserve original case for custom model names
    if has_1m_tag:
        return model_input.replace("[1m]", "").strip() + "[1m]"
    return model_input


def _is_legacy_opus_first_party(model: str) -> bool:
    """Check if model is a legacy Opus model."""
    legacy_models = [
        "claude-opus-4-20250514",
        "claude-opus-4-1-20250805",
        "claude-opus-4-0",
        "claude-opus-4-1",
    ]
    return model in legacy_models


def _is_legacy_model_remap_enabled() -> bool:
    """Check if legacy model remapping is enabled."""
    return os.environ.get("CLAUDE_CODE_DISABLE_LEGACY_MODEL_REMAP", "").lower() not in (
        "true",
        "1",
        "yes",
    )


def first_party_name_to_canonical(name: str) -> ModelShortName:
    """
    Strip date/provider suffixes from first-party model name.

    Converts 'claude-opus-4-6-20250514' to 'claude-opus-4-6'.
    """
    name = name.lower()

    # Check more specific versions first (order matters)
    canonical_patterns = [
        (r"claude-opus-4-6", "claude-opus-4-6"),
        (r"claude-opus-4-5", "claude-opus-4-5"),
        (r"claude-opus-4-1", "claude-opus-4-1"),
        (r"claude-opus-4", "claude-opus-4"),
        (r"claude-sonnet-4-6", "claude-sonnet-4-6"),
        (r"claude-sonnet-4-5", "claude-sonnet-4-5"),
        (r"claude-sonnet-4", "claude-sonnet-4"),
        (r"claude-haiku-4-5", "claude-haiku-4-5"),
        (r"claude-3-7-sonnet", "claude-3-7-sonnet"),
        (r"claude-3-5-sonnet", "claude-3-5-sonnet"),
        (r"claude-3-5-haiku", "claude-3-5-haiku"),
        (r"claude-3-opus", "claude-3-opus"),
        (r"claude-3-sonnet", "claude-3-sonnet"),
        (r"claude-3-haiku", "claude-3-haiku"),
    ]

    for pattern, canonical in canonical_patterns:
        if re.search(pattern, name):
            return canonical

    # Fall back to extracting base model name
    match = re.match(r"(claude-(\d+-\d+-)?\w+)", name)
    if match:
        return match.group(1)
    return name


def get_canonical_name(full_model_name: str) -> ModelShortName:
    """Map full model string to canonical short version."""
    return first_party_name_to_canonical(full_model_name)


def get_public_model_display_name(model: str) -> str | None:
    """Get human-readable display name for known public models."""
    display_names = {
        Opus_46: "Opus 4.6",
        f"{Opus_46}[1m]": "Opus 4.6 (1M context)",
        Opus_45: "Opus 4.5",
        Opus_41: "Opus 4.1",
        Opus_40: "Opus 4",
        f"{SONNET_46}[1m]": "Sonnet 4.6 (1M context)",
        SONNET_46: "Sonnet 4.6",
        f"{SONNET_45}[1m]": "Sonnet 4.5 (1M context)",
        SONNET_45: "Sonnet 4.5",
        f"{SONNET_40}[1m]": "Sonnet 4 (1M context)",
        SONNET_40: "Sonnet 4",
        SONNET_37: "Sonnet 3.7",
        SONNET_35: "Sonnet 3.5",
        HAIKU_45: "Haiku 4.5",
        HAIKU_35: "Haiku 3.5",
    }
    return display_names.get(model)


def render_model_name(model: str) -> str:
    """Get human-readable model name for display."""
    public_name = get_public_model_display_name(model)
    if public_name:
        return public_name
    return model


def get_public_model_name(model: str) -> str:
    """
    Get safe author name for public display (e.g., git commit trailers).
    Returns "Claude {ModelName}" for public models.
    """
    public_name = get_public_model_display_name(model)
    if public_name:
        return f"Claude {public_name}"
    return f"Claude ({model})"


def normalize_model_string_for_api(model: str) -> str:
    """Remove [1m] or [2m] suffix from model string for API calls."""
    return re.sub(r"\[(1|2)m\]", "", model, flags=re.IGNORECASE)
