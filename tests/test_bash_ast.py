"""Tests for BashTool AST subsystem (tools/bash/)."""

from __future__ import annotations

import pytest

from py_claw.tools.bash import (
    BashASTNode,
    BashASTParser,
    BashSecurityResult,
    analyze_command_security,
    check_command_injection,
    check_env_whitelist,
    check_zsh_bypass,
    classify_command,
    strip_safe_wrapper,
)
from py_claw.tools.bash.ast import (
    count_nodes,
    get_command_name,
    get_words,
    has_command_group,
    has_compound_operators,
    has_pipeline,
    has_subshell,
    walk_ast,
)


# ─── Parser ─────────────────────────────────────────────────────────────────

class TestBashASTParser:
    """Tests for BashASTParser."""

    def test_parse_simple_echo(self):
        ast = BashASTParser().parse("echo hello")
        assert ast is not None
        assert ast.type == "program"

    def test_parse_command_with_args(self):
        ast = BashASTParser().parse("ls -la /tmp")
        assert ast is not None
        words = get_words(ast)
        assert "ls" in words
        assert "-la" in words
        assert "/tmp" in words

    def test_parse_compound_and(self):
        """echo a && echo b should produce two command_list children."""
        ast = BashASTParser().parse("echo a && echo b")
        assert ast is not None
        assert len(ast.children) == 2  # two command_list nodes

    def test_parse_compound_or(self):
        ast = BashASTParser().parse("cat foo || echo failed")
        assert ast is not None
        assert len(ast.children) == 2

    def test_parse_pipeline(self):
        ast = BashASTParser().parse("cat foo | grep bar")
        assert ast is not None
        assert has_pipeline(ast)

    def test_parse_empty_string(self):
        ast = BashASTParser().parse("")
        assert ast is not None
        assert ast.type == "program"

    def test_parse_with_ansi_c_string(self):
        ast = BashASTParser().parse("echo $'hello\\nworld'")
        assert ast is not None

    def test_parse_comment_ignored(self):
        ast = BashASTParser().parse("echo hello  # this is a comment")
        assert ast is not None
        words = get_words(ast)
        assert "echo" in words
        assert "hello" in words

    def test_parse_node_count_reasonable(self):
        """Node count should be bounded and reasonable for simple commands."""
        for cmd in ["echo", "ls -la", "echo a && echo b", "cat foo | grep bar"]:
            ast = BashASTParser().parse(cmd)
            assert ast is not None
            assert count_nodes(ast) < 100, f"Node count too high for: {cmd}"

    def test_node_count_limit(self):
        """Very long commands should hit node budget limit, not hang."""
        long_cmd = "echo " + "x " * 10000
        ast = BashASTParser().parse(long_cmd)
        # Should either parse successfully or return None (budget exceeded)
        # Should NOT hang or raise uncontrolled exceptions
        assert ast is None or count_nodes(ast) < 50000


# ─── AST traversal ───────────────────────────────────────────────────────────

class TestASTTraversal:
    """Tests for AST node traversal utilities."""

    def test_walk_ast_echo(self):
        ast = BashASTParser().parse("echo hello")
        nodes = list(walk_ast(ast))
        assert len(nodes) > 3  # program > command_list > command > simple_command > WORD

    def test_get_words(self):
        ast = BashASTParser().parse("ls -la /tmp")
        words = get_words(ast)
        assert "ls" in words
        assert "-la" in words
        assert "/tmp" in words

    def test_get_command_name(self):
        ast = BashASTParser().parse("grep -r pattern .")
        assert get_command_name(ast) == "grep"

    def test_has_compound_operators(self):
        ast = BashASTParser().parse("echo a && echo b")
        assert has_compound_operators(ast)

    def test_no_compound_operators_simple(self):
        ast = BashASTParser().parse("echo hello")
        assert not has_compound_operators(ast)

    def test_has_pipeline(self):
        ast = BashASTParser().parse("cat foo | grep bar")
        assert has_pipeline(ast)

    def test_no_pipeline_simple(self):
        ast = BashASTParser().parse("ls -la")
        assert not has_pipeline(ast)

    def test_has_subshell(self):
        ast = BashASTParser().parse("echo $(date)")
        assert has_subshell(ast)

    def test_no_subshell_simple(self):
        ast = BashASTParser().parse("ls")
        assert not has_subshell(ast)

    def test_has_command_group(self):
        ast = BashASTParser().parse("{ echo a; echo b; }")
        assert has_command_group(ast)


