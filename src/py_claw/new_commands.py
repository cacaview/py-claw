"""
New commands lightweight implementations.

These commands started as placeholders and are gradually being wired to
existing runtime services where practical.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any


def _rename_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Rename command - rename files or variables."""
    return "Rename command is not yet implemented. This feature requires full refactoring support."


def _format_pr_comment(comment: dict[str, Any]) -> list[str]:
    author = (((comment.get("user") or {}).get("login")) or "unknown")
    body = str(comment.get("body") or "").strip() or "(no text)"
    path = comment.get("path")
    line = comment.get("line") or comment.get("original_line")
    created_at = comment.get("created_at") or comment.get("updated_at") or "unknown time"
    location = f" {path}#{line}" if path and line else f" {path}" if path else ""
    lines = [f"- @{author}{location} ({created_at})"]
    diff_hunk = str(comment.get("diff_hunk") or "").strip()
    if diff_hunk:
        lines.append("  ```diff")
        lines.extend(f"  {line}" for line in diff_hunk.splitlines())
        lines.append("  ```")
    lines.append(f"  > {body}")
    return lines


def _run_gh_json(args: list[str]) -> Any:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise RuntimeError(stderr)
    stdout = result.stdout.strip()
    if not stdout:
        return None
    return json.loads(stdout)


def _pr_comments_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """PR comments command - fetch and display PR comments."""
    pr_ref = arguments.strip()
    if not pr_ref:
        return (
            "Usage: /pr-comments <pr-number>\n\n"
            "Fetches GitHub pull request comments using gh CLI and shows both\n"
            "PR-level comments and review comments."
        )

    try:
        pr_info = _run_gh_json([
            "pr",
            "view",
            pr_ref,
            "--json",
            "number,headRepository,headRepositoryOwner",
        ])
    except FileNotFoundError:
        return "GitHub CLI (gh) is not installed or not available in PATH."
    except (json.JSONDecodeError, RuntimeError) as exc:
        return f"Failed to load PR metadata: {exc}"

    pr_number = pr_info.get("number")
    repo_name = ((pr_info.get("headRepository") or {}).get("name"))
    owner_login = ((pr_info.get("headRepositoryOwner") or {}).get("login"))
    if not pr_number or not repo_name or not owner_login:
        return "Failed to determine repository information for this PR."

    repo_path = f"repos/{owner_login}/{repo_name}"

    try:
        issue_comments = _run_gh_json(["api", f"/{repo_path}/issues/{pr_number}/comments"]) or []
        review_comments = _run_gh_json(["api", f"/{repo_path}/pulls/{pr_number}/comments"]) or []
    except FileNotFoundError:
        return "GitHub CLI (gh) is not installed or not available in PATH."
    except (json.JSONDecodeError, RuntimeError) as exc:
        return f"Failed to load PR comments: {exc}"

    if not issue_comments and not review_comments:
        return "No comments found."

    lines: list[str] = [f"## PR #{pr_number} Comments", ""]

    if issue_comments:
        lines.append("### PR comments")
        for comment in issue_comments:
            lines.extend(_format_pr_comment(comment))
            lines.append("")

    if review_comments:
        lines.append("### Review comments")
        for comment in review_comments:
            lines.extend(_format_pr_comment(comment))
            lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _rate_limit_options_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Rate limit options command - configure rate limiting."""
    return "Rate limit options command is not yet implemented."


def _remote_env_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Remote env command - manage remote environment variables."""
    return "Remote env command is not yet implemented."


