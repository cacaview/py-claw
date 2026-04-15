from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ShellSeverity = Literal["critical", "high", "medium", "low", "safe"]
ShellType = Literal["bash", "zsh", "sh", "dash", "posh", "powershell", "pwsh", "fish", "unknown"]

# (compiled_pattern, label, severity)
_SECURITY_PATTERNS: list[tuple[re.Pattern[str], str, ShellSeverity]] = [
    # critical
    (re.compile(r"(?<!-)\brm\s+(-[rf]+\s+)+/"), "rm_recursive_root", "critical"),
    (re.compile(r"\bdd\b.*\bif="), "dd_input_file", "critical"),
    (re.compile(r"\bmkfs\b"), "mkfs_command", "critical"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}"), "fork_bomb", "critical"),
    # high
    (re.compile(r"\bcurl\b.*\|\s*(?:sudo\s+)?sh"), "curl_pipe_sh", "high"),
    (re.compile(r"\bwget\b.*\|\s*(?:sudo\s+)?sh"), "wget_pipe_sh", "high"),
    (re.compile(r"\bfetch\b.*\|\s*(?:sudo\s+)?sh"), "fetch_pipe_sh", "high"),
    (re.compile(r"\|.*sudo\s+sh"), "pipe_sudo_sh", "high"),
    (re.compile(r"\|?\s*bash\s+-c\s+.*\|\s*sudo"), "bash_c_sudo", "high"),
    (re.compile(r"\bexec\s+"), "exec_command", "high"),
    (re.compile(r"\beval\s+"), "eval_command", "high"),
    (re.compile(r"\bsudo\s+su\b"), "sudo_su", "high"),
    (re.compile(r"\$\([^)]*\)\s*\|"), "command_substitution_pipe", "high"),
    (re.compile(r"`[^`]+`\s*\|"), "backtick_substitution_pipe", "high"),
    (re.compile(r"\bsh\s+-c\s+['\"]\s*;.*"), "sh_c_injection", "high"),
    (re.compile(r"\.\s*/\.\s*"), "dot_dot_slash", "high"),
    # medium
    (re.compile(r"zsh\s+(-c|-s)\b"), "zsh_shell", "medium"),
    (re.compile(r"\bsource\s+/dev/"), "source_dev_file", "medium"),
    (re.compile(r">\s*/proc/"), "write_proc", "medium"),
    (re.compile(r">\s*/sys/"), "write_sys", "medium"),
    (re.compile(r">\s*/dev/sd[a-z]"), "write_device", "medium"),
    (re.compile(r">>\s*/dev/sd[a-z]"), "append_device", "medium"),
    (re.compile(r"\bkill\s+-9\s+1\b"), "kill_init", "medium"),
    (re.compile(r"\bkill\s+-TERM\s+-1\b"), "kill_term_all", "medium"),
    # low
    (re.compile(r"\bchmod\s+(-R\s+)?777\s+/"), "chmod_777_root", "low"),
    (re.compile(r"\bchown\s+.*\s+-R\s+777\s+/"), "chown_777_root", "low"),
]

_DANGEROUS_PREFIXES: list[tuple[str, ShellSeverity]] = [
    ("> /dev/sd", "high"),
    (">> /dev/sd", "high"),
    ("> /dev/null", "low"),
    ("dd if=", "critical"),
    ("mkfs.", "critical"),
    ("rm -rf /", "critical"),
    ("rm -rf /usr", "critical"),
    ("rm -rf /bin", "critical"),
    ("rm -rf /lib", "critical"),
    ("chmod -R 777 /", "low"),
    ("chown -R 777 /", "low"),
]

