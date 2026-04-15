"""
MCP configuration management.

Handles MCP server configuration loading, normalization, dedup, and policy filtering.

Mirrors: ClaudeCode-main/src/services/mcp/config.ts
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from py_claw.mcp.env_expansion import expand_env_vars_in_config, expand_env_vars_in_string
from py_claw.mcp.normalization import normalize_name_for_mcp
from py_claw.mcp.utils import hash_mcp_config, get_logging_safe_mcp_base_url


# CCR proxy URL path markers for claude.ai connectors
CCR_PROXY_PATH_MARKERS = [
    "/v2/session_ingress/shttp/mcp/",
    "/v2/ccr-sessions/",
]

# 25-letter alphabet for short ID generation (a-z minus 'l')
ID_ALPHABET = "abcdefghijkmnopqrstuvwxyz"

# Substring blocklist for short IDs
ID_AVOID_SUBSTRINGS = [
    "fuck", "shit", "cunt", "cock", "dick", "twat", "piss", "crap", "bitch",
    "whore", "ass", "tit", "cum", "fag", "dyke", "nig", "kike", "rape", "nazi",
    "damn", "poo", "pee", "wank", "anus",
]


def get_server_command_array(config: dict[str, Any]) -> list[str] | None:
    """
    Extract command array from server config (stdio servers only).

    Returns None for non-stdio servers.

    Args:
        config: MCP server config

    Returns:
        Command array [command, ...args] or None
    """
    config_type = config.get("type")
    if config_type is not None and config_type != "stdio":
        return None
    stdio_config = config
    command = stdio_config.get("command", "")
    args = stdio_config.get("args") or []
    return [command] + args


def get_server_url(config: dict[str, Any]) -> str | None:
    """
    Extract URL from server config (remote servers only).

    Returns None for stdio/sdk servers.

    Args:
        config: MCP server config

    Returns:
        URL string or None
    """
    url = config.get("url")
    return url if isinstance(url, str) else None


def unwrap_ccr_proxy_url(url: str) -> str:
    """
    If the URL is a CCR proxy URL, extract the original vendor URL.

    In remote sessions, claude.ai connectors arrive via --mcp-config with URLs
    rewritten to route through the CCR/session-ingress SHTTP proxy. The original
    vendor URL is preserved in the mcp_url query param so the proxy knows where
    to forward.

    Args:
        url: The URL to unwrap

    Returns:
        Original vendor URL or unchanged URL
    """
    if not any(marker in url for marker in CCR_PROXY_PATH_MARKERS):
        return url
    try:
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        original = query_params.get("mcp_url", [None])[0]
        return original if original else url
    except Exception:
        return url


def get_mcp_server_signature(config: dict[str, Any]) -> str | None:
    """
    Compute a dedup signature for an MCP server config.

    Two configs with the same signature are considered "the same server" for
    plugin deduplication. Ignores env (plugins always inject CLAUDE_PLUGIN_ROOT)
    and headers (same URL = same server regardless of auth).

    Returns None only for configs with neither command nor url (sdk type).

    Args:
        config: MCP server config

    Returns:
        Signature string or None
    """
    cmd = get_server_command_array(config)
    if cmd:
        return f"stdio:{json.dumps(cmd)}"
    url = get_server_url(config)
    if url:
        return f"url:{unwrap_ccr_proxy_url(url)}"
    return None


def command_arrays_match(a: list[str], b: list[str]) -> bool:
    """
    Check if two command arrays match exactly.

    Args:
        a: First command array
        b: Second command array

    Returns:
        True if arrays match exactly
    """
    if len(a) != len(b):
        return False
    return all(val == b[i] for i, val in enumerate(a))


def url_pattern_to_regex(pattern: str) -> re.Pattern:
    """
    Convert a URL pattern with wildcards to a RegExp.

    Supports * as wildcard matching any characters, including in port positions.

    Args:
        pattern: URL pattern with optional wildcards

    Returns:
        Compiled regex pattern
    """
    # For port patterns like "https://example.com:*/*", we need special handling
    # because :* doesn't mean "zero or more chars after colon" but rather
    # "match any port number"

    # First, escape regex special characters except *
    escaped = re.escape(pattern)

    # Replace escaped \* with regex pattern that matches any characters
    # But handle port patterns specially: \:* should match : followed by digits
    # Let's do a simple string-based replacement before regex compilation

    # Replace patterns like \* in hostname/path context
    regex_str = escaped.replace(r"\*", ".*")

    # Handle :\* for port matching (e.g., "https://example.com:*/*")
    # This should match :8080, :3000, etc.
    regex_str = re.sub(r":\\\*", r":[0-9]*", regex_str)

    return re.compile(f"^{regex_str}$")


def url_matches_pattern(url: str, pattern: str) -> bool:
    """
    Check if a URL matches a pattern with wildcard support.

    Args:
        url: URL to check
        pattern: Pattern with optional wildcards

    Returns:
        True if URL matches pattern
    """
    regex = url_pattern_to_regex(pattern)
    return regex.match(url) is not None


def short_request_id(tool_use_id: str) -> str:
    """
    Generate a short ID from a toolUseID.

    5 letters from a 25-char alphabet (a-z minus 'l' — looks like 1/I).
    Letters-only so phone users don't switch keyboard modes.

    Args:
        tool_use_id: The tool use ID to hash

    Returns:
        5-letter short ID
    """
    # FNV-1a hash
    h = 0x811C9DC5
    for char in tool_use_id:
        h ^= ord(char)
        h = (h * 0x01000193) & 0xFFFFFFFF
    h = h & 0xFFFFFFFF

    def base25_encode(value: int) -> str:
        result = ""
        for _ in range(5):
            result = ID_ALPHABET[value % 25] + result
            value //= 25
        return result

    def hash_with_salt(salt: int) -> str:
        h2 = 0x811C9DC5
        combined = f"{tool_use_id}:{salt}"
        for char in combined:
            h2 ^= ord(char)
            h2 = (h2 * 0x01000193) & 0xFFFFFFFF
        h2 = h2 & 0xFFFFFFFF
        return base25_encode(h2)

    # Try up to 10 salts to avoid blocked substrings
    for salt in range(10):
        candidate = hash_with_salt(salt)
        if not any(bad in candidate for bad in ID_AVOID_SUBSTRINGS):
            return candidate

    # Fallback: return last candidate
    return hash_with_salt(9)


def truncate_for_preview(input_data: Any, max_chars: int = 200) -> str:
    """
    Truncate tool input to a phone-sized JSON preview.

    Args:
        input_data: The input data to truncate
        max_chars: Maximum characters to include

    Returns:
        Truncated string
    """
    try:
        s = json.dumps(input_data)
        return s[:max_chars] + "…" if len(s) > max_chars else s
    except Exception:
        return "(unserializable)"


def dedup_plugin_mcp_servers(
    plugin_servers: dict[str, dict[str, Any]],
    manual_servers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Filter plugin MCP servers, dropping any whose signature matches a
    manually-configured server or an earlier-loaded plugin server.

    Manual wins over plugin; between plugins, first-loaded wins.

    Args:
        plugin_servers: Plugin-provided server configs
        manual_servers: Manually configured server configs

    Returns:
        Dict with 'servers' (filtered servers) and 'suppressed' (list of suppressed servers)
    """
    # Map signature -> server name
    manual_sigs: dict[str, str] = {}
    for name, config in manual_servers.items():
        sig = get_mcp_server_signature(config)
        if sig and sig not in manual_sigs:
            manual_sigs[sig] = name

    servers: dict[str, dict[str, Any]] = {}
    suppressed: list[dict[str, str]] = []
    seen_plugin_sigs: dict[str, str] = {}

    for name, config in plugin_servers.items():
        sig = get_mcp_server_signature(config)
        if sig is None:
            servers[name] = config
            continue

        manual_dup = manual_sigs.get(sig)
        if manual_dup is not None:
            suppressed.append({"name": name, "duplicateOf": manual_dup})
            continue

        plugin_dup = seen_plugin_sigs.get(sig)
        if plugin_dup is not None:
            suppressed.append({"name": name, "duplicateOf": plugin_dup})
            continue

        seen_plugin_sigs[sig] = name
        servers[name] = config

    return {"servers": servers, "suppressed": suppressed}


