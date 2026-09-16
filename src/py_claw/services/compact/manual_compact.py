"""Manual /compact orchestration.

Bridges the command layer and the compact service: normalizes the engine
transcript, runs ``compact_conversation``, and adapts the project's async
API client to the summary-call interface the compressor expects.

Write-back and rollback live on the query engine (``replace_transcript``
plus the pre-compact snapshot methods); this module only produces the
compaction result and the post-compact transcript.
"""
from __future__ import annotations

from typing import Any

from .compressor import compact_conversation
from .message_compat import estimate_message_tokens, normalize_compact_messages
from .types import CompactionResult


class AnthropicSummaryAdapter:
    """Adapt ``AsyncAnthropicClient`` to the summary-call shape compact uses.

    The compressor calls ``await api_client.create_message(messages=[...],
    model=..., max_tokens=...)`` and reads ``response.content[0].text``;
    ``AsyncAnthropicClient.create_message`` instead takes a
    ``MessageCreateParams`` object, hence this thin adapter.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def create_message(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
    ) -> Any:
        from py_claw.services.api.types import MessageCreateParams, MessageParam

        params = MessageCreateParams(
            model=model,
            messages=[MessageParam(**m) for m in messages],
            max_tokens=max_tokens,
        )
        return await self._client.create_message(params)


def build_compact_api_client() -> Any:
    """Build the summary API client, or ``None`` if unavailable.

    Construction failures (missing SDK, unconfigured provider) degrade
    gracefully: ``compact_conversation`` then compacts without a generated
    summary (boundary marker + preserved tail only).
    """
    try:
        from py_claw.services.api import AsyncAnthropicClient

        return AnthropicSummaryAdapter(AsyncAnthropicClient())
    except Exception:
        return None


async def run_manual_compact(
    messages: list[Any],
    *,
    api_client: Any = None,
    custom_instructions: str | None = None,
    token_counter: Any = None,
) -> CompactionResult:
    """Run a manual compaction over a raw engine transcript.

    Args:
        messages: Raw transcript entries (SDK objects or dicts).
        api_client: Summary client (see ``AnthropicSummaryAdapter``); when
            ``None`` the result carries no summary message.
        custom_instructions: Optional instructions injected into the
            summarization prompt.
        token_counter: Optional ``messages -> int`` estimator.

    Returns:
        ``CompactionResult``; convert it for write-back with
        ``build_compact_transcript``.

    Raises:
        ValueError: When there is not enough conversation to compact.
    """
    normalized = normalize_compact_messages(messages)
    counter = token_counter or estimate_message_tokens
    return await compact_conversation(
        normalized,
        counter,
        api_client=api_client,
        custom_instructions=custom_instructions,
        is_auto_compact=False,
    )