def _issue_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Issue command - interact with issue tracking systems."""
    if not arguments.strip():
        return (
            "Usage: /issue <subcommand> [args...]\n\n"
            "Supported subcommands:\n"
            "- /issue list [state]\n"
            "- /issue show <number>\n\n"
            "This command uses gh CLI to read GitHub issues for the current repository."
        )

    parts = arguments.strip().split()
    action = parts[0].lower()

    if action == "list":
        issue_state = parts[1].lower() if len(parts) > 1 else "open"
        if issue_state not in {"open", "closed", "all"}:
            return "Usage: /issue list [open|closed|all]"

        try:
            issues = _run_gh_json([
                "issue",
                "list",
                "--state",
                issue_state,
                "--limit",
                "20",
                "--json",
                "number,title,state,author,assignees,labels",
            ]) or []
        except FileNotFoundError:
            return "GitHub CLI (gh) is not installed or not available in PATH."
        except (json.JSONDecodeError, RuntimeError) as exc:
            return f"Failed to load issues: {exc}"

        if not issues:
            return f"No {issue_state} issues found."

        lines = [f"## Issues ({issue_state})", ""]
        for issue in issues:
            number = issue.get("number", "?")
            title = str(issue.get("title") or "(untitled)")
            state_name = str(issue.get("state") or "unknown")
            author = (((issue.get("author") or {}).get("login")) or "unknown")
            assignees = issue.get("assignees") or []
            labels = issue.get("labels") or []
            assignee_text = ", ".join(
                f"@{assignee.get('login')}" for assignee in assignees if assignee.get("login")
            ) or "none"
            label_text = ", ".join(
                str(label.get("name")) for label in labels if label.get("name")
            ) or "none"
            lines.append(f"- #{number} [{state_name}] {title}")
            lines.append(f"  author: @{author}")
            lines.append(f"  assignees: {assignee_text}")
            lines.append(f"  labels: {label_text}")
            lines.append("")

        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    if action == "show":
        if len(parts) < 2:
            return "Usage: /issue show <number>"
        issue_ref = parts[1]
        try:
            issue = _run_gh_json([
                "issue",
                "view",
                issue_ref,
                "--json",
                "number,title,state,body,author,assignees,labels,url",
            ])
        except FileNotFoundError:
            return "GitHub CLI (gh) is not installed or not available in PATH."
        except (json.JSONDecodeError, RuntimeError) as exc:
            return f"Failed to load issue: {exc}"

        if not isinstance(issue, dict):
            return "Failed to load issue details."

        number = issue.get("number", issue_ref)
        title = str(issue.get("title") or "(untitled)")
        state_name = str(issue.get("state") or "unknown")
        author = (((issue.get("author") or {}).get("login")) or "unknown")
        assignees = issue.get("assignees") or []
        labels = issue.get("labels") or []
        body = str(issue.get("body") or "").strip() or "(no description)"
        url = str(issue.get("url") or "")
        assignee_text = ", ".join(
            f"@{assignee.get('login')}" for assignee in assignees if assignee.get("login")
        ) or "none"
        label_text = ", ".join(
            str(label.get("name")) for label in labels if label.get("name")
        ) or "none"

        lines = [
            f"## Issue #{number}: {title}",
            "",
            f"State: {state_name}",
            f"Author: @{author}",
            f"Assignees: {assignee_text}",
            f"Labels: {label_text}",
        ]
        if url:
            lines.append(f"URL: {url}")
        lines.extend(["", body])
        return "\n".join(lines)

    return (
        f"Unsupported issue subcommand: {action}\n\n"
        "Supported subcommands: list, show"
    )


def _debug_tool_call_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Debug tool call command - debug a specific tool invocation."""
    from py_claw.services.diagnostic_tracking import generate_report, get_diagnostics_summary

    requested_tool = arguments.strip()
    summary = get_diagnostics_summary()
    report = generate_report()

    if requested_tool:
        lines = [
            f"=== Tool Debug: {requested_tool} ===",
            "",
            "Tool-specific tracing is not yet available in py-claw.",
            "Current diagnostic tracking snapshot:",
            f"  Enabled: {'yes' if summary.get('enabled') else 'no'}",
            f"  Total tracked: {summary.get('total_tracked', 0)}",
            f"  Fixed total: {summary.get('fixed_total', 0)}",
            f"  Max tracked: {summary.get('max_tracked', 0)}",
            f"  Auto-fix suggestions: {'yes' if summary.get('auto_fix_suggestions') else 'no'}",
            "",
            "Severity counts:",
        ]
    else:
        lines = [
            "=== Debug Tool Call ===",
            "",
            "Usage: /debug-tool-call <tool-name>",
            "",
            "Diagnostic tracking snapshot:",
            f"  Enabled: {'yes' if summary.get('enabled') else 'no'}",
            f"  Total tracked: {summary.get('total_tracked', 0)}",
            f"  Fixed total: {summary.get('fixed_total', 0)}",
            f"  Max tracked: {summary.get('max_tracked', 0)}",
            f"  Auto-fix suggestions: {'yes' if summary.get('auto_fix_suggestions') else 'no'}",
            "",
            "Severity counts:",
        ]

    severity_counts = report.by_severity or {}
    if severity_counts:
        for severity_name in ("error", "warning", "info", "hint"):
            if severity_name in severity_counts:
                lines.append(f"  {severity_name}: {severity_counts[severity_name]}")
    else:
        lines.append("  none")

    lines.extend(["", "Source counts:"])
    source_counts = report.by_source or {}
    if source_counts:
        for source_name, count in sorted(source_counts.items()):
            lines.append(f"  {source_name}: {count}")
    else:
        lines.append("  none")

    lines.extend(
        [
            "",
            f"Newly introduced (1h): {report.newly_introduced}",
            f"Newly fixed: {report.newly_fixed}",
        ]
    )
    if report.most_recent is not None:
        lines.append(f"Most recent: {report.most_recent.isoformat()}")

    return "\n".join(lines)


