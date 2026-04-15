"""Tests for voice service."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from py_claw.services.voice import (
    AudioChunk,
    AudioDevice,
    AudioInputDevice,
    KeywordDetector,
    STTProvider,
    STTError,
    StreamSTT,
    StreamSTTConfig,
    TranscriptionResult,
    VoiceConfig,
    VoiceService,
    detect_keywords,
    detect_phrase_matches,
    extract_keyword_context,
    build_keyword_pattern,
    list_audio_devices,
)


class TestVoiceConfig:
    """Tests for VoiceConfig."""

    def test_default_values(self):
        """Test VoiceConfig defaults."""
        config = VoiceConfig()
        assert config.provider == STTProvider.DEEPGRAM
        assert config.model == "nova-3"
        assert config.sample_rate == 16000
        assert config.channels == 1
        assert config.keywords == []

    def test_custom_values(self):
        """Test VoiceConfig with custom values."""
        config = VoiceConfig(
            provider=STTProvider.DEEPGRAM,
            model="nova-2",
            sample_rate=44100,
            channels=2,
            keywords=["hello", "world"],
        )
        assert config.model == "nova-2"
        assert config.sample_rate == 44100
        assert config.channels == 2
        assert config.keywords == ["hello", "world"]

    def test_from_env_with_defaults(self):
        """Test VoiceConfig.from_env() with no env vars."""
        with patch.dict("os.environ", {}, clear=True):
            config = VoiceConfig.from_env()
            assert config.provider == STTProvider.DEEPGRAM
            assert config.model == "nova-3"
            assert config.sample_rate == 16000

    def test_from_env_with_vars(self):
        """Test VoiceConfig.from_env() with env vars."""
        env = {
            "DEEPGRAM_API_KEY": "test-key",
            "STT_LANGUAGE": "fr-FR",
        }
        with patch.dict("os.environ", env, clear=True):
            config = VoiceConfig.from_env()
            assert config.provider == STTProvider.DEEPGRAM
            assert config.api_key == "test-key"
            assert config.language == "fr-FR"


class TestTranscriptionResult:
    """Tests for TranscriptionResult."""

    def test_default_final(self):
        """Test default is_final is True."""
        result = TranscriptionResult(text="Hello world")
        assert result.text == "Hello world"
        assert result.is_final is True
        assert result.confidence is None
        assert result.words == []

    def test_with_confidence(self):
        """Test result with confidence."""
        result = TranscriptionResult(
            text="Testing",
            is_final=False,
            confidence=0.95,
            words=[{"word": "Testing", "start": 0.0, "end": 0.5}],
        )
        assert result.is_final is False
        assert result.confidence == 0.95
        assert len(result.words) == 1


class TestKeywordDetection:
    """Tests for keyword detection functions."""

    def test_detect_keywords_basic(self):
        """Test basic keyword detection."""
        text = "Hello world, hello again"
        keywords = ["hello", "world"]
        detected = detect_keywords(text, keywords)
        assert "hello" in detected
        assert "world" in detected

    def test_detect_keywords_case_sensitive(self):
        """Test case-sensitive detection."""
        text = "Hello hello HELLO"
        keywords = ["hello"]
        detected = detect_keywords(text, keywords, case_sensitive=True)
        assert detected == ["hello"]

    def test_detect_keywords_no_duplicates(self):
        """Test duplicates are removed."""
        text = "hello hello hello"
        keywords = ["hello"]
        detected = detect_keywords(text, keywords)
        assert detected == ["hello"]

    def test_detect_keywords_empty(self):
        """Test empty inputs return empty."""
        assert detect_keywords("", ["hello"]) == []
        assert detect_keywords("hello", []) == []
        assert detect_keywords("", []) == []

    def test_detect_phrase_matches_basic(self):
        """Test phrase match detection."""
        text = "I love Python programming. Python is great."
        phrases = ["Python"]
        matches = detect_phrase_matches(text, phrases)
        assert len(matches) == 2
        assert matches[0][0] == "Python"

    def test_detect_phrase_matches_partial(self):
        """Test partial vs boundary matching."""
        text = "pythonic python"
        # Partial matches - 'python' appears twice (in 'pythonic' and as standalone)
        matches = detect_phrase_matches(text, ["python"], partial=True)
        assert len(matches) == 2
        # Word boundary matches - 'python' appears once as standalone word
        matches = detect_phrase_matches(text, ["python"], partial=False)
        assert len(matches) == 1

    def test_extract_keyword_context(self):
        """Test context extraction."""
        text = "The quick brown fox jumps over the lazy dog"
        context = extract_keyword_context(text, "fox", context_words=2)
        assert "brown" in context
        assert "fox" in context
        assert "jumps" in context

    def test_extract_keyword_context_not_found(self):
        """Test context when keyword not found."""
        text = "Hello world"
        context = extract_keyword_context(text, "missing")
        assert context == ""

    def test_build_keyword_pattern(self):
        """Test regex pattern building."""
        keywords = ["hello", "world"]
        pattern = build_keyword_pattern(keywords)
        assert "hello" in pattern
        assert "world" in pattern
        assert r"\b" in pattern  # word boundary

    def test_build_keyword_pattern_empty(self):
        """Test empty keywords return empty pattern."""
        assert build_keyword_pattern([]) == ""


class TestKeywordDetector:
    """Tests for KeywordDetector class."""

    def test_detect(self):
        """Test basic detection."""
        detector = KeywordDetector(["hello", "world"])
        detected = detector.detect("Say hello world")
        assert "hello" in detected
        assert "world" in detected

    def test_detect_new(self):
        """Test new keyword detection."""
        detector = KeywordDetector(["hello"])
        new1 = detector.detect_new("Say hello")
        assert new1 == ["hello"]
        new2 = detector.detect_new("Say hello again")
        assert new2 == []  # already seen

    def test_add_keyword(self):
        """Test adding keyword dynamically."""
        detector = KeywordDetector(["hello"])
        detector.add_keyword("world")
        assert "world" in detector.keywords

    def test_remove_keyword(self):
        """Test removing keyword."""
        detector = KeywordDetector(["hello", "world"])
        detector.remove_keyword("hello")
        assert "hello" not in detector.keywords
        assert "world" in detector.keywords

    def test_reset(self):
        """Test resetting seen keywords."""
        detector = KeywordDetector(["hello"])
        detector.detect_new("Say hello")
        assert detector.detect_new("Say hello") == []
        detector.reset()
        assert detector.detect_new("Say hello") == ["hello"]


class TestAudioDevice:
    """Tests for AudioDevice."""

    def test_audio_device_creation(self):
        """Test AudioDevice creation."""
        device = AudioDevice(
            index=0,
            name="Test Device",
            max_input_channels=2,
            default_sample_rate=44100.0,
        )
        assert device.index == 0
        assert device.name == "Test Device"
        assert device.max_input_channels == 2
        assert device.default_sample_rate == 44100.0

    def test_audio_device_is_input(self):
        """Test is_input method."""
        device = AudioDevice(index=0, name="Test", max_input_channels=2)
        assert device.is_input() is True

    def test_audio_device_is_output(self):
        """Test is_output method."""
        device = AudioDevice(index=0, name="Test", max_output_channels=2)
        assert device.is_output() is True


class TestAudioChunk:
    """Tests for AudioChunk."""

    def test_audio_chunk_creation(self):
        """Test AudioChunk creation."""
        data = b"\x00\x01\x02\x03"
        chunk = AudioChunk(data=data, sample_rate=16000, channels=1)
        assert len(chunk.data) == 4
        assert chunk.sample_rate == 16000
        assert chunk.channels == 1

    def test_audio_chunk_default_values(self):
        """Test AudioChunk default values."""
        chunk = AudioChunk(data=b"test", sample_rate=16000)
        assert chunk.channels == 1
        assert chunk.width == 2
        assert chunk.timestamp == 0


class TestStreamSTT:
    """Tests for StreamSTT."""

    def test_stt_config_defaults(self):
        """Test StreamSTTConfig defaults."""
        config = StreamSTTConfig(api_key="test-key")
        assert config.model == "nova-3"
        assert config.language == "en-US"
        assert config.sample_rate == 16000
        assert config.channels == 1
        assert config.interim_results is True
        assert config.punctuate is True

    def test_stt_config_custom(self):
        """Test StreamSTTConfig with custom values."""
        config = StreamSTTConfig(
            api_key="test-key",
            model="nova-2",
            sample_rate=44100,
            interim_results=False,
        )
        assert config.model == "nova-2"
        assert config.sample_rate == 44100
        assert config.interim_results is False

    @pytest.mark.asyncio
    async def test_send_audio_not_connected(self):
        """Test sending audio when not connected raises."""
        config = StreamSTTConfig(api_key="test-key")
        stt = StreamSTT(config)

        chunk = AudioChunk(data=b"test", sample_rate=16000, channels=1)
        with pytest.raises(STTError, match="Not connected"):
            await stt.send_audio(chunk)


class TestVoiceService:
    """Tests for VoiceService."""

    def test_service_default_state(self):
        """Test service starts inactive."""
        service = VoiceService()
        assert service.is_active is False

    def test_service_config(self):
        """Test service uses provided config."""
        config = VoiceConfig(model="nova-2", sample_rate=48000)
        service = VoiceService(config=config)
        assert service.config.model == "nova-2"
        assert service.config.sample_rate == 48000

    def test_service_default_config(self):
        """Test service creates default config if none provided."""
        service = VoiceService()
        assert service.config is not None
        assert service.config.model == "nova-3"

    @pytest.mark.asyncio
    async def test_stop_when_not_active(self):
        """Test stopping when not active is no-op."""
        service = VoiceService()
        service._is_active = False

        await service.stop()  # Should not raise


class TestListAudioDevices:
    """Tests for list_audio_devices."""

    def test_audio_device_creation(self):
        """Test AudioDevice creation."""
        device = AudioDevice(
            index=0,
            name="Test Device",
            max_input_channels=2,
            default_sample_rate=44100.0,
        )
        assert device.index == 0
        assert device.name == "Test Device"
        assert device.is_input() is True
        assert device.is_output() is False

    def test_audio_device_output(self):
        """Test AudioDevice with output."""
        device = AudioDevice(
            index=1,
            name="Output Device",
            max_output_channels=2,
            default_sample_rate=48000.0,
        )
        assert device.is_output() is True
        assert device.is_input() is False

    def test_list_devices_returns_list(self):
        """Test that list_audio_devices returns a list."""
        devices = list_audio_devices()
        assert isinstance(devices, list)