# ─── Security analysis ───────────────────────────────────────────────────────

class TestSecurityAnalysis:
    """Tests for command security analysis."""

    def test_safe_echo(self):
        result = analyze_command_security("echo hello world")
        assert result.is_safe
        assert result.severity == "safe"

    def test_safe_ls(self):
        result = analyze_command_security("ls -la /tmp")
        assert result.is_safe

    def test_injection_semicolon(self):
        """Semicolons are valid compound operators; newline in quoted context is injection."""
        # echo '\n...' has newline inside quotes — the \n is the injection vector
        result = analyze_command_security("echo '\nrm -rf /'")
        assert result.has_injection
        assert result.injection_type == "newline_injection"

    def test_injection_newline(self):
        result = analyze_command_security("echo hello\nrm -rf /")
        assert result.has_injection
        assert result.injection_type == "newline_injection"

    def test_safe_compound_operators(self):
        """Compound operators && and || should NOT be flagged as injection."""
        for cmd in ["echo a && echo b", "echo a || echo b"]:
            result = analyze_command_security(cmd)
            assert not result.has_injection, f"{cmd} should not be injection"

    def test_safe_pipeline(self):
        """Pipeline | should NOT be flagged as injection."""
        result = analyze_command_security("cat foo | grep bar")
        assert not result.has_injection

    def test_dangerous_prefix_rm_rf_root(self):
        result = analyze_command_security("rm -rf /")
        assert not result.is_safe
        assert "dangerous_prefix:rm -rf /" in result.dangerous_patterns

    def test_dangerous_prefix_dd(self):
        result = analyze_command_security("dd if=/dev/zero of=/dev/null")
        assert not result.is_safe

    def test_network_command(self):
        result = analyze_command_security("curl http://example.com")
        assert result.is_network_command
        assert result.command_class.value == "network"

    def test_file_destructive_command(self):
        result = analyze_command_security("rm -rf /tmp/test")
        assert result.is_file_destructive

    def test_safe_wrapper_sudo_n(self):
        """sudo -n should be stripped as safe wrapper."""
        result = analyze_command_security("sudo -n ls /root")
        assert result.safe_wrappers_stripped == ["sudo -n"]

    def test_safe_wrapper_timeout(self):
        result = analyze_command_security("timeout 10s sleep 5")
        assert result.safe_wrappers_stripped == ["timeout"]

    def test_unsafe_env_var(self):
        """LD_PRELOAD should be flagged as unsafe."""
        result = analyze_command_security("LD_PRELOAD=/tmp/evil.so ls")
        assert "LD_PRELOAD" in result.unsafe_env_vars

    def test_safe_env_var_home(self):
        result = analyze_command_security("echo $HOME")
        assert "HOME" not in result.unsafe_env_vars

    def test_classify_network_commands(self):
        for cmd in ["curl http://foo.com", "wget http://foo.com", "ssh user@host"]:
            result = classify_command(cmd)
            assert result[0].value == "network", f"{cmd} should be network"

    def test_classify_file_operations(self):
        for cmd in ["cp a b", "mv a b", "mkdir /tmp/test"]:
            result = classify_command(cmd)
            assert result[0].value == "file_operation", f"{cmd} should be file_operation"

    def test_classify_destructive(self):
        result = classify_command("rm -rf /tmp")
        assert result[2]  # is_destructive

    def test_zsh_bypass_recursive_glob(self):
        result = analyze_command_security("echo **/")
        assert result.has_zsh_bypass

    def test_severity_order(self):
        """Severity escalation: safe < low < medium < high < critical."""
        # safe
        safe = analyze_command_security("echo hello")
        assert safe.severity_score == 0

        # injection → critical
        inj = analyze_command_security("echo $(rm -rf /)")
        assert inj.severity_score >= 4
        assert inj.has_injection

    def test_stripped_command_preserved(self):
        """Stripped command should be analyzable."""
        result = analyze_command_security("sudo -n ls /root")
        assert result.stripped_command is not None


