"""
Token estimation service.

Centralized token counting across different backends:
- Anthropic API (when available)
- Rough estimation (fallback)
- File-type-aware estimation
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .types import (
    TokenEstimationResult,
    TokenEstimateForMessage,
    TokenEstimateForMessages,
    bytes_per_token_for_file_type,
    DEFAULT_CHARS_PER_TOKEN,
)


class TokenEstimationService:
    """
    Service for estimating token counts.

    Supports:
    - Direct API counting (when ANTHROPIC_API_KEY is available)
    - Rough estimation with file-type-aware ratios
    - Per-message breakdown
    """

    def __init__(self) -> None:
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        """Initialize the token estimation service."""
        self._initialized = True

    def rough_token_count(self, content: str, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
        """
        Rough token count estimation using character ratio.

        Args:
            content: Text content to estimate
            chars_per_token: Characters per token ratio (default 4)

        Returns:
            Estimated token count
        """
        if not content:
            return 0
        return max(1, round(len(content) / chars_per_token))

    def rough_token_count_for_file(
        self,
        content: str,
        file_extension: str,
    ) -> int:
        """
        Rough token count with file-type-aware ratio.

        Args:
            content: Text content to estimate
            file_extension: File extension for ratio lookup

        Returns:
            Estimated token count
        """
        ratio = bytes_per_token_for_file_type(file_extension)
        return self.rough_token_count(content, ratio)

    async def count_tokens_with_api(
        self,
        content: str,
        model: str | None = None,
    ) -> TokenEstimationResult | None:
        """
        Count tokens using the Anthropic API.

        Args:
            content: Text content to count
            model: Model to use (uses default if not specified)

        Returns:
            TokenEstimationResult or None if API unavailable
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)

            model_name = model or "claude-sonnet-4-20250514"

            response = client.beta.messages.count_tokens(
                model=model_name,
                messages=[{"role": "user", "content": content}],
            )

            return TokenEstimationResult(
                input_tokens=response.input_tokens,
                method="api",
                model=model_name,
            )
        except Exception:
            return None

    async def count_messages_tokens_with_api(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> TokenEstimationResult | None:
        """
        Count tokens for messages using the Anthropic API.

        Args:
            messages: List of messages with role and content
            tools: Optional list of tool definitions
            model: Model to use

        Returns:
            TokenEstimationResult or None if API unavailable
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)

            model_name = model or "claude-sonnet-4-20250514"

            # Convert messages to API format
            api_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, str):
                    api_messages.append({"role": role, "content": content})
                else:
                    api_messages.append({"role": role, "content": content})

            kwargs: dict[str, Any] = {"model": model_name, "messages": api_messages}
            if tools:
                kwargs["tools"] = tools

            response = client.beta.messages.count_tokens(**kwargs)

            return TokenEstimationResult(
                input_tokens=response.input_tokens,
                method="api",
                model=model_name,
            )
        except Exception:
            return None

    def estimate_messages_tokens(
        self,
        messages: list[dict[str, Any]],
    ) -> TokenEstimateForMessages:
        """
        Estimate tokens for a list of messages.

        Args:
            messages: List of messages with role and content

        Returns:
            TokenEstimateForMessages with per-message breakdown
        """
        total = 0
        message_estimates = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, str):
                tokens = self.rough_token_count(content)
            elif isinstance(content, list):
                # Handle content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            # Include tool name in estimate
                            tool_name = block.get("name", "")
                            tool_input = str(block.get("input", ""))
                            text_parts.append(f"Tool: {tool_name} {tool_input}")
                tokens = self.rough_token_count(" ".join(text_parts))
            else:
                tokens = self.rough_token_count(str(content))

            message_estimates.append(TokenEstimateForMessage(
                role=role,
                content=str(content)[:100] if isinstance(content, str) else str(content),
                tokens=tokens,
            ))
            total += tokens

        return TokenEstimateForMessages(
            total_tokens=total,
            message_tokens=message_estimates,
            method="estimation",
        )

    def estimate_tool_tokens(
        self,
        tools: list[dict[str, Any]],
    ) -> int:
        """
        Estimate tokens for tool definitions.

        Args:
            tools: List of tool definitions

        Returns:
            Estimated token count
        """
        if not tools:
            return 0

        total = 0
        for tool in tools:
            # Include tool name and description
            parts = []
            if "name" in tool:
                parts.append(f"tool: {tool['name']}")
            if "description" in tool:
                parts.append(tool["description"])
            if "input_schema" in tool or "parameters" in tool:
                schema = tool.get("input_schema") or tool.get("parameters", {})
                parts.append(str(schema))

            total += self.rough_token_count(" ".join(parts))

        return total


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_service: TokenEstimationService | None = None


def get_token_estimation_service() -> TokenEstimationService:
    """Get the global token estimation service."""
    global _service
    if _service is None:
        _service = TokenEstimationService()
    return _service


def rough_token_count(content: str) -> int:
    """Quick rough token count estimation."""
    return get_token_estimation_service().rough_token_count(content)


def estimate_tokens(content: str, file_extension: str | None = None) -> int:
    """
    Estimate tokens for content.

    Args:
        content: Text content
        file_extension: Optional file extension for type-aware estimation

    Returns:
        Estimated token count
    """
    svc = get_token_estimation_service()
    if file_extension:
        return svc.rough_token_count_for_file(content, file_extension)
    return svc.rough_token_count(content)
