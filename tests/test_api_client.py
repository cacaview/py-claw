"""Tests for the API client module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from py_claw.services.api import (
    AnthropicClient,
    ContentBlock,
    Message,
    MessageCreateParams,
    MessageParam,
    ProviderConfig,
    Usage,
    create_client,
    classify_error,
    is_prompt_too_long,
    PromptTooLongError,
    RateLimitError,
    OverloadedError,
)


class TestProviderConfig:
    def test_default_provider_is_first_party(self):
        config = ProviderConfig()
        assert config.provider == "firstParty"

    def test_provider_with_api_key(self):
        config = ProviderConfig(api_key="test-key")
        assert config.api_key == "test-key"


class TestMessageCreateParams:
    def test_minimal_params(self):
        params = MessageCreateParams(
            model="claude-sonnet-4-20250514",
            messages=[MessageParam(role="user", content="Hello")],
        )
        assert params.model == "claude-sonnet-4-20250514"
        assert len(params.messages) == 1
        assert params.messages[0].content == "Hello"
        assert params.max_tokens == 4096
        assert params.stream is False

    def test_with_system_prompt(self):
        params = MessageCreateParams(
            model="claude-sonnet-4-20250514",
            messages=[MessageParam(role="user", content="Hello")],
            system="You are a helpful assistant.",
        )
        assert params.system == "You are a helpful assistant."

    def test_with_temperature(self):
        params = MessageCreateParams(
            model="claude-sonnet-4-20250514",
            messages=[MessageParam(role="user", content="Hello")],
            temperature=0.7,
        )
        assert params.temperature == 0.7


class TestCreateClient:
    def test_create_client_without_api_key(self):
        # Should not raise even without API key
        client = create_client(api_key=None)
        assert isinstance(client, AnthropicClient)
        assert client.config is not None

    def test_create_client_with_api_key(self):
        client = create_client(api_key="test-key")
        assert client.config.api_key == "test-key"


class TestClassifyError:
    def test_401_is_authentication_error(self):
        error = classify_error(401, "Unauthorized", {})
        from py_claw.services.api.errors import AuthenticationError
        assert isinstance(error, AuthenticationError)
        assert error.status_code == 401
        assert error.retryable is False

    def test_429_is_rate_limit_error(self):
        error = classify_error(429, "Rate limit exceeded", {})
        assert isinstance(error, RateLimitError)
        assert error.status_code == 429
        assert error.retryable is True

    def test_529_is_overloaded_error(self):
        error = classify_error(529, "Server overloaded", {})
        assert isinstance(error, OverloadedError)
        assert error.status_code == 529
        assert error.retryable is True

    def test_400_prompt_too_long(self):
        error = classify_error(
            400,
            "Prompt is too long",
            {"type": "invalid_request", "error": {"message": "Prompt is too long"}},
        )
        assert isinstance(error, PromptTooLongError)

    def test_500_is_internal_error(self):
        error = classify_error(500, "Internal server error", {})
        from py_claw.services.api.errors import InternalError
        assert isinstance(error, InternalError)
        assert error.retryable is True


class TestIsPromptTooLong:
    def test_prompt_too_long_error(self):
        error = PromptTooLongError("Prompt is too long")
        assert is_prompt_too_long(error) is True

    def test_rate_limit_is_not_prompt_too_long(self):
        error = RateLimitError("Rate limit exceeded")
        assert is_prompt_too_long(error) is False

    def test_generic_400_with_prompt_message(self):
        from py_claw.services.api.errors import InvalidRequestError
        error = InvalidRequestError("maximum context length exceeded")
        assert is_prompt_too_long(error) is True


class TestContentBlock:
    def test_text_block(self):
        block = ContentBlock(type="text", text="Hello, world!")
        assert block.type == "text"
        assert block.text == "Hello, world!"

    def test_tool_use_block(self):
        block = ContentBlock(
            type="tool_use",
            id="tool_1",
            name="bash",
            input={"command": "ls"},
        )
        assert block.type == "tool_use"
        assert block.name == "bash"
        assert block.input == {"command": "ls"}


class TestUsage:
    def test_basic_usage(self):
        usage = Usage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cache_creation_input_tokens is None
        assert usage.cache_read_input_tokens is None

    def test_with_cache(self):
        usage = Usage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=150,
        )
        assert usage.cache_creation_input_tokens == 200
        assert usage.cache_read_input_tokens == 150


class TestMessage:
    def test_message_construction(self):
        msg = Message(
            id="msg_123",
            type="message",
            role="assistant",
            content=[ContentBlock(type="text", text="Hello!")],
            model="claude-sonnet-4-20250514",
            stop_reason="end_turn",
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        assert msg.id == "msg_123"
        assert msg.role == "assistant"
        assert len(msg.content) == 1
        assert msg.stop_reason == "end_turn"