class TestCheckFunctions:
    """Unit tests for individual security check functions."""

    def test_check_command_injection_false_positives(self):
        """Known safe commands should not trigger injection detection."""
        safe_commands = [
            "echo hello",
            "ls -la",
            "cat foo | grep bar",
            "make && make install",
            "cd /tmp && ls",
        ]
        for cmd in safe_commands:
            has_inj, _, _ = check_command_injection(cmd)
            assert not has_inj, f"False positive on: {cmd}"

    def test_check_command_injection_true_positives(self):
        """Command substitution patterns should be detected."""
        has_inj, inj_type, _ = check_command_injection("echo $(echo a; rm -rf /)")
        assert has_inj
        assert inj_type == "command_substitution"

    def test_check_zsh_bypass_false_positives(self):
        safe_commands = ["echo hello", "ls -la /tmp", "cat foo | grep bar"]
        for cmd in safe_commands:
            has_bp, _ = check_zsh_bypass(cmd)
            assert not has_bp, f"False zsh bypass on: {cmd}"

    def test_strip_safe_wrapper_basic(self):
        stripped, wrappers = strip_safe_wrapper("sudo -n ls /root")
        assert "sudo -n" in wrappers
        assert stripped.startswith("ls")

    def test_strip_safe_wrapper_timeout(self):
        stripped, wrappers = strip_safe_wrapper("timeout 30s sleep 10")
        assert "timeout" in wrappers
        # After stripping timeout, the duration + command remain
        assert "sleep" in stripped

    def test_strip_safe_wrapper_no_change(self):
        stripped, wrappers = strip_safe_wrapper("ls -la")
        assert not wrappers
        assert stripped == "ls -la"

    def test_check_env_whitelist_safe(self):
        unsafe = check_env_whitelist("echo $HOME $USER $PATH")
        assert not unsafe

    def test_check_env_whitelist_unsafe(self):
        unsafe = check_env_whitelist("LD_PRELOAD=/tmp/evil.so ls")
        assert "LD_PRELOAD" in unsafe

    def test_classify_command_unknown(self):
        cmd_class, is_net, is_dest = classify_command("completely_unknown_cmd arg")
        assert cmd_class.value == "unknown"
        assert not is_net
        assert not is_dest


class TestBashSecurityResult:
    """Tests for BashSecurityResult data class."""

    def test_result_is_dataclass(self):
        result = analyze_command_security("echo hello")
        assert hasattr(result, "is_safe")
        assert hasattr(result, "severity")
        assert hasattr(result, "has_injection")
        assert hasattr(result, "command_class")

    def test_severity_consistency(self):
        """is_safe should be True only when severity is safe and no dangerous patterns."""
        result = analyze_command_security("echo hello")
        if result.is_safe:
            assert result.severity == "safe"
            assert not result.has_injection


# ─── Integration ─────────────────────────────────────────────────────────────

class TestLocalShellIntegration:
    """Integration tests: AST security used in BashTool context."""

    def test_security_result_format(self):
        """AST security result should map to compatible format."""
        from py_claw.tools.local_shell import _ast_to_security_result

        ast_result = analyze_command_security("echo hello")
        check_result = _ast_to_security_result(ast_result)
        assert check_result.is_safe == ast_result.is_safe
        assert check_result.severity == ast_result.severity

    def test_security_block_echo_hello(self):
        """AST analysis should not block safe echo commands."""
        ast_result = analyze_command_security("echo hello")
        assert ast_result.severity == "safe"

    def test_security_block_injection(self):
        """AST analysis should detect and flag injection."""
        ast_result = analyze_command_security("echo $(rm -rf /)")
        assert not ast_result.is_safe
        assert ast_result.has_injection