_SEVERITY_ORDER: dict[ShellSeverity, int] = {
    "safe": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


@dataclass(frozen=True, slots=True)
class BashSecurityCheckResult:
    is_safe: bool
    shell_type: ShellType
    dangerous_patterns: list[str]
    warnings: list[str]
    severity: Literal["safe", "low", "medium", "high", "critical"]


def check_bash_security(command: str) -> BashSecurityCheckResult:
    """Analyze a bash command for security risks.

    This is a pattern-based heuristic analyzer, not a full AST-based analysis.
    It is intentionally conservative and may produce false positives.
    """
    cmd = command.strip()
    dangerous: list[str] = []
    max_severity: ShellSeverity = "safe"

    if not cmd:
        return BashSecurityCheckResult(
            is_safe=True,
            shell_type="bash",
            dangerous_patterns=[],
            warnings=[],
            severity="safe",
        )

    for pattern, label, severity in _SECURITY_PATTERNS:
        if pattern.search(cmd):
            dangerous.append(label)
            if _SEVERITY_ORDER.get(severity, 0) > _SEVERITY_ORDER.get(max_severity, 0):
                max_severity = severity

    for prefix, severity in _DANGEROUS_PREFIXES:
        if cmd.startswith(prefix) or f" {prefix}" in cmd:
            dangerous.append(f"prefix: {prefix}")
            if _SEVERITY_ORDER.get(severity, 0) > _SEVERITY_ORDER.get(max_severity, 0):
                max_severity = severity

    warnings: list[str] = []
    if re.search(r"\\$", cmd):
        warnings.append("line_continuation")

    shell_type = _detect_shell_type(cmd)
    if shell_type in ("zsh", "fish"):
        warnings.append(f"non_bash_shell: {shell_type}")

    severity: Literal["safe", "low", "medium", "high", "critical"] = max_severity
    if severity == "safe" and warnings:
        severity = "low"

    return BashSecurityCheckResult(
        is_safe=severity == "safe",
        shell_type=shell_type,
        dangerous_patterns=dangerous,
        warnings=warnings,
        severity=severity,
    )


def _detect_shell_type(command: str) -> ShellType:
    """Detect which shell the command is written for."""
    stripped = command.strip()
    if stripped.startswith("#!"):
        shebang = stripped.splitlines()[0]
        if "zsh" in shebang:
            return "zsh"
        if "bash" in shebang:
            return "bash"
        if "sh" in shebang:
            return "sh"
        if "dash" in shebang:
            return "dash"
        if "fish" in shebang:
            return "fish"
        if "pwsh" in shebang or "powershell" in shebang:
            return "pwsh"
    first_word = stripped.split()[0] if stripped else ""
    if first_word in ("zsh", "bash", "sh", "dash", "fish", "pwsh"):
        return first_word  # type: ignore[return-value]
    if first_word in ("powershell",):
        return "pwsh"
    return "bash"


# Commands that are safe to run in read-only contexts (low-risk)
_READ_ONLY_COMMANDS = frozenset({
    "cat", "head", "tail", "less", "more", "sort", "uniq", "wc",
    "cut", "paste", "column", "tr", "file", "stat", "diff",
    "awk", "strings", "hexdump", "od", "base64", "nl", "grep",
    "rg", "jq", "ls", "pwd", "whoami", "id", "date", "echo",
    "printf", "true", "false", "which", "type", "command", "builtin",
})

# Commands that are considered write/delete operations
_WRITE_COMMANDS = frozenset({
    "rm", "rmdir", "mv", "cp", "ln", "mkdir", "touch", "chmod",
    "chown", "chgrp", "dd", "mkfs", "mount", "umount", "del",
    "erase", "rd", "format",
})

# Paths that are always considered dangerous to modify
_DANGEROUS_WRITE_PATHS = (
    "/dev/sd",
    "/sys/",
    "/proc/",
    "/boot/",
    "/etc/fstab",
)


def check_path_security(command: str, cwd: str) -> tuple[bool, str | None]:
    """Check if a bash command accesses paths outside the allowed scope.

    Returns (is_safe, reason). Read-only commands are permitted to access any path.
    Write/delete commands that target paths outside cwd or home are flagged.
    Writes to dangerous system paths (/dev/sd, /sys/, /proc/, /boot/, /etc/fstab) are always blocked.
    Path traversal that escapes the resolved cwd is flagged.

    On Windows (or when cwd and target are on different drives), only the
    dangerous-system-path check is enforced, since cross-drive relative-to
    comparison is not meaningful.
    """
    import sys
    is_windows = sys.platform == "win32"

    resolved_cwd = Path(cwd).resolve()
    home = Path.home().resolve()

    cmd = _extract_command(command)
    if cmd in _READ_ONLY_COMMANDS:
        return True, None

    tokens = _extract_path_tokens(command)
    if not tokens:
        return True, None

    for token in tokens:
        if not token:
            continue
        expanded = os.path.expanduser(token)
        try:
            abs_path = Path(expanded).resolve()
        except (OSError, ValueError):
            continue

        abs_str = str(abs_path)

        # Always block writes to dangerous system paths
        # Check the original token (Unix-style) and the normalized resolved path
        token_norm = token.replace("\\", "/")
        abs_str_norm = abs_str.replace("\\", "/")
        for dangerous in _DANGEROUS_WRITE_PATHS:
            normalized_dangerous = dangerous.replace("\\", "/")
            if (
                abs_str_norm.startswith(normalized_dangerous)
                or abs_str_norm == normalized_dangerous.rstrip("/")
                or token_norm.startswith(normalized_dangerous)
            ):
                if _is_write_command(cmd):
                    return False, f"write to protected path: {token}"

        # On Windows, also check for Windows-specific dangerous paths
        # device names and critical system file locations
        if is_windows:
            import re as _re
            token_upper = token.upper()
            # Windows device names (NUL, CON, PRN, AUX, COM1, LPT1, etc.)
            if _re.match(r"^[A-Z]:?\\?(NUL|CON|PRN|AUX|COM[1-9]|LPT[1-9])(\.|\\|/|:|$)", token_upper, _re.IGNORECASE):
                if _is_write_command(cmd):
                    return False, f"write to Windows device: {token}"
            # Windows SAM/System hive writes
            if "SYSTEM32\\CONFIG\\SAM" in token_upper or "SYSTEM32\\CONFIG\\SYSTEM" in token_upper:
                if _is_write_command(cmd):
                    return False, f"write to protected Windows registry hive: {token}"

        # On Windows, skip cross-drive containment checks
        if is_windows:
            continue

        # Check if path is within cwd or home
        try:
            abs_path.relative_to(resolved_cwd)
        except ValueError:
            try:
                abs_path.relative_to(home)
            except ValueError:
                return False, f"path outside cwd/home: {abs_str}"

        # Check for path traversal that escapes cwd
        if ".." in abs_path.parts and abs_path.is_absolute():
            try:
                rel = abs_path.relative_to(resolved_cwd)
                if ".." in rel.parts:
                    return False, f"path traversal escape: {abs_str}"
            except ValueError:
                pass

    return True, None


def _is_write_command(cmd: str) -> bool:
    """Check if cmd is a write/delete command (exact or prefix match)."""
    return any(cmd.startswith(w) or cmd == w for w in _WRITE_COMMANDS)


def _extract_command(command: str) -> str:
    """Extract the base command from a shell command string."""
    stripped = command.strip()
    for sep in (" | ", " || ", " && ", " > ", " >> ", " < ", " 2>", " &"):
        if sep in stripped:
            stripped = stripped.split(sep)[0]
    stripped = stripped.strip()
    tokens = stripped.split()
    if not tokens:
        return ""
    return tokens[0].split("/")[-1]


_PATH_TOKEN_RE = re.compile(
    r"""
    (?P<quote>['"])(?P<quoted>(?:[^\\'"]|\\.)*)((?<!\\)\1)|
    (?:\s|^)(~[a-zA-Z_][a-zA-Z0-9_]*/?(?:[a-zA-Z0-9_./-]*)?)
    """,
    re.VERBOSE,
)


def _extract_path_tokens(command: str) -> list[str]:
    """Extract path-like tokens from a shell command.

    Handles:
    - Quoted strings (single or double) containing path-like content
    - Tilde expansions (~user/path)
    - Absolute paths starting with / that appear as separate tokens
    """
    tokens: list[str] = []
    for m in _PATH_TOKEN_RE.finditer(command):
        if m.group("quote"):
            quoted = m.group("quoted")
            if quoted and ("/" in quoted or "~" in quoted):
                tokens.append(quoted)
        elif m.group(4):
            tokens.append(m.group(4))

    # Find absolute paths as distinct tokens (preceded by whitespace, not part of a flag)
    # This matches /path but not inside words like "python"
    bare_paths = re.findall(r'(?<![a-zA-Z0-9_.-])(/[a-zA-Z0-9_./+-]+)', command)
    tokens.extend(bare_paths)

    # Also find Windows absolute paths: X:\... or X:/... by splitting on whitespace
    # and checking each token for a drive letter pattern
    for token in command.split():
        # Match Windows absolute path: drive letter + colon + path separator
        if len(token) >= 3 and token[1] == ":" and token[0].isalpha():
            tokens.append(token)

    return tokens