def _perf_issue_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Perf issue command - diagnose performance problems."""
    if not arguments.strip():
        return """Performance Issue Diagnostics

This command analyzes performance problems in your session.

Usage: /perf-issue [area]

Areas:
- session     - Session-level performance issues
- tools       - Tool execution timing
- api         - API response times
- memory      - Memory usage analysis

Example: /perf-issue tools"""
    return f"Performance issue analysis: {arguments}\n\nThis feature analyzes session performance."


def _mock_limits_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Mock limits command - simulate rate limit errors for testing."""
    if not arguments.strip():
        return """Mock Limits (Testing Only)

Usage: /mock-limits <type> [duration]

Types:
- rate_limit    - Simulate rate limit error
- token_limit   - Simulate token limit error
- timeout       - Simulate timeout error

Example: /mock-limits rate_limit 60"""
    return f"Mock limits: {arguments}\n\nThis is for testing purposes only."


def _build_oauth_status(service) -> str:
    tokens = service.get_tokens()
    profile = service.get_profile()
    authenticated = service.is_authenticated()
    profile_email = "unknown"
    if profile is not None and isinstance(getattr(profile, "raw", None), dict):
        profile_email = str(profile.raw.get("email") or profile.raw.get("name") or "unknown")
    lines = [
        "OAuth Status",
        "",
        f"Authenticated: {'yes' if authenticated else 'no'}",
        f"Refresh token: {'yes' if tokens and tokens.refresh_token else 'no'}",
        f"Token expired: {'yes' if tokens and tokens.is_expired else 'no'}",
        f"Profile: {profile_email}",
        "",
        "Usage:",
        "- /oauth-refresh",
        "- /oauth-refresh status",
        "- /oauth-refresh refresh",
    ]
    return "\n".join(lines)


def _oauth_refresh_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """OAuth refresh command - refresh OAuth tokens."""
    from py_claw.services.oauth.service import get_oauth_service

    service = get_oauth_service()
    action = arguments.strip().lower()

    if not action or action == "status":
        return _build_oauth_status(service)

    if action not in {"refresh", "current", "claude.ai"}:
        return (
            f"Unsupported OAuth target: {arguments.strip()}\n\n"
            "Currently supported targets: status, refresh, current, claude.ai"
        )

    if not service.is_authenticated():
        return "OAuth is not authenticated for the current session. Run /login first."

    tokens = service.get_tokens()
    if tokens is None:
        return "No OAuth tokens are available for the current session."
    if not tokens.refresh_token:
        return "OAuth tokens do not include a refresh token. Please log in again."

    try:
        refreshed = service.refresh_token(tokens)
    except Exception as exc:
        return f"OAuth token refresh failed: {exc}"

    service._tokens = refreshed
    profile = service.get_profile()
    profile_email = "unknown"
    if profile is not None and isinstance(getattr(profile, "raw", None), dict):
        profile_email = str(profile.raw.get("email") or profile.raw.get("name") or "unknown")

    return "\n".join(
        [
            "OAuth token refreshed.",
            f"Access token present: {'yes' if refreshed.access_token else 'no'}",
            f"Refresh token present: {'yes' if refreshed.refresh_token else 'no'}",
            f"Profile: {profile_email}",
        ]
    )


