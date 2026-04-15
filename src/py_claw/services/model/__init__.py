"""Model utilities - model selection, alias resolution, and API provider detection."""

from __future__ import annotations

from .providers import APIProvider, get_api_provider, is_first_party_anthropic_base_url
from .model import (
    ModelName,
    ModelShortName,
    ModelSetting,
    get_small_fast_model,
    get_main_loop_model,
    get_default_opus_model,
    get_default_sonnet_model,
    get_default_haiku_model,
    parse_user_specified_model,
    first_party_name_to_canonical,
    get_canonical_name,
    render_model_name,
    get_public_model_name,
    normalize_model_string_for_api,
)

__all__ = [
    "APIProvider",
    "get_api_provider",
    "is_first_party_anthropic_base_url",
    "ModelName",
    "ModelShortName",
    "ModelSetting",
    "get_small_fast_model",
    "get_main_loop_model",
    "get_default_opus_model",
    "get_default_sonnet_model",
    "get_default_haiku_model",
    "parse_user_specified_model",
    "first_party_name_to_canonical",
    "get_canonical_name",
    "render_model_name",
    "get_public_model_name",
    "normalize_model_string_for_api",
]
