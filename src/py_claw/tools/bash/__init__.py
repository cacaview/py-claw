"""Bash tool AST parsing and security analysis.

This module provides tree-sitter compatible AST parsing for bash commands,
with security analysis capabilities including injection detection and
zsh bypass prevention.
"""

from __future__ import annotations

from py_claw.tools.bash.ast import (
    BashASTNode,
    get_command_name,
    get_redirects,
    get_words,
    has_command_group,
    has_compound_operators,
    has_pipeline,
    has_redirect,
    has_subshell,
    walk_ast,
)
from py_claw.tools.bash.parser import BashASTParser
from py_claw.tools.bash.security import (
    BashSecurityResult,
    analyze_command_security,
    check_command_injection,
    check_env_whitelist,
    check_zsh_bypass,
    classify_command,
    strip_safe_wrapper,
)

__all__ = [
    "BashASTNode",
    "BashASTParser",
    "BashSecurityResult",
    "analyze_command_security",
    "check_command_injection",
    "check_env_whitelist",
    "check_zsh_bypass",
    "classify_command",
    "get_command_name",
    "get_redirects",
    "get_words",
    "has_command_group",
    "has_compound_operators",
    "has_pipeline",
    "has_redirect",
    "has_subshell",
    "strip_safe_wrapper",
    "walk_ast",
]
