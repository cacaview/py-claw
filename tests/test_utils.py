"""
Tests for py_claw/utils module.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from py_claw.utils.errors import (
    ErrorContext,
    error_message,
    get_error_context,
    CliError,
    ConfigError,
    ValidationError,
    is_user_facing_error,
    format_error_for_display,
)
from py_claw.utils.json import (
    json_parse,
    json_stringify,
    safe_json_parse,
    is_json_string,
    normalize_json_key,
)
from py_claw.utils.path import (
    normalize_path,
    is_absolute_path,
    join_paths,
    get_home_dir,
    ensure_dir_exists,
    is_subpath,
    windows_to_posix_path,
    posix_to_windows_path,
    path_to_uri,
    uri_to_path,
)
from py_claw.utils.env import (
    EnvInfo,
    get_env_info,
    is_ci,
    is_test,
    is_production,
    is_development,
    get_env_bool,
    get_env_int,
    get_env_str,
    is_env_truthy,
    get_claude_config_dir,
)


class TestErrorUtils:
    """Tests for error utilities."""

    def test_error_message_from_exception(self):
        """Test extracting message from exception."""
        exc = ValueError("test error")
        assert error_message(exc) == "test error"

    def test_error_message_from_string(self):
        """Test extracting message from string."""
        assert error_message("plain string error") == "plain string error"

    def test_error_context_from_exception(self):
        """Test creating ErrorContext from exception."""
        exc = ValueError("test error")
        ctx = ErrorContext.from_exception(exc)
        assert ctx.message == "test error"
        assert ctx.error_type == "ValueError"
        assert ctx.stack_trace is not None

    def test_cli_error_with_exit_code(self):
        """Test CliError with exit code."""
        err = CliError("test", exit_code=42)
        assert str(err) == "test"
        assert err.exit_code == 42

    def test_config_error_inheritance(self):
        """Test ConfigError inherits from CliError."""
        err = ConfigError("config issue")
        assert isinstance(err, CliError)
        assert isinstance(err, Exception)

    def test_validation_error_inheritance(self):
        """Test ValidationError inherits from CliError."""
        err = ValidationError("invalid input")
        assert isinstance(err, CliError)

    def test_is_user_facing_error(self):
        """Test user-facing error detection."""
        assert is_user_facing_error(ValueError("test"))
        assert not is_user_facing_error(KeyboardInterrupt())
        assert not is_user_facing_error(SystemExit())

    def test_format_error_for_display(self):
        """Test error formatting."""
        assert "test" in format_error_for_display(ValueError("test"))


class TestJsonUtils:
    """Tests for JSON utilities."""

    def test_json_parse_valid(self):
        """Test parsing valid JSON."""
        result = json_parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_parse_invalid(self):
        """Test parsing invalid JSON raises error."""
        with pytest.raises(json.JSONDecodeError):
            json_parse("not json")

    def test_json_stringify(self):
        """Test serializing to JSON."""
        result = json_stringify({"key": "value"})
        assert '"key"' in result

    def test_json_stringify_with_indent(self):
        """Test serializing with indentation."""
        result = json_stringify({"key": "value"}, indent=2)
        assert "\n" in result

    def test_safe_json_parse_valid(self):
        """Test safe parsing with valid JSON."""
        result = safe_json_parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_safe_json_parse_invalid(self):
        """Test safe parsing with invalid JSON returns None."""
        assert safe_json_parse("not json") is None

    def test_safe_json_parse_with_default(self):
        """Test safe parsing with custom default."""
        assert safe_json_parse("not json", default={}) == {}

    def test_is_json_string(self):
        """Test JSON string detection."""
        assert is_json_string('{"key": "value"}')
        assert not is_json_string("not json")
        assert not is_json_string("")

    def test_normalize_json_key(self):
        """Test JSON key normalization."""
        assert normalize_json_key("path/to/key") == "path/to/key"
        assert normalize_json_key("path\\to\\key") == "path/to/key"


class TestPathUtils:
    """Tests for path utilities."""

    def test_normalize_path_string(self):
        """Test normalizing a string path."""
        result = normalize_path(".")
        assert isinstance(result, Path)

    def test_normalize_path_expands_user(self):
        """Test that normalize_path expands ~."""
        result = normalize_path("~")
        assert "~" not in str(result)

    def test_is_absolute_path(self):
        """Test absolute path detection."""
        # Unix-style absolute path (only works on Unix)
        if sys.platform != "win32":
            assert is_absolute_path("/usr/bin")
        # Windows-style absolute path
        assert is_absolute_path("C:\\Users") or is_absolute_path("C:/Users")
        assert not is_absolute_path("relative/path")

    def test_join_paths(self):
        """Test joining path components."""
        result = join_paths("a", "b", "c")
        assert "a" in str(result)
        assert "b" in str(result)
        assert "c" in str(result)

    def test_get_home_dir(self):
        """Test getting home directory."""
        home = get_home_dir()
        assert home.exists()
        assert home.is_dir()

    def test_ensure_dir_exists(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test" / "nested"
            result = ensure_dir_exists(test_dir)
            assert result.exists()
            assert result.is_dir()

    def test_is_subpath(self):
        """Test subpath detection."""
        home = get_home_dir()
        assert is_subpath(home / "file.txt", home)
        assert not is_subpath(Path("/other"), home)

    def test_windows_to_posix_path(self):
        """Test Windows to POSIX conversion."""
        assert windows_to_posix_path("C:\\Users\\test") == "C:/Users/test"
        assert windows_to_posix_path("D:\\a\\b") == "D:/a/b"

    def test_posix_to_windows_path(self):
        """Test POSIX to Windows conversion."""
        assert posix_to_windows_path("C:/Users/test") == "C:\\Users\\test"
        assert posix_to_windows_path("D:/a/b") == "D:\\a\\b"

    def test_path_to_uri(self):
        """Test converting path to URI."""
        uri = path_to_uri(Path("/tmp/test.txt"))
        assert uri.startswith("file://")

    def test_uri_to_path(self):
        """Test converting URI to path."""
        path = uri_to_path("file:///tmp/test.txt")
        assert "test.txt" in str(path)


class TestEnvUtils:
    """Tests for environment utilities."""

    def test_get_env_info(self):
        """Test getting environment info."""
        info = get_env_info()
        assert isinstance(info, EnvInfo)
        assert isinstance(info.is_ci, bool)
        assert isinstance(info.is_test, bool)
        assert isinstance(info.platform, str)
        assert info.is_windows == (os.name == "nt")
        assert info.is_macos == (sys.platform == "darwin")
        assert info.is_linux == (sys.platform.startswith("linux"))

    def test_is_ci(self):
        """Test CI detection."""
        # Can't easily mock sys.modules, just check it returns a bool
        result = is_ci()
        assert isinstance(result, bool)

    def test_is_test(self):
        """Test test mode detection."""
        result = is_test()
        assert isinstance(result, bool)

    def test_is_production(self):
        """Test production mode detection."""
        result = is_production()
        assert isinstance(result, bool)

    def test_is_development(self):
        """Test development mode detection."""
        result = is_development()
        assert isinstance(result, bool)

    def test_get_env_bool(self):
        """Test getting boolean env var."""
        os.environ["TEST_BOOL_TRUE"] = "true"
        os.environ["TEST_BOOL_1"] = "1"
        os.environ["TEST_BOOL_FALSE"] = "false"
        try:
            assert get_env_bool("TEST_BOOL_TRUE") is True
            assert get_env_bool("TEST_BOOL_1") is True
            assert get_env_bool("TEST_BOOL_FALSE") is False
            assert get_env_bool("NONEXISTENT") is False
            assert get_env_bool("NONEXISTENT", default=True) is True
        finally:
            os.environ.pop("TEST_BOOL_TRUE", None)
            os.environ.pop("TEST_BOOL_1", None)
            os.environ.pop("TEST_BOOL_FALSE", None)

    def test_get_env_int(self):
        """Test getting integer env var."""
        os.environ["TEST_INT"] = "42"
        try:
            assert get_env_int("TEST_INT") == 42
            assert get_env_int("NONEXISTENT") is None
            assert get_env_int("NONEXISTENT", 0) == 0
            assert get_env_int("TEST_INT_INVALID") is None
        finally:
            os.environ.pop("TEST_INT", None)

    def test_get_env_str(self):
        """Test getting string env var."""
        os.environ["TEST_STR"] = "hello"
        try:
            assert get_env_str("TEST_STR") == "hello"
            assert get_env_str("NONEXISTENT") == ""
            assert get_env_str("NONEXISTENT", "default") == "default"
        finally:
            os.environ.pop("TEST_STR", None)

    def test_is_env_truthy(self):
        """Test env truthy checking."""
        os.environ["TEST_TRUTHY_1"] = "1"
        os.environ["TEST_TRUTHY_TRUE"] = "true"
        os.environ["TEST_TRUTHY_0"] = "0"
        try:
            assert is_env_truthy("TEST_TRUTHY_1") is True
            assert is_env_truthy("TEST_TRUTHY_TRUE") is True
            assert is_env_truthy("TEST_TRUTHY_0") is False
            assert is_env_truthy("NONEXISTENT") is False
        finally:
            os.environ.pop("TEST_TRUTHY_1", None)
            os.environ.pop("TEST_TRUTHY_TRUE", None)
            os.environ.pop("TEST_TRUTHY_0", None)

    def test_get_claude_config_dir(self):
        """Test getting Claude config directory."""
        config_dir = get_claude_config_dir()
        assert config_dir is not None
        assert "claude" in config_dir.lower()
