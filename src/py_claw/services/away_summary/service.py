"""
AwaySummary service - generates "While you were away" session recap.

Generates a short session recap for the "while you were away" card
when the user returns after being away.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Awaitable

from py_claw.services.api import AnthropicClient, MessageCreateParams, MessageParam

from .config import get_away_summary_config
from .types import AwaySummaryConfig

if TYPE_CHECKING:
    from py_claw.schemas.common import Message

logger = logging.getLogger(__name__)

# Default model for away summary (fast and capable)
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Maximum tokens for summary generation
MAX_SUMMARY_TOKENS = 256


def _get_small_fast_model() -> str:
    """Get the small fast model for lightweight API calls."""
    return DEFAULT_MODEL


def _build_away_summary_prompt(memory: str | None) -> str:
    """Build the away summary prompt."""
    memory_block = f"Session memory (broader context):\n{memory}\n\n" if memory else ""
    return (
        f"{memory_block}"
        "The user stepped away and is coming back. "
        "Write exactly 1-3 short sentences. "
        "Start by stating the high-level task — what they are building or debugging, "
        "not implementation details. Next: the concrete next step. "
        "Skip status reports and commit recaps."
    )


def _get_assistant_text(response: Any) -> str:
    """Extract text content from an assistant message response."""
    if hasattr(response, "content"):
        content = response.content
        if isinstance(content, list):
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    return text
                # Handle dict-like blocks
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        return text
    return ""


class AwaySummaryService:
    """Generates short session recaps for returning users.

    Uses a small fast model to generate 1-3 sentence summaries
    of what was being worked on and what the next step is.
    """

    def __init__(
        self,
        config: AwaySummaryConfig | None = None,
        api_client: AnthropicClient | None = None,
    ) -> None:
        self._config = config or AwaySummaryConfig()
        self._api_client = api_client or AnthropicClient()

    async def generate_summary(
        self,
        messages: list[Message],
        signal: Awaitable[Any] | None = None,
    ) -> str | None:
        """Generate an away summary for the given messages.

        Args:
            messages: List of conversation messages.
            signal: Optional abort signal.

        Returns:
            Summary string, or None if generation failed/empty.
        """
        if not messages:
            return None

        try:
            # Get session memory content if available
            memory = await self._get_session_memory_content()

            # Take recent messages
            recent = messages[-self._config.recent_message_window :]

            # Build prompt with appended user message
            summary_prompt = _build_away_summary_prompt(memory)
            recent_messages = [
                *(self._message_to_param(m) for m in recent),
                MessageParam(role="user", content=summary_prompt),
            ]

            # Prepare API call kwargs
            kwargs: dict[str, Any] = {
                "model": _get_small_fast_model(),
                "messages": recent_messages,
                "max_tokens": MAX_SUMMARY_TOKENS,
                "system": [],
                "tools": [],
                "thinking": {"type": "disabled"},
            }

            # Handle abort signal
            if signal is not None:
                ab_signal = await signal
                if ab_signal is not None and hasattr(ab_signal, "aborted") and ab_signal.aborted:
                    return None

            # Make API call
            result = self._api_client.create_message(
                MessageCreateParams(**kwargs)
            )

            # Check for API error message
            if hasattr(result, "content") and isinstance(result.content, list):
                for block in result.content:
                    # Handle both dict-style and object-style blocks
                    if isinstance(block, dict):
                        if block.get("type") == "error":
                            text = block.get("text") or str(block)
                            logger.debug(f"[awaySummary] API error: {text}")
                            return None
                    elif getattr(block, "type", None) == "error":
                        text = getattr(block, "text", None) or str(block)
                        logger.debug(f"[awaySummary] API error: {text}")
                        return None

            summary = _get_assistant_text(result)
            if not summary:
                return None

            # Truncate to max length
            if len(summary) > self._config.max_summary_length:
                summary = summary[: self._config.max_summary_length].rsplit(" ", 1)[0] + "..."

            return summary

        except Exception as err:
            logger.debug(f"[awaySummary] generation failed: {err}")
            return None

    async def _get_session_memory_content(self) -> str | None:
        """Get current session memory content if available."""
        try:
            from py_claw.services.session_memory.memory_file import (
                get_session_memory_content,
            )
            return await get_session_memory_content()
        except Exception:
            return None

    def _message_to_param(self, message: Message) -> MessageParam:
        """Convert a Message to MessageParam."""
        role = getattr(message, "role", "user")
        content = getattr(message, "content", "")

        if isinstance(content, str):
            return MessageParam(role=role, content=content)

        # Handle content blocks
        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                else:
                    text = getattr(block, "text", "") or ""
                if text:
                    text_parts.append(text)
            content = " ".join(text_parts) if text_parts else ""

        return MessageParam(role=role, content=content)


# Global singleton instance
_service: AwaySummaryService | None = None
_init_lock: Any = None


def get_away_summary_service() -> AwaySummaryService:
    """Get the global AwaySummaryService singleton."""
    global _service
    if _service is None:
        try:
            import threading
            global _init_lock
            if _init_lock is None:
                _init_lock = threading.Lock()
            with _init_lock:
                if _service is None:
                    _service = AwaySummaryService()
        except Exception:
            # Fallback if threading not available
            if _service is None:
                _service = AwaySummaryService()
    return _service


async def generate_away_summary(
    messages: list[Message],
    signal: Awaitable[Any] | None = None,
) -> str | None:
    """Generate an away summary for the given messages."""
    return await get_away_summary_service().generate_summary(messages, signal)