def _remote_setup_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Remote setup command - configure remote connections."""
    from py_claw.services.remote_settings.service import get_remote_settings_service

    service = get_remote_settings_service()
    if not service.initialized:
        service.initialize()

    action = arguments.strip().lower()
    if action in {"", "status", "config"}:
        config = service.get_config()
        cached_settings = service.get_settings()
        checksum = service.get_checksum()
        polling_active = getattr(service, "_polling_interval_id", None) is not None
        api_url = config.api_url or os.environ.get("CLAUDE_API_URL") or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"

        lines = [
            "Remote Setup",
            "",
            f"Eligible: {'yes' if service.is_eligible() else 'no'}",
            f"Initialized: {'yes' if service.initialized else 'no'}",
            f"Remote settings enabled: {'yes' if config.enabled else 'no'}",
            f"Polling active: {'yes' if polling_active else 'no'}",
            f"API URL: {api_url}",
            f"Managed settings endpoint: {config.api_url or 'default'}",
            f"Timeout: {config.timeout_ms} ms",
            f"Polling interval: {config.polling_interval_ms} ms",
            f"Cache file: {config.cache_file}",
            f"Cached settings: {'yes' if cached_settings else 'no'}",
            f"Checksum: {checksum or 'none'}",
        ]
        if cached_settings:
            lines.append(f"Cached keys: {', '.join(sorted(cached_settings.keys()))}")
        lines.extend(
            [
                "",
                "Usage:",
                "- /remote-setup",
                "- /remote-setup status",
                "- /remote-setup config",
                "- /remote-setup clear-cache",
            ]
        )
        return "\n".join(lines)

    if action == "clear-cache":
        service.clear_cache()
        return "Remote managed settings cache cleared."

    return (
        f"Unsupported remote setup action: {arguments.strip()}\n\n"
        "Supported actions: status, config, clear-cache"
    )


def _thinkback_play_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Thinkback play command - play back think-back history."""
    if not arguments.strip():
        return """Think-Back Playback

Usage: /thinkback-play [session-id]

Play back the think-back history from a previous session.

Example: /thinkback-play abc123"""
    return f"Thinkback playback: {arguments}\n\nThis feature plays back session think history."


def _bridge_kick_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Bridge kick command - inject bridge fault state (Ant internal)."""
    return "Bridge kick command is for internal use only."


def _agents_platform_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Agents platform command - manage agents platform."""
    if not arguments.strip():
        return """Agents Platform

Usage: /agents-platform [action]

Actions:
- status    - Show platform status
- list      - List active agents
- create    - Create new agent

Example: /agents-platform status"""
    return f"Agents platform: {arguments}\n\nThis feature manages the agents platform."


def _ant_trace_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Ant trace command - trace Ant internal operations."""
    return "Ant trace command is for internal use only."


def _ctx_viz_handler(
    command,
    *,
    arguments: str,
    state,
    settings,
    registry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Context visualization command - visualize context usage."""
    settings_skills = None
    if hasattr(settings, "effective") and isinstance(settings.effective, dict):
        settings_skills = settings.effective.get("skills")

    try:
        slash_usage = state.build_slash_command_usage(settings_skills) if hasattr(state, "build_slash_command_usage") else None
    except Exception:
        slash_usage = None
    try:
        skill_usage = state.build_skill_usage(settings_skills) if hasattr(state, "build_skill_usage") else None
    except Exception:
        skill_usage = None

    total_input = int(getattr(state, "_total_input_tokens", 0) or 0)
    total_output = int(getattr(state, "_total_output_tokens", 0) or 0)
    total_tokens = total_input + total_output
    command_count = slash_usage.get("includedCommands") if isinstance(slash_usage, dict) else len(registry.list())
    skill_count = skill_usage.get("includedSkills") if isinstance(skill_usage, dict) else 0
    tasks = state.task_runtime.list() if hasattr(state, "task_runtime") else []
    active_tasks = [task for task in tasks if getattr(task, "status", None) != "completed"]

    lines = [
        "=== Context Visualization ===",
        "",
        f"Session ID: {session_id or 'inactive'}",
        f"Transcript messages: {transcript_size}",
        f"Working directory: {getattr(state, 'cwd', 'unknown')}",
        "",
        "Context components:",
        f"  Commands: {command_count}",
        f"  Skills: {skill_count}",
        f"  Agents: {len(getattr(state, 'initialized_agents', {}))}",
        f"  SDK MCP servers: {len(getattr(state, 'sdk_mcp_servers', []))}",
        f"  Todos: {len(getattr(state, 'todos', []))}",
        f"  Cron jobs: {len(getattr(state, 'scheduled_cron_jobs', []))}",
        f"  Active tasks: {len(active_tasks)}",
        "",
        "Token usage:",
        f"  Input: {total_input:,}",
        f"  Output: {total_output:,}",
        f"  Total: {total_tokens:,}",
    ]

    if total_tokens > 0:
        input_width = round((total_input / total_tokens) * 20)
        output_width = 20 - input_width
        lines.extend(
            [
                "",
                "Token mix:",
                f"  input  [{'#' * input_width}{'.' * (20 - input_width)}]",
                f"  output [{'#' * output_width}{'.' * (20 - output_width)}]",
            ]
        )

    lines.extend(
        [
            "",
            "Use /summary for a broader session summary.",
            "Use /compact when context pressure grows.",
        ]
    )
    return "\n".join(lines)
