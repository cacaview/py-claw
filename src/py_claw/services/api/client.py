from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator

from anthropic import Anthropic, AnthropicBedrock, AsyncAnthropic

from py_claw.services.api.types import (
    APIError,
    ApiProvider,
    BETA_HEADERS,
    ContentBlock,
    CountTokensResult,
    Message,
    MessageCreateParams,
    MessageCreateResult,
    MessageDelta,
    MessageDeltaEvent,
    MessageStartEvent,
    ProviderConfig,
    StreamEvent,
    ToolUseBlock,
    Usage,
)


def _get_api_key() -> str | None:
    """Get API key from environment."""
    return os.environ.get("ANTHROPIC_API_KEY")


def _get_provider() -> ApiProvider:
    """Determine which API provider to use based on env vars."""
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK"):
        return "bedrock"
    if os.environ.get("CLAUDE_CODE_USE_VERTEX"):
        return "vertex"
    if os.environ.get("CLAUDE_CODE_USE_FOUNDRY"):
        return "foundry"
    return "firstParty"


def _build_provider_config(api_key: str | None = None) -> ProviderConfig:
    """Build provider config from environment."""
    provider = _get_provider()
    config = ProviderConfig(provider=provider)

    if api_key:
        config.api_key = api_key
    else:
        config.api_key = _get_api_key()

    # AWS Bedrock
    if provider == "bedrock":
        config.aws_region = os.environ.get("AWS_REGION", "us-east-1")
        config.aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        config.aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        config.aws_session_token = os.environ.get("AWS_SESSION_TOKEN")

    # Google Vertex
    if provider == "vertex":
        config.vertex_region = os.environ.get("VERTEX_REGION", "us-east-1")
        config.vertex_project_id = os.environ.get("VERTEX_PROJECT_ID")

    # Azure Foundry
    if provider == "foundry":
        config.azure_endpoint = os.environ.get("ANTHROPIC_FOUNDRY_ENDPOINT")
        config.azure_ad_token_provider = os.environ.get("ANTHROPIC_FOUNDRY_AD_TOKEN_PROVIDER")

    return config


def _create_sync_client(config: ProviderConfig) -> Anthropic:
    """Create a synchronous Anthropic client."""
    kwargs: dict[str, Any] = {}

    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.base_url:
        kwargs["base_url"] = config.base_url

    if config.provider == "bedrock":
        # Use Bedrock client
        bedrock_kwargs: dict[str, Any] = {}
        if config.aws_access_key:
            bedrock_kwargs["aws_access_key"] = config.aws_access_key
        if config.aws_secret_key:
            bedrock_kwargs["aws_secret_key"] = config.aws_secret_key
        if config.aws_session_token:
            bedrock_kwargs["aws_session_token"] = config.aws_session_token
        return AnthropicBedrock(
            region=config.aws_region or "us-east-1",
            **bedrock_kwargs,
        )

    return Anthropic(**kwargs)


