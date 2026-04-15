"""Tests for away_summary service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestAwaySummaryConfig:
    """Tests for AwaySummaryConfig."""

    def test_default_values(self) -> None:
        """Test AwaySummaryConfig default values."""
        from py_claw.services.away_summary import AwaySummaryConfig

        config = AwaySummaryConfig()
        assert config.recent_message_window == 30
        assert config.max_summary_length == 500

    def test_custom_values(self) -> None:
        """Test AwaySummaryConfig with custom values."""
        from py_claw.services.away_summary import AwaySummaryConfig

        config = AwaySummaryConfig(
            recent_message_window=50,
            max_summary_length=1000,
        )
        assert config.recent_message_window == 50
        assert config.max_summary_length == 1000


class TestAwaySummaryService:
    """Tests for AwaySummaryService."""

    def test_service_initialization(self) -> None:
        """Test service can be initialized."""
        from py_claw.services.away_summary import AwaySummaryService

        service = AwaySummaryService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_generate_summary_empty_messages(self) -> None:
        """Test generate_summary with empty messages returns None."""
        from py_claw.services.away_summary import AwaySummaryService

        service = AwaySummaryService()
        result = await service.generate_summary([])
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_summary_api_error(self) -> None:
        """Test generate_summary handles API errors gracefully."""
        from py_claw.services.away_summary import AwaySummaryService

        mock_client = MagicMock()
        # Simulate API error response
        mock_response = MagicMock()
        mock_response.content = [{"type": "error", "text": "API Error"}]
        mock_client.create_message.return_value = mock_response

        service = AwaySummaryService(api_client=mock_client)

        mock_message = MagicMock()
        mock_message.id = "msg1"
        mock_message.role = "user"
        mock_message.content = "Hello"

        result = await service.generate_summary([mock_message])
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_summary_success(self) -> None:
        """Test generate_summary returns summary on success."""
        from py_claw.services.away_summary import AwaySummaryService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [{"type": "text", "text": "Working on feature X. Next: implement Y."}]
        mock_client.create_message.return_value = mock_response

        service = AwaySummaryService(api_client=mock_client)

        mock_message = MagicMock()
        mock_message.id = "msg1"
        mock_message.role = "user"
        mock_message.content = "Hello"

        result = await service.generate_summary([mock_message])
        assert result is not None
        assert "Working on feature X" in result

    @pytest.mark.asyncio
    async def test_generate_summary_truncation(self) -> None:
        """Test generate_summary truncates long summaries."""
        from py_claw.services.away_summary import AwaySummaryService

        mock_client = MagicMock()
        # Create a very long response
        long_text = "A" * 1000
        mock_response = MagicMock()
        mock_response.content = [{"type": "text", "text": long_text}]
        mock_client.create_message.return_value = mock_response

        service = AwaySummaryService(
            api_client=mock_client,
            config=MagicMock(recent_message_window=30, max_summary_length=100),
        )

        mock_message = MagicMock()
        mock_message.id = "msg1"
        mock_message.role = "user"
        mock_message.content = "Hello"

        result = await service.generate_summary([mock_message])
        assert result is not None
        assert len(result) <= 100 + 3  # 100 chars + "..."

    @pytest.mark.asyncio
    async def test_generate_summary_with_session_memory(self) -> None:
        """Test generate_summary uses session memory when available."""
        from py_claw.services.away_summary import AwaySummaryService

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [{"type": "text", "text": "Summary text"}]
        mock_client.create_message.return_value = mock_response

        service = AwaySummaryService(api_client=mock_client)

        mock_message = MagicMock()
        mock_message.id = "msg1"
        mock_message.role = "user"
        mock_message.content = "Hello"

        # Mock session memory (async function needs to return awaitable)
        async def mock_get_memory():
            return "Project context from memory"

        with patch.object(
            service,
            "_get_session_memory_content",
            side_effect=mock_get_memory,
        ):
            result = await service.generate_summary([mock_message])
            assert result is not None

            # Check the API was called
            mock_client.create_message.assert_called_once()
            call_args = mock_client.create_message.call_args
            # The call is: client.create_message(MessageCreateParams(...))
            # call_args[0][0] is the MessageCreateParams object
            params = call_args[0][0]
            messages = params.messages
            user_message = messages[-1]
            assert "Session memory" in user_message.content
            assert "Project context from memory" in user_message.content


class TestAwaySummaryModuleFunctions:
    """Tests for module-level away_summary functions."""

    @pytest.mark.asyncio
    async def test_generate_away_summary_function(self) -> None:
        """Test generate_away_summary module function."""
        from py_claw.services.away_summary import generate_away_summary

        mock_message = MagicMock()
        mock_message.id = "msg1"
        mock_message.role = "user"
        mock_message.content = "Hello"

        with patch(
            "py_claw.services.away_summary.service.get_away_summary_service"
        ) as mock_get:
            mock_service = MagicMock()
            # generate_summary is async, so return_value needs to be awaitable
            async def mock_generate(*args, **kwargs):
                return "Test summary"
            mock_service.generate_summary = mock_generate
            mock_get.return_value = mock_service

            result = await generate_away_summary([mock_message])
            assert result == "Test summary"


class TestBuildAwaySummaryPrompt:
    """Tests for prompt building."""

    def test_build_prompt_without_memory(self) -> None:
        """Test prompt building without session memory."""
        from py_claw.services.away_summary.service import _build_away_summary_prompt

        result = _build_away_summary_prompt(None)
        assert "The user stepped away and is coming back" in result
        assert "Session memory" not in result

    def test_build_prompt_with_memory(self) -> None:
        """Test prompt building with session memory."""
        from py_claw.services.away_summary.service import _build_away_summary_prompt

        result = _build_away_summary_prompt("Project context")
        assert "Session memory" in result
        assert "Project context" in result
        assert "The user stepped away" in result


class TestGetAssistantText:
    """Tests for _get_assistant_text helper."""

    def test_extract_text_from_response(self) -> None:
        """Test extracting text from assistant response."""
        from py_claw.services.away_summary.service import _get_assistant_text

        mock_response = MagicMock()
        mock_response.content = [
            {"type": "text", "text": "Hello world"},
            {"type": "text", "text": "Second part"},
        ]

        result = _get_assistant_text(mock_response)
        assert result == "Hello world"

    def test_extract_text_empty_content(self) -> None:
        """Test extracting text from empty content."""
        from py_claw.services.away_summary.service import _get_assistant_text

        mock_response = MagicMock()
        mock_response.content = []

        result = _get_assistant_text(mock_response)
        assert result == ""
