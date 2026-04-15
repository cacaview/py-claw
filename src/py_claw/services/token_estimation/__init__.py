"""
Token Estimation Service.

Centralized token counting across different backends.

Provides:
- Direct API counting (when ANTHROPIC_API_KEY is available)
- Rough estimation with file-type-aware ratios
- Per-message breakdown
- Tool definition token estimation

Basic usage:

    from py_claw.services.token_estimation import rough_token_count, estimate_tokens

    # Quick rough estimate
    tokens = rough_token_count("Hello, world!")

    # File-type-aware estimate
    tokens = estimate_tokens(json_content, file_extension="json")
"""
from __future__ import annotations

from .types import (
    TokenEstimationResult,
    TokenEstimateForMessage,
    TokenEstimateForMessages,
    bytes_per_token_for_file_type,
    DEFAULT_CHARS_PER_TOKEN,
    JSON_CHARS_PER_TOKEN,
    CODE_CHARS_PER_TOKEN,
)
from .service import (
    TokenEstimationService,
    get_token_estimation_service,
    rough_token_count,
    estimate_tokens,
)

__all__ = [
    # Types
    "TokenEstimationResult",
    "TokenEstimateForMessage",
    "TokenEstimateForMessages",
    # Constants
    "bytes_per_token_for_file_type",
    "DEFAULT_CHARS_PER_TOKEN",
    "JSON_CHARS_PER_TOKEN",
    "CODE_CHARS_PER_TOKEN",
    # Service
    "TokenEstimationService",
    "get_token_estimation_service",
    # Convenience
    "rough_token_count",
    "estimate_tokens",
]