class AnthropicClient:
    """Synchronous client for Anthropic API."""

    def __init__(
        self,
        config: ProviderConfig | None = None,
        api_key: str | None = None,
    ) -> None:
        if config is None:
            config = _build_provider_config(api_key)
        self.config = config
        self._client = _create_sync_client(config)
        self._beta_headers = {
            "anthropic-beta": "; ".join(BETA_HEADERS),
        }

    def create_message(
        self,
        params: MessageCreateParams,
    ) -> MessageCreateResult:
        """Create a non-streaming message."""
        kwargs = self._build_kwargs(params)
        response = self._client.messages.create(**kwargs)
        return self._parse_response(response)

    def create_message_streaming(
        self,
        params: MessageCreateParams,
    ) -> Iterator[StreamEvent]:
        """Create a streaming message, yielding events."""
        kwargs = self._build_kwargs(params)
        kwargs["stream"] = True

        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                parsed = self._parse_stream_event(event)
                if parsed is not None:
                    yield parsed

    def count_tokens(self, text: str) -> CountTokensResult:
        """Count tokens in text (estimate)."""
        # Use the SDK's token counting if available, otherwise estimate
        try:
            result = self._client.count_tokens(text)
            return CountTokensResult(input_tokens=result)
        except AttributeError:
            # Fallback: rough estimate (4 chars per token)
            return CountTokensResult(input_tokens=max(1, len(text) // 4))

    def _build_kwargs(self, params: MessageCreateParams) -> dict[str, Any]:
        """Build kwargs for API call from params."""
        kwargs: dict[str, Any] = {
            "model": params.model,
            "messages": [m.model_dump() for m in params.messages],
            "max_tokens": params.max_tokens,
        }

        if params.system is not None:
            if isinstance(params.system, list):
                kwargs["system"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in params.system]
            else:
                kwargs["system"] = params.system

        if params.tools:
            kwargs["tools"] = [t.model_dump(by_alias=True) for t in params.tools]

        if params.tool_choice:
            kwargs["tool_choice"] = params.tool_choice

        if params.temperature is not None:
            kwargs["temperature"] = params.temperature

        if params.top_p is not None:
            kwargs["top_p"] = params.top_p

        if params.top_k is not None:
            kwargs["top_k"] = params.top_k

        if params.thinking:
            kwargs["thinking"] = params.thinking

        if params.betas:
            kwargs["betas"] = params.betas

        if params.metadata:
            kwargs["metadata"] = params.metadata

        return kwargs

    def _parse_response(self, response: Any) -> MessageCreateResult:
        """Parse non-streaming API response."""
        return MessageCreateResult(
            id=response.id,
            type="message",
            role="assistant",
            content=[
                ContentBlock(type=c.type, text=getattr(c, "text", None))
                for c in response.content
            ],
            model=response.model,
            stop_reason=response.stop_reason,
            usage=Usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", None),
                cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", None),
            ),
        )

    def _parse_stream_event(self, event: Any) -> StreamEvent | None:
        """Parse a streaming event from the SDK."""
        event_type = event.type

        if event_type == "message_start":
            return MessageStartEvent(
                type="message_start",
                message=self._parse_message(event.message),
            )

        if event_type == "content_block_start":
            block = event.content_block
            if block.type == "thinking":
                from py_claw.services.api.types import ThinkingBlock
                return StreamEvent(
                    type="content_block_start",
                    index=event.index,
                    content_block=ThinkingBlock(type="thinking", thinking=""),
                )
            elif block.type == "tool_use":
                return StreamEvent(
                    type="content_block_start",
                    index=event.index,
                    content_block=ToolUseBlock(
                        type="tool_use",
                        id=block.id or "",
                        name=block.name or "",
                        input=block.input or {},
                    ),
                )
            else:
                return StreamEvent(
                    type="content_block_start",
                    index=event.index,
                    content_block=ContentBlock(type=block.type or "text", text=""),
                )

        if event_type == "content_block_delta":
            delta = event.delta
            from py_claw.services.api.types import ContentBlockDeltaEvent, ContentDelta
            if delta.type == "thinking_delta":
                return ContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=event.index,
                    delta=ContentDelta(type="thinking_delta", thinking=delta.thinking or ""),
                )
            elif delta.type == "input_json_delta":
                return ContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=event.index,
                    delta=ContentDelta(type="input_json_delta", input_json=delta.input_json or ""),
                )
            else:
                return ContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=event.index,
                    delta=ContentDelta(type="text_delta", text=delta.text or ""),
                )

        if event_type == "content_block_stop":
            return StreamEvent(type="content_block_stop", index=event.index)

        if event_type == "message_delta":
            usage = None
            if event.delta.usage:
                usage = Usage(
                    input_tokens=event.delta.usage.input_tokens or 0,
                    output_tokens=event.delta.usage.output_tokens or 0,
                )
            return MessageDeltaEvent(
                type="message_delta",
                delta=MessageDelta(
                    stop_reason=event.delta.stop_reason,
                    usage=usage,
                ),
            )

        if event_type == "message_stop":
            return StreamEvent(type="message_stop")

        if event_type == "error":
            return StreamEvent(
                type="error",
                error=getattr(event, "error", str(event)),
            )

        # Skip unknown events
        return None

    def _parse_message(self, msg: Any) -> Message:
        """Parse a Message object from SDK response."""
        content = []
        for block in msg.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    content.append(ContentBlock(type="text", text=block.text or ""))
                elif block.type == "tool_use":
                    content.append(ContentBlock(
                        type="tool_use",
                        id=block.id or "",
                        name=block.name or "",
                        input=block.input or {},
                    ))
                elif block.type == "thinking":
                    content.append(ContentBlock(
                        type="thinking",
                        thinking=block.thinking or "",
                    ))
        return Message(
            id=msg.id,
            type="message",
            role=msg.role,
            content=content,
            model=msg.model,
            stop_reason=msg.stop_reason,
            usage=Usage(
                input_tokens=msg.usage.input_tokens,
                output_tokens=msg.usage.output_tokens,
                cache_creation_input_tokens=getattr(msg.usage, "cache_creation_input_tokens", None),
                cache_read_input_tokens=getattr(msg.usage, "cache_read_input_tokens", None),
            ),
        )


