"""
Tests for the token estimation service.
"""
from __future__ import annotations

import pytest

from py_claw.services.token_estimation import (
    TokenEstimationService,
    get_token_estimation_service,
    rough_token_count,
    estimate_tokens,
    bytes_per_token_for_file_type,
    TokenEstimationResult,
    TokenEstimateForMessage,
    TokenEstimateForMessages,
    DEFAULT_CHARS_PER_TOKEN,
    JSON_CHARS_PER_TOKEN,
    CODE_CHARS_PER_TOKEN,
)


class TestBytesPerTokenForFileType:
    """Tests for file-type-aware token ratio."""

    def test_json_ratio(self) -> None:
        assert bytes_per_token_for_file_type("json") == JSON_CHARS_PER_TOKEN
        assert bytes_per_token_for_file_type("JSON") == JSON_CHARS_PER_TOKEN
        assert bytes_per_token_for_file_type(".jsonl") == JSON_CHARS_PER_TOKEN

    def test_code_ratio(self) -> None:
        assert bytes_per_token_for_file_type("py") == CODE_CHARS_PER_TOKEN
        assert bytes_per_token_for_file_type("js") == CODE_CHARS_PER_TOKEN
        assert bytes_per_token_for_file_type("ts") == CODE_CHARS_PER_TOKEN
        assert bytes_per_token_for_file_type("rs") == CODE_CHARS_PER_TOKEN

    def test_default_ratio(self) -> None:
        assert bytes_per_token_for_file_type("txt") == DEFAULT_CHARS_PER_TOKEN
        assert bytes_per_token_for_file_type("unknown") == DEFAULT_CHARS_PER_TOKEN


class TestTokenEstimationService:
    """Tests for TokenEstimationService."""

    def setup_method(self) -> None:
        import py_claw.services.token_estimation.service as svc_module
        svc_module._service = None

    def test_singleton(self) -> None:
        svc1 = get_token_estimation_service()
        svc2 = get_token_estimation_service()
        assert svc1 is svc2

    def test_initialize(self) -> None:
        svc = get_token_estimation_service()
        svc.initialize()
        assert svc.initialized

    def test_rough_token_count_empty(self) -> None:
        svc = get_token_estimation_service()
        assert svc.rough_token_count("") == 0
        assert svc.rough_token_count("   ") == 1  # Whitespace still counts

    def test_rough_token_count_basic(self) -> None:
        svc = get_token_estimation_service()
        # 4 chars per token by default
        content = "a" * 40
        assert svc.rough_token_count(content) == 10

    def test_rough_token_count_custom_ratio(self) -> None:
        svc = get_token_estimation_service()
        content = "a" * 40
        # 2 chars per token
        assert svc.rough_token_count(content, chars_per_token=2) == 20

    def test_rough_token_count_for_file(self) -> None:
        svc = get_token_estimation_service()
        content = '{"key": "value"}'  # JSON is more token-dense
        tokens = svc.rough_token_count_for_file(content, "json")
        # Should use JSON ratio (~2)
        assert tokens == round(len(content) / JSON_CHARS_PER_TOKEN)

    def test_estimate_messages_tokens(self) -> None:
        svc = get_token_estimation_service()
        messages = [
            {"role": "user", "content": "Hello, world!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = svc.estimate_messages_tokens(messages)
        assert isinstance(result, TokenEstimateForMessages)
        assert result.total_tokens > 0
        assert len(result.message_tokens) == 2
        assert result.message_tokens[0].role == "user"
        assert result.message_tokens[1].role == "assistant"

    def test_estimate_messages_tokens_with_tool_content(self) -> None:
        svc = get_token_estimation_service()
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll help you."},
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "bash",
                        "input": {"command": "ls"},
                    },
                ],
            },
        ]
        result = svc.estimate_messages_tokens(messages)
        assert result.total_tokens > 0
        # Should include tool_use content in estimate
        assert "tool" in result.message_tokens[0].content.lower()

    def test_estimate_tool_tokens(self) -> None:
        svc = get_token_estimation_service()
        tools = [
            {
                "name": "bash",
                "description": "Run a bash command",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                    },
                },
            },
        ]
        tokens = svc.estimate_tool_tokens(tools)
        assert tokens > 0

    def test_estimate_tool_tokens_empty(self) -> None:
        svc = get_token_estimation_service()
        assert svc.estimate_tool_tokens([]) == 0
        assert svc.estimate_tool_tokens(None) == 0


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self) -> None:
        import py_claw.services.token_estimation.service as svc_module
        svc_module._service = None

    def test_rough_token_count(self) -> None:
        assert rough_token_count("Hello, world!") == rough_token_count("Hello, world!")

    def test_estimate_tokens_default(self) -> None:
        content = "Hello, world!"
        tokens = estimate_tokens(content)
        assert tokens == round(len(content) / DEFAULT_CHARS_PER_TOKEN)

    def test_estimate_tokens_with_extension(self) -> None:
        content = '{"key": "value"}'
        tokens = estimate_tokens(content, file_extension="json")
        assert tokens == round(len(content) / JSON_CHARS_PER_TOKEN)


class TestTokenEstimationResult:
    """Tests for TokenEstimationResult."""

    def test_defaults(self) -> None:
        result = TokenEstimationResult(input_tokens=100)
        assert result.input_tokens == 100
        assert result.method == "estimation"
        assert result.model is None

    def test_with_model(self) -> None:
        result = TokenEstimationResult(
            input_tokens=100,
            method="api",
            model="claude-sonnet-4",
        )
        assert result.method == "api"
        assert result.model == "claude-sonnet-4"


class TestTokenEstimateForMessages:
    """Tests for TokenEstimateForMessages."""

    def test_defaults(self) -> None:
        result = TokenEstimateForMessages(
            total_tokens=100,
            message_tokens=[],
        )
        assert result.total_tokens == 100
        assert result.tool_tokens == 0
        assert result.method == "estimation"

    def test_with_message_tokens(self) -> None:
        msg = TokenEstimateForMessage(role="user", content="Hi", tokens=2)
        result = TokenEstimateForMessages(
            total_tokens=10,
            message_tokens=[msg],
            tool_tokens=3,
            method="api",
        )
        assert result.total_tokens == 10
        assert len(result.message_tokens) == 1
        assert result.tool_tokens == 3