def dedup_claude_ai_mcp_servers(
    claudeai_servers: dict[str, dict[str, Any]],
    manual_servers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Filter claude.ai connectors, dropping any whose signature matches an enabled
    manually-configured server.

    Manual wins: a user who wrote .mcp.json or ran `claude mcp add` expressed
    higher intent than a connector toggled in the web UI.

    Args:
        claudeai_servers: claude.ai connector configs
        manual_servers: Manually configured server configs

    Returns:
        Dict with 'servers' and 'suppressed'
    """
    # Only enabled manual servers count as dedup targets
    manual_sigs: dict[str, str] = {}
    for name, config in manual_servers.items():
        # Skip disabled servers
        if config.get("disabled"):
            continue
        sig = get_mcp_server_signature(config)
        if sig and sig not in manual_sigs:
            manual_sigs[sig] = name

    servers: dict[str, dict[str, Any]] = {}
    suppressed: list[dict[str, str]] = []

    for name, config in claudeai_servers.items():
        sig = get_mcp_server_signature(config)
        manual_dup = sig if sig else None
        if manual_dup is not None and manual_dup in manual_sigs:
            suppressed.append({"name": name, "duplicateOf": manual_sigs[manual_dup]})
            continue
        servers[name] = config

    return {"servers": servers, "suppressed": suppressed}


def is_mcp_server_denied(
    server_name: str,
    config: dict[str, Any] | None = None,
    denied_list: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Check if an MCP server is denied by enterprise policy.

    Checks name-based, command-based, and URL-based restrictions.

    Args:
        server_name: Name of the server
        config: Optional server config for command/URL-based matching
        denied_list: List of denied server entries

    Returns:
        True if denied
    """
    if not denied_list:
        return False

    # Check name-based denial
    for entry in denied_list:
        entry_type = entry.get("type")
        if entry_type == "name" and entry.get("serverName") == server_name:
            return True

    if config:
        # Check command-based denial (stdio servers)
        server_command = get_server_command_array(config)
        if server_command:
            for entry in denied_list:
                if entry.get("type") == "command" and command_arrays_match(
                    entry.get("serverCommand", []), server_command
                ):
                    return True

        # Check URL-based denial (remote servers)
        server_url = get_server_url(config)
        if server_url:
            for entry in denied_list:
                if entry.get("type") == "url" and url_matches_pattern(
                    server_url, entry.get("serverUrl", "")
                ):
                    return True

    return False


def is_mcp_server_allowed(
    server_name: str,
    config: dict[str, Any] | None = None,
    allowed_list: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Check if an MCP server is allowed by enterprise policy.

    Args:
        server_name: Name of the server
        config: Optional server config
        allowed_list: List of allowed server entries

    Returns:
        True if allowed
    """
    # Empty allowlist means block all servers
    if allowed_list is not None and len(allowed_list) == 0:
        return False

    # No allowlist restrictions
    if not allowed_list:
        return True

    # Check if allowlist contains any command-based or URL-based entries
    has_command_entries = any(e.get("type") == "command" for e in allowed_list)
    has_url_entries = any(e.get("type") == "url" for e in allowed_list)

    if config:
        server_command = get_server_command_array(config)
        server_url = get_server_url(config)

        if server_command:
            # This is a stdio server
            if has_command_entries:
                for entry in allowed_list:
                    if entry.get("type") == "command" and command_arrays_match(
                        entry.get("serverCommand", []), server_command
                    ):
                        return True
                return False  # Stdio server doesn't match any command entry
            else:
                # No command entries, check name-based allowance
                return any(
                    e.get("type") == "name" and e.get("serverName") == server_name
                    for e in allowed_list
                )
        elif server_url:
            # This is a remote server
            if has_url_entries:
                for entry in allowed_list:
                    if entry.get("type") == "url" and url_matches_pattern(
                        server_url, entry.get("serverUrl", "")
                    ):
                        return True
                return False  # Remote server doesn't match any URL entry
            else:
                return any(
                    e.get("type") == "name" and e.get("serverName") == server_name
                    for e in allowed_list
                )

    # No config provided - check name-based allowance only
    return any(
        e.get("type") == "name" and e.get("serverName") == server_name
        for e in allowed_list
    )


def filter_mcp_servers_by_policy(
    configs: dict[str, dict[str, Any]],
    allowed_list: list[dict[str, Any]] | None = None,
    denied_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Filter MCP server configs by enterprise policy (allowlist/denylist).

    Args:
        configs: Server configs to filter
        allowed_list: Optional allowlist
        denied_list: Optional denylist

    Returns:
        Dict with 'allowed' and 'blocked' keys
    """
    allowed: dict[str, dict[str, Any]] = {}
    blocked: list[str] = []

    for name, config in configs.items():
        # SDK-type servers are exempt
        if config.get("type") == "sdk":
            allowed[name] = config
            continue

        # Denylist takes absolute precedence
        if is_mcp_server_denied(name, config, denied_list):
            blocked.append(name)
            continue

        # Check allowlist
        if not is_mcp_server_allowed(name, config, allowed_list):
            blocked.append(name)
            continue

        allowed[name] = config

    return {"allowed": allowed, "blocked": blocked}


def parse_mcp_config(
    config_object: Any,
    expand_vars: bool = True,
    scope: str = "local",
) -> dict[str, Any]:
    """
    Parse and validate an MCP configuration object.

    Args:
        config_object: Raw config object
        expand_vars: Whether to expand environment variables
        scope: Config scope for error reporting

    Returns:
        Dict with 'config' (validated config or None) and 'errors' (list of errors)
    """
    from pydantic import TypeAdapter, ValidationError
    from py_claw.schemas.common import McpServerConfigForProcessTransport

    errors: list[dict[str, Any]] = []

    # Handle raw dict format
    if isinstance(config_object, dict) and "mcpServers" in config_object:
        mcp_servers = config_object.get("mcpServers", {})
    elif isinstance(config_object, dict):
        mcp_servers = config_object
    else:
        return {"config": None, "errors": [{"message": "Invalid MCP config format"}]}

    validated_servers: dict[str, dict[str, Any]] = {}

    adapter = TypeAdapter(McpServerConfigForProcessTransport)

    for name, server_config in mcp_servers.items():
        if not isinstance(server_config, dict):
            errors.append({
                "path": f"mcpServers.{name}",
                "message": "Server config must be an object",
                "scope": scope,
            })
            continue

        config_to_validate = server_config

        if expand_vars:
            result = expand_env_vars_in_config(config_to_validate)
            config_to_validate = result["expanded"]
            if result["missing_vars"]:
                errors.append({
                    "path": f"mcpServers.{name}",
                    "message": f"Missing environment variables: {', '.join(result['missing_vars'])}",
                    "suggestion": f"Set the following environment variables: {', '.join(result['missing_vars'])}",
                    "scope": scope,
                    "serverName": name,
                })

        # Validate with Pydantic
        try:
            adapter.validate_python(config_to_validate)
            validated_servers[name] = config_to_validate
        except ValidationError as e:
            errors.append({
                "path": f"mcpServers.{name}",
                "message": f"Invalid server config: {str(e)}",
                "scope": scope,
                "serverName": name,
            })

    return {"config": {"mcpServers": validated_servers}, "errors": errors}


def parse_mcp_config_from_file(
    file_path: str,
    expand_vars: bool = True,
    scope: str = "local",
) -> dict[str, Any]:
    """
    Parse and validate an MCP configuration from a file.

    Args:
        file_path: Path to the config file
        expand_vars: Whether to expand environment variables
        scope: Config scope

    Returns:
        Dict with 'config' and 'errors'
    """
    path = Path(file_path)

    if not path.exists():
        return {
            "config": None,
            "errors": [{
                "file": file_path,
                "path": "",
                "message": f"MCP config file not found: {file_path}",
                "suggestion": "Check that the file path is correct",
                "scope": scope,
            }],
        }

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "config": None,
            "errors": [{
                "file": file_path,
                "path": "",
                "message": f"Failed to read file: {e}",
                "scope": scope,
            }],
        }

    try:
        config_object = json.loads(content)
    except json.JSONDecodeError as e:
        return {
            "config": None,
            "errors": [{
                "file": file_path,
                "path": "",
                "message": f"MCP config is not valid JSON: {e}",
                "suggestion": "Fix the JSON syntax errors in the file",
                "scope": scope,
            }],
        }

    result = parse_mcp_config(config_object, expand_vars, scope)
    if result["config"] is None and not result["errors"]:
        result["errors"] = [{
            "file": file_path,
            "path": "",
            "message": "MCP config is empty or invalid",
            "scope": scope,
        }]
    return result


def get_enterprise_mcp_file_path() -> str:
    """
    Get the path to the managed MCP configuration file.

    Returns:
        Path to enterprise MCP config
    """
    # This would use settings/managedPath in real implementation
    # For now, return a sensible default
    return os.path.join(os.path.expanduser("~"), ".claude", "managed-mcp.json")


def get_global_mcp_file_path() -> str:
    """
    Get the path to the global MCP configuration file.

    Returns:
        Path to global MCP config
    """
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def does_enterprise_mcp_config_exist() -> bool:
    """
    Check if enterprise MCP config exists.

    Returns:
        True if enterprise config exists
    """
    return Path(get_enterprise_mcp_file_path()).exists()


def get_mcp_json_path() -> str:
    """
    Get the path to .mcp.json in current directory.

    Returns:
        Path to .mcp.json
    """
    cwd = os.getcwd()
    return os.path.join(cwd, ".mcp.json")


async def write_mcp_json_file(config: dict[str, Any], file_path: str | None = None) -> None:
    """
    Write MCP config to .mcp.json file atomically.

    Args:
        config: MCP config to write
        file_path: Optional custom path
    """
    if file_path is None:
        file_path = get_mcp_json_path()

    import tempfile
    import shutil

    path = Path(file_path)
    temp_fd, temp_path = tempfile.mkstemp(
        suffix=".tmp",
        prefix=f".mcp.json.tmp.{os.getpid()}.",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(temp_fd, "w") as f:
            json.dump(config, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename
        shutil.move(temp_path, file_path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise


def is_mcp_server_disabled(name: str, disabled_list: list[str] | None = None) -> bool:
    """
    Check if an MCP server is disabled.

    Args:
        name: Server name
        disabled_list: List of disabled server names

    Returns:
        True if disabled
    """
    if not disabled_list:
        return False
    name_normalized = normalize_name_for_mcp(name)
    disabled_normalized = [normalize_name_for_mcp(n) for n in disabled_list]
    return name in disabled_list or name_normalized in disabled_normalized