class AsyncAnthropicClient:
    """Asynchronous client for Anthropic API."""

    def __init__(
        self,
        config: ProviderConfig | None = None,
        api_key: str | None = None,
    ) -> None:
        if config is None:
            config = _build_provider_config(api_key)
        self.config = config
        self._client = AsyncAnthropic(api_key=config.api_key or undefined)
        self._beta_headers = {
            "anthropic-beta": "; ".join(BETA_HEADERS),
        }

    async def create_message(
        self,
        params: MessageCreateParams,
    ) -> MessageCreateResult:
        """Create a non-streaming message."""
        kwargs = self._build_kwargs(params)
        response = await self._client.messages.create(**kwargs)
        return self._parse_response(response)

    async def create_message_streaming(
        self,
        params: MessageCreateParams,
    ) -> AsyncIterator[StreamEvent]:
        """Create a streaming message, yielding events."""
        kwargs = self._build_kwargs(params)
        kwargs["stream"] = True

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                parsed = self._parse_stream_event(event)
                if parsed is not None:
                    yield parsed

    def _build_kwargs(self, params: MessageCreateParams) -> dict[str, Any]:
        """Build kwargs for API call from params."""
        kwargs: dict[str, Any] = {
            "model": params.model,
            "messages": [m.model_dump() for m in params.messages],
            "max_tokens": params.max_tokens,
        }

        if params.system is not None:
            if isinstance(params.system, list):
                kwargs["system"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in params.system]
            else:
                kwargs["system"] = params.system

        if params.tools:
            kwargs["tools"] = [t.model_dump(by_alias=True) for t in params.tools]

        if params.tool_choice:
            kwargs["tool_choice"] = params.tool_choice

        if params.temperature is not None:
            kwargs["temperature"] = params.temperature

        if params.thinking:
            kwargs["thinking"] = params.thinking

        if params.betas:
            kwargs["betas"] = params.betas

        return kwargs

    def _parse_response(self, response: Any) -> MessageCreateResult:
        """Parse non-streaming API response."""
        return MessageCreateResult(
            id=response.id,
            type="message",
            role="assistant",
            content=[
                ContentBlock(type=c.type, text=getattr(c, "text", None))
                for c in response.content
            ],
            model=response.model,
            stop_reason=response.stop_reason,
            usage=Usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )

    def _parse_stream_event(self, event: Any) -> StreamEvent | None:
        """Parse a streaming event from the SDK."""
        event_type = event.type

        if event_type == "message_start":
            return MessageStartEvent(
                type="message_start",
                message=self._parse_message(event.message),
            )

        if event_type == "content_block_start":
            block = event.content_block
            return StreamEvent(
                type="content_block_start",
                index=event.index,
                content_block=ContentBlock(type=block.type or "text", text=""),
            )

        if event_type == "content_block_delta":
            delta = event.delta
            from py_claw.services.api.types import ContentBlockDeltaEvent, ContentDelta
            return ContentBlockDeltaEvent(
                type="content_block_delta",
                index=event.index,
                delta=ContentDelta(
                    type=delta.type,
                    text=delta.text if hasattr(delta, "text") else None,
                    thinking=delta.thinking if hasattr(delta, "thinking") else None,
                    input_json=delta.input_json if hasattr(delta, "input_json") else None,
                ),
            )

        if event_type == "content_block_stop":
            return StreamEvent(type="content_block_stop", index=event.index)

        if event_type == "message_delta":
            return MessageDeltaEvent(
                type="message_delta",
                delta=MessageDelta(
                    stop_reason=event.delta.stop_reason,
                ),
            )

        if event_type == "message_stop":
            return StreamEvent(type="message_stop")

        return None

    def _parse_message(self, msg: Any) -> Message:
        """Parse a Message object from SDK response."""
        content = []
        for block in msg.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    content.append(ContentBlock(type="text", text=block.text or ""))
                elif block.type == "tool_use":
                    content.append(ContentBlock(
                        type="tool_use",
                        id=block.id or "",
                        name=block.name or "",
                        input=block.input or {},
                    ))
        return Message(
            id=msg.id,
            type="message",
            role=msg.role,
            content=content,
            model=msg.model,
            usage=Usage(
                input_tokens=msg.usage.input_tokens,
                output_tokens=msg.usage.output_tokens,
            ),
        )


# Sentinel for undefined
undefined = object()  # type: ignore[misc]
