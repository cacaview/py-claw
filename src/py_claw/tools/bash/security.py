"""Security analysis for bash commands using AST.

Provides command injection detection, zsh bypass prevention,
safe wrapper stripping, and environment variable whitelist checking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from py_claw.tools.bash.ast import (
    BashASTNode,
    get_words,
    has_command_group,
    has_compound_operators,
    has_pipeline,
    has_subshell,
)
from py_claw.tools.bash.parser import BashASTParser

# Severity levels
ShellSeverity = Literal["critical", "high", "medium", "low", "safe"]


class CommandClass(str, Enum):
    """Command classification."""

    FILE_OP = "file_operation"
    NETWORK = "network"
    SYSTEM = "system"
    PROCESS = "process"
    PERMISSION = "permission"
    SHELL_BUILTIN = "shell_builtin"
    SCRIPT = "script"
    UNKNOWN = "unknown"


# Safe wrappers that should be stripped before analysis
SAFE_WRAPPERS = {
    "sudo -n",  # Non-interactive sudo
    "timeout",  # Timeout wrapper
    "ionice",  # I/O priority
    "renice",  # Process priority
    "chrt",  # Scheduler priority
    "taskset",  # CPU affinity
    "strace",  # System call trace
    "ltrace",  # Library call trace
    "valgrind",  # Memory debugger
}

# Environment variable whitelist (variables that are safe to expand)
SAFE_ENV_VARS = {
    "HOME",
    "USER",
    "SHELL",
    "PATH",
    "PWD",
    "OLDPWD",
    "TERM",
    "LANG",
    "LC_ALL",
    "EDITOR",
    "VISUAL",
    "PAGER",
    "BROWSER",
    "GIT_EDITOR",
    "SVN_EDITOR",
    "KEEP",
    "HISTORY",
    "SECONDS",
    "RANDOM",
    "LINENO",
    "DIRSTACK",
    "EUID",
    "UID",
    "GID",
    "EGID",
    "GROUPS",
    "HOSTNAME",
    "HOSTTYPE",
    "VENDOR",
    "OSTYPE",
    "MACHTYPE",
    "ARCH",
    "BASH",
    "BASH_VERSION",
    "BASH_VERSINFO",
    "DIRSTACK",
    "EUID",
    "FCEDIT",
    "FIGNORE",
    "FUNCNAME",
    "GLOBIGNORE",
    "GROUPS",
    "HISTCONTROL",
    "HISTFILE",
    "HISTFILESIZE",
    "HISTSIZE",
    "HISTTIMEFORMAT",
    "IFS",
    "INPUTRC",
    "LINENO",
    "MAIL",
    "MAILCHECK",
    "MAILPATH",
    "OPTERR",
    "OPTIND",
    "OSTYPE",
    "PIPESTATUS",
    "POSIXLY_CORRECT",
    "PROMPT_COMMAND",
    "PS1",
    "PS2",
    "PS3",
    "PS4",
    "SHELLOPTS",
    "SHLVL",
    "TIMEFORMAT",
    "TMOUT",
    "TMPDIR",
    "UID",
}


@dataclass
class BashSecurityResult:
    """Result of bash security analysis."""

    # Overall safety
    is_safe: bool
    severity: ShellSeverity
    severity_score: int  # 0-4 mapping to safe/low/medium/high/critical

    # Specific findings
    has_injection: bool
    injection_type: str | None
    injection_details: str | None

    has_zsh_bypass: bool
    zsh_bypass_details: str | None

    has_dangerous_patterns: bool
    dangerous_patterns: list[str]

    is_safe_wrapper: bool
    stripped_command: str | None

    # Env var issues
    unsafe_env_vars: list[str]

    # Command classification
    command_class: CommandClass
    is_network_command: bool
    is_file_destructive: bool

    # Additional details
    warnings: list[str]
    safe_wrappers_stripped: list[str]


def check_command_injection(command: str) -> tuple[bool, str | None, str | None]:
    """Check for command injection patterns.

    Args:
        command: Bash command string

    Returns:
        Tuple of (has_injection, injection_type, details)
    """
    # Check for classic injection patterns
    injection_patterns = [
        # Command substitution injection (only when unquoted or suspicious)
        (r"\$\([^)]+\)", "command_substitution", "$() command substitution"),
        (r"`[^`]+`", "backtick_substitution", "Backtick command substitution"),
        # Quote escape — semicolon after closing quote (injection attempt)
        (r"'\s*;\s*'", "quote_escape_injection", "Quote escape pattern for injection"),
        # Newline injection
        (r"\n\s*\w+", "newline_injection", "Newline used to inject additional command"),
    ]

    for pattern, inj_type, details in injection_patterns:
        if re.search(pattern, command):
            return True, inj_type, details

    return False, None, None


def check_zsh_bypass(command: str) -> tuple[bool, str | None]:
    """Check for zsh bypass patterns.

    Zsh can enable certain options that bypass security restrictions
    in bash, such as glob expansion in strings.

    Args:
        command: Bash command string

    Returns:
        Tuple of (has_bypass, details)
    """
    # Zsh-specific patterns that could bypass security
    zsh_bypass_patterns = [
        # Glob in double quotes (enabled by EXTENDED_GLOB in zsh)
        (r'"\*.+"', "zsh_extended_glob"),
        # Recursive glob
        (r"\*\*/", "zsh_recursive_glob"),
        # History expansion
        (r"![!a-z]", "zsh_history_expansion"),
        # Process substitution bypass
        (r"<\(\w+\)", "zsh_process_sub"),
    ]

    for pattern, details in zsh_bypass_patterns:
        if re.search(pattern, command):
            return True, details

    return False, None


def strip_safe_wrapper(command: str) -> tuple[str, list[str]]:
    """Strip known safe wrappers from command.

    Args:
        command: Bash command string

    Returns:
        Tuple of (stripped_command, wrappers_stripped)
    """
    stripped = []
    result = command.strip()

    # Known safe wrapper patterns
    for wrapper in SAFE_WRAPPERS:
        if result.startswith(wrapper):
            rest = result[len(wrapper) :].strip()
            # Accept: rest is empty (wrapper alone), starts with - (flags),
            # or is a timeout/sudo-style numeric argument followed by command
            if not rest or rest.startswith("-") or (rest and rest[0].isdigit()):
                stripped.append(wrapper)
                result = rest
                break

    # Check for sudo with specific safe flags
    sudo_match = re.match(r"sudo\s+(-n\s+)?(\S+)", result)
    if sudo_match:
        # Keep sudo -n but potentially flag the target command
        if sudo_match.group(1):  # had -n flag
            if "sudo -n" not in stripped:
                stripped.append("sudo -n")
        result = sudo_match.group(2) if sudo_match.group(2) else result

    return result.strip(), stripped


def check_env_whitelist(command: str) -> list[str]:
    """Check for unsafe environment variable expansion.

    Args:
        command: Bash command string

    Returns:
        List of unsafe environment variable names
    """
    unsafe_vars = []

    # Find all ${VAR} or $VAR expansion patterns
    env_pattern = r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"
    matches = re.findall(env_pattern, command)

    for var in matches:
        if var not in SAFE_ENV_VARS and var not in ("LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES"):
            unsafe_vars.append(var)

    # Also detect bare VAR=value assignments (unsafe env vars before command)
    assign_pattern = r"(?:^|\s)([A-Z_][A-Z0-9_]*)=[^\s]+"
    assign_matches = re.findall(assign_pattern, command)
    for var in assign_matches:
        if var not in SAFE_ENV_VARS and var not in unsafe_vars:
            unsafe_vars.append(var)

    return unsafe_vars


def classify_command(command: str) -> tuple[CommandClass, bool, bool]:
    """Classify a bash command.

    Args:
        command: Bash command string

    Returns:
        Tuple of (class, is_network, is_destructive)
    """
    if not command.strip():
        return CommandClass.UNKNOWN, False, False

    # Strip leading/trailing quotes to get clean command name
    stripped = command.strip()
    if stripped.startswith(("'", '"')):
        quote = stripped[0]
        end = stripped.find(quote, 1)
        if end > 0:
            stripped = stripped[1:end]

    cmd_first = stripped.split()[0].lower()

    # Network commands
    network_commands = {
        "curl", "wget", "nc", "netcat", "ncat", "ssh", "scp",
        "sftp", "rsync", "ftp", "telnet",
    }
    if cmd_first in network_commands:
        return CommandClass.NETWORK, True, False

    # File destructive commands
    destructive_commands = {
        "rm", "rmdir", "mkfs", "dd", "fdisk", "parted", "mke2fs",
    }
    if cmd_first in destructive_commands:
        return CommandClass.FILE_OP, False, True

    # File operations
    file_commands = {
        "cp", "mv", "ln", "cat", "chmod", "chown", "chgrp",
        "touch", "mkdir",
    }
    if cmd_first in file_commands:
        return CommandClass.FILE_OP, False, False

    # Process commands
    process_commands = {"kill", "killall", "pkill", "ps", "top", "htop"}
    if cmd_first in process_commands:
        return CommandClass.PROCESS, False, False

    # System commands
    system_commands = {
        "shutdown", "reboot", "halt", "poweroff", "init", "systemctl", "service",
    }
    if cmd_first in system_commands:
        return CommandClass.SYSTEM, False, False

    # Permission commands
    permission_commands = {"sudo", "su", "chmod", "chown", "chgrp", "passwd"}
    if cmd_first in permission_commands:
        return CommandClass.PERMISSION, False, False

    # Shell builtins
    shell_builtins = {
        "cd", "export", "source", "alias", "echo", "printf", "read",
        "set", "unset", "shift", "exit", "return", "break", "continue",
        "eval", "exec", "test",
    }
    if cmd_first in shell_builtins:
        return CommandClass.SHELL_BUILTIN, False, False

    return CommandClass.UNKNOWN, False, False


def analyze_command_security(command: str) -> BashSecurityResult:
    """Perform comprehensive security analysis on a bash command.

    Args:
        command: Bash command string

    Returns:
        BashSecurityResult with detailed findings
    """
    warnings = []

    # Parse the command
    parser = BashASTParser()
    ast = parser.parse(command)

    # Strip safe wrappers
    stripped_cmd, wrappers_stripped = strip_safe_wrapper(command)
    stripped_ast = parser.parse(stripped_cmd) if stripped_cmd else None

    # Check injection
    has_injection, inj_type, inj_details = check_command_injection(command)

    # Check zsh bypass
    has_zsh_bypass, zsh_details = check_zsh_bypass(command)

    # Check env whitelist
    unsafe_env = check_env_whitelist(command)

    # Classify command
    cmd_class, is_network, is_destructive = classify_command(stripped_cmd)

    # Check for dangerous patterns from AST
    dangerous = []
    if ast:
        # Check compound operators
        if has_compound_operators(ast):
            dangerous.append("compound_operators")

        # Check pipelines
        if has_pipeline(ast):
            dangerous.append("pipeline")

        # Check subshell
        if has_subshell(ast):
            dangerous.append("subshell")

        # Check command group
        if has_command_group(ast):
            dangerous.append("command_group")

        # Check for command substitution
        for node in ast.find_all("DOLLAR_PAREN"):
            dangerous.append("command_substitution")
            break

        for node in ast.find_all("BACKTICK"):
            dangerous.append("backtick_substitution")
            break

    # Check for dangerous prefixes
    dangerous_prefixes = [
        "rm -rf /",
        "rm -rf /usr",
        "rm -rf /bin",
        "dd if=",
        "mkfs.",
        "> /dev/sd",
        "chmod -R 777 /",
    ]
    for prefix in dangerous_prefixes:
        if stripped_cmd.startswith(prefix):
            dangerous.append(f"dangerous_prefix:{prefix}")

    # Determine severity
    severity = "safe"
    severity_score = 0

    if has_injection:
        severity = "critical"
        severity_score = 4
    elif has_zsh_bypass:
        severity = "high"
        severity_score = 3
    elif is_destructive and dangerous:
        severity = "high"
        severity_score = 3
    elif dangerous:
        severity = "medium"
        severity_score = 2
    elif unsafe_env:
        severity = "low"
        severity_score = 1

    is_safe = severity == "safe" and not dangerous

    return BashSecurityResult(
        is_safe=is_safe,
        severity=severity,
        severity_score=severity_score,
        has_injection=has_injection,
        injection_type=inj_type,
        injection_details=inj_details,
        has_zsh_bypass=has_zsh_bypass,
        zsh_bypass_details=zsh_details,
        has_dangerous_patterns=len(dangerous) > 0,
        dangerous_patterns=dangerous,
        is_safe_wrapper=len(wrappers_stripped) > 0,
        stripped_command=stripped_cmd if wrappers_stripped else None,
        unsafe_env_vars=unsafe_env,
        command_class=cmd_class,
        is_network_command=is_network,
        is_file_destructive=is_destructive,
        warnings=warnings,
        safe_wrappers_stripped=wrappers_stripped,
    )
