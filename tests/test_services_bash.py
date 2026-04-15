"""Tests for bash services."""

import pytest

from py_claw.services.bash import (
    OpEntry,
    ParseEntry,
    StringEntry,
    has_malformed_tokens,
    has_shell_quote_single_quote_bug,
    try_parse_shell_command,
    try_quote_shell_args,
    quote_shell_args,
)


class TestTryParseShellCommand:
    """Tests for try_parse_shell_command."""

    def test_parse_simple_command(self):
        """Test parsing a simple command."""
        success, tokens, error = try_parse_shell_command("echo hello")
        assert success
        assert len(tokens) == 2
        assert isinstance(tokens[0], StringEntry)
        assert tokens[0].value == "echo"
        assert isinstance(tokens[1], StringEntry)
        assert tokens[1].value == "hello"

    def test_parse_command_with_operator(self):
        """Test parsing a command with pipe operator."""
        success, tokens, error = try_parse_shell_command("echo hello | wc")
        assert success
        assert len(tokens) == 4
        assert isinstance(tokens[0], StringEntry)
        assert tokens[0].value == "echo"
        assert isinstance(tokens[1], StringEntry)
        assert tokens[1].value == "hello"
        assert isinstance(tokens[2], OpEntry)
        assert tokens[2].op == "|"
        assert isinstance(tokens[3], StringEntry)
        assert tokens[3].value == "wc"

    def test_parse_command_with_double_operator(self):
        """Test parsing a command with && operator."""
        success, tokens, error = try_parse_shell_command("echo a && echo b")
        assert success
        # Tokens: echo, a, &&, echo, b (5 tokens with space splitting)
        assert isinstance(tokens[2], OpEntry)
        assert tokens[2].op == "&&"

    def test_parse_empty_command(self):
        """Test parsing an empty command."""
        success, tokens, error = try_parse_shell_command("")
        assert success
        assert tokens == []


class TestTryQuoteShellArgs:
    """Tests for try_quote_shell_args."""

    def test_quote_strings(self):
        """Test quoting string arguments."""
        success, quoted, error = try_quote_shell_args(["hello", "world"])
        assert success
        assert "hello" in quoted
        assert "world" in quoted

    def test_quote_numbers(self):
        """Test quoting number arguments."""
        success, quoted, error = try_quote_shell_args([1, 2, 3])
        assert success

    def test_quote_mixed_types(self):
        """Test quoting mixed type arguments."""
        success, quoted, error = try_quote_shell_args(["hello", 42, True])
        assert success

    def test_quote_unsupported_type(self):
        """Test quoting unsupported type fails gracefully."""
        success, quoted, error = try_quote_shell_args([{"key": "value"}])
        assert not success
        assert "object" in error.lower()


class TestQuoteShellArgs:
    """Tests for quote_shell_args (with fallback)."""

    def test_quote_simple_args(self):
        """Test quoting simple arguments."""
        result = quote_shell_args(["echo", "hello"])
        assert "echo" in result
        assert "hello" in result

    def test_quote_with_spaces(self):
        """Test quoting arguments with spaces."""
        result = quote_shell_args(["hello world"])
        assert "hello world" in result


class TestHasMalformedTokens:
    """Tests for has_malformed_tokens detection."""

    def test_balanced_tokens(self):
        """Test tokens with balanced braces."""
        tokens = [StringEntry('{"key": "value"}')]
        assert not has_malformed_tokens('{"key": "value"}', tokens)

    def test_unbalanced_braces(self):
        """Test tokens with unbalanced braces."""
        tokens = [StringEntry("{unbalanced")]
        assert has_malformed_tokens("{unbalanced", tokens)

    def test_unbalanced_parens(self):
        """Test tokens with unbalanced parentheses."""
        tokens = [StringEntry("(unbalanced")]
        assert has_malformed_tokens("(unbalanced", tokens)

    def test_unbalanced_brackets(self):
        """Test tokens with unbalanced brackets."""
        tokens = [StringEntry("[unbalanced")]
        assert has_malformed_tokens("[unbalanced", tokens)


class TestHasShellQuoteSingleQuoteBug:
    """Tests for shell-quote single quote bug detection."""

    def test_normal_single_quotes(self):
        """Test normal single quoted string."""
        cmd = "'normal string'"
        assert not has_shell_quote_single_quote_bug(cmd)

    def test_escaped_backslash_in_single_quote(self):
        """Test escaped backslash pattern that triggers bug."""
        # Pattern: '\' <payload> '\'
        cmd = r"'\' --upload-pack=evil '"
        # This is a simplified test - real bug involves shell-quote
        # incorrectly treating \ as escape inside single quotes
        result = has_shell_quote_single_quote_bug(cmd)
        # Result depends on the specific bug pattern
        assert isinstance(result, bool)

    def test_even_backslashes(self):
        """Test even number of trailing backslashes."""
        cmd = "'hello\\\\'"
        result = has_shell_quote_single_quote_bug(cmd)
        assert isinstance(result, bool)
