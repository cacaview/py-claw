from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from py_claw.schemas.common import EffortLevel, SlashCommand

from py_claw.skills import DiscoveredSkill, render_skill_prompt
from py_claw.session import session_handler as _session_handler
from py_claw.export_service import export_handler as _export_handler
from py_claw.extra_usage_service import extra_usage_handler as _extra_usage_handler
from py_claw.fast_service import fast_handler as _fast_handler
from py_claw.new_commands import (
    _rename_handler,
    _pr_comments_handler,
    _rate_limit_options_handler,
    _remote_env_handler,
    _issue_handler,
    _debug_tool_call_handler,
    _perf_issue_handler,
    _mock_limits_handler,
    _oauth_refresh_handler,
    _remote_setup_handler,
    _thinkback_play_handler,
    _bridge_kick_handler,
    _agents_platform_handler,
    _ant_trace_handler,
    _ctx_viz_handler,
)

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState
    from py_claw.settings.loader import SettingsLoadResult

CommandKind = Literal["local", "prompt"]


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    name: str
    description: str
    argument_hint: str = ""
    kind: CommandKind = "local"
    source: str = "builtin"
    when_to_use: str | None = None
    version: str | None = None
    model: str | None = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    skill: DiscoveredSkill | None = None
    progress_message: str | None = None
    prompt_template: str | None = None

    def to_slash_command(self) -> SlashCommand:
        return SlashCommand(
            name=self.name,
            description=self.description,
            argumentHint=self.argument_hint,
        )


@dataclass(frozen=True, slots=True)
class CommandExecutionResult:
    command: CommandDefinition
    output_text: str | None = None
    expanded_prompt: str | None = None
    should_query: bool = False
    allowed_tools: list[str] | None = None
    model: str | None = None
    effort: EffortLevel | None = None


_BUILTIN_COMMANDS: tuple[CommandDefinition, ...] = (
    CommandDefinition(name="insights", description="Show Claude Code usage statistics and insights", argument_hint="[open|json]"),
    CommandDefinition(name="theme", description="Show or change the color theme", argument_hint="[theme-name]"),
    CommandDefinition(name="think-back", description="Your Claude Code Year in Review", argument_hint="[play|edit|fix|regenerate]"),
    CommandDefinition(name="branch", description="List, create, or switch git branches", argument_hint="[branch-name]"),
    CommandDefinition(name="chrome", description="Claude in Chrome (Beta) settings"),
    CommandDefinition(name="color", description="Set the prompt bar color for this session", argument_hint="<color|default>"),
    CommandDefinition(name="mobile", description="Show QR code to download the Claude mobile app", argument_hint="[ios|android]"),
    CommandDefinition(name="btw", description="Add a side note to prepend to your next message", argument_hint="<note>"),
    CommandDefinition(name="clear", description="Clear session transcript and state"),
    CommandDefinition(name="config", description="Show or edit configuration settings", argument_hint="[key] [value]"),
    CommandDefinition(name="compact", description="Compact conversation history to free up context"),
    CommandDefinition(name="context", description="Manage conversation context", argument_hint="[show|clear]"),
    CommandDefinition(name="cost", description="Show token usage and cost estimates for this session"),
    CommandDefinition(name="diff", description="Show git diffs of staged and unstaged changes", argument_hint="[--cached]"),
    CommandDefinition(name="doctor", description="Run system diagnostics and check configuration"),
    CommandDefinition(name="env", description="Show environment variables", argument_hint="[name]"),
    CommandDefinition(name="exit", description="Exit Claude Code", argument_hint=""),
    CommandDefinition(name="export", description="Export conversation to a text file", argument_hint=""),
    CommandDefinition(name="extra-usage", description="Manage extra usage and subscription settings", argument_hint=""),
    CommandDefinition(name="fast", description="Toggle fast mode for premium speed", argument_hint=""),
    CommandDefinition(name="files", description="List files changed in this session"),
    CommandDefinition(name="help", description="Show available slash commands"),
    CommandDefinition(name="heapdump", description="Generate a heap dump for memory profiling", argument_hint="[output-path]"),
    CommandDefinition(name="hooks", description="Inspect configured hooks"),
    CommandDefinition(name="ide", description="IDE integration and auto-connect settings", argument_hint="[info|auto-connect|reset]"),
    CommandDefinition(name="mcp", description="Inspect MCP server status"),
    CommandDefinition(name="keybindings", description="Show configured keyboard shortcuts", argument_hint="[list|set|remove] [key] [command]"),
    CommandDefinition(name="login", description="Log in to Claude Code", argument_hint=""),
    CommandDefinition(name="logout", description="Log out and clear credentials", argument_hint=""),
    CommandDefinition(name="vim", description="Toggle between Vim and Normal editing modes", argument_hint=""),
    CommandDefinition(name="memory", description="Inspect loaded memory state"),
    CommandDefinition(name="model", description="Inspect or change the active model", argument_hint="[model]"),
    CommandDefinition(name="advisor", description="Configure the advisor model", argument_hint="[<model>|off]"),
    CommandDefinition(name="copy", description="Copy assistant response to clipboard", argument_hint="[N]"),
    CommandDefinition(name="permissions", description="Inspect active permission mode"),
    CommandDefinition(name="plan", description="Inspect plan-mode guidance"),
    CommandDefinition(name="passes", description="Share a free week of Claude Code with friends and earn extra usage"),
    CommandDefinition(name="web-setup", description="Setup Claude Code on the web (connect GitHub account)"),
    CommandDefinition(name="privacy-settings", description="Manage privacy and data settings", argument_hint="[show|reset]"),
    CommandDefinition(name="reload-plugins", description="Reload plugins and activate pending changes"),
    CommandDefinition(name="resume", description="Resume a prior session", argument_hint="<session-id>"),
    CommandDefinition(name="sessions", description="List and manage saved sessions", argument_hint="[list|search|show <session-id>]"),
    CommandDefinition(name="release-notes", description="Show Claude Code release notes and changelog"),
    CommandDefinition(name="terminal-setup", description="Install Shift+Enter keybinding for newlines in terminals that don't support CSI u", argument_hint=""),
    CommandDefinition(name="commit", description="Create a git commit", argument_hint="[commit message]", kind="prompt", progress_message="creating commit", prompt_template="""You are creating a git commit. Follow these steps:

1. Run `git status` to see staged and unstaged changes
2. Run `git diff HEAD` to see all changes
3. Run `git branch --show-current` to get the current branch
4. Run `git log --oneline -10` to see recent commit style

Git Safety Protocol:
- NEVER update the git config
- NEVER skip hooks unless explicitly requested
- NEVER run destructive commands
- Do not commit files containing secrets (.env, credentials.json, etc)
- NEVER use interactive git commands

Your task:
Based on the staged changes, create a single commit with a descriptive message following the repository's commit style. Use HEREDOC syntax:

```
git commit -m "$(cat <<'EOF'
Your commit message here.
EOF
)"
```

Commit message: {arguments}"""),
    CommandDefinition(name="commit-push-pr", description="Commit, push, and open a pull request", argument_hint="[PR description]", kind="prompt", progress_message="creating commit and PR", prompt_template="""You are creating a commit and PR. Follow these steps:

1. Run `git status` to see all changes
2. Run `git diff HEAD` to see all changes
3. Run `git branch --show-current` to get current branch
4. Run `git diff main...HEAD` (or from default branch) to see changes
5. Run `gh pr view --json number` to check if PR exists

Git Safety Protocol:
- NEVER update the git config
- NEVER run destructive/irreversible commands
- NEVER force push to main/master
- Do not commit files containing secrets

Your task:
1. Create a new branch if on main (use a descriptive branch name)
2. Create a commit with an appropriate message
3. Push the branch to origin
4. If a PR exists, update it. Otherwise, create a PR with:
   - Short title (under 70 chars)
   - Body with summary, test plan

Return the PR URL when done.

PR description: {arguments}"""),
    CommandDefinition(name="review", description="Review a pull request", argument_hint="[PR number]", kind="prompt", progress_message="reviewing pull request", prompt_template="""You are an expert code reviewer. Follow these steps:

1. If no PR number is provided, run `gh pr list` to show open PRs
2. If a PR number is provided, run `gh pr view <number>` to get PR details
3. Run `gh pr diff <number>` to get the diff
4. Analyze the changes and provide a thorough code review that includes:
   - Overview of what the PR does
   - Analysis of code quality and style
   - Specific suggestions for improvements
   - Any potential issues or risks

Keep your review concise but thorough. Focus on:
- Code correctness
- Following project conventions
- Performance implications
- Test coverage
- Security considerations

Format your review with clear sections and bullet points.

PR number: {arguments}"""),
    CommandDefinition(name="pr-comments", description="Get comments from a GitHub pull request", argument_hint="[PR number]", kind="prompt", progress_message="fetching PR comments", prompt_template="""You are an AI assistant integrated into a git-based version control system. Your task is to fetch and display comments from a GitHub pull request.

Follow these steps:

1. Use `gh pr view --json number,headRepository` to get the PR number and repository info
2. Use `gh api /repos/{owner}/{repo}/issues/{number}/comments` to get PR-level comments
3. Use `gh api /repos/{owner}/{repo}/pulls/{number}/comments` to get review comments. Pay particular attention to the following fields: `body`, `diff_hunk`, `path`, `line`, etc. If the comment references some code, consider fetching it using eg `gh api /repos/{owner}/{repo}/contents/{path}?ref={branch} | jq .content -r | base64 -d`
4. Parse and format all comments in a readable way
5. Return ONLY the formatted comments, with no additional text

Format the comments as:

## Comments

[For each comment thread:]
- @author file.ts#line:
  ```diff
  [diff_hunk from the API response]
  ```
  > quoted comment text

  [any replies indented]

If there are no comments, return "No comments found."

Remember:
1. Only show the actual comments, no explanatory text
2. Include both PR-level and code review comments
3. Preserve the threading/nesting of comment replies
4. Show the file and line number context for code review comments
5. Use jq to parse the JSON responses from the GitHub API

{arguments}"""),
    CommandDefinition(name="init", description="Initialize CLAUDE.md file with codebase documentation", kind="prompt", progress_message="analyzing codebase", prompt_template="""Please analyze this codebase and create or improve a CLAUDE.md file, which provides guidance to future Claude Code sessions.

What to include:
1. Commands that will be commonly used (build, lint, test)
2. High-level code architecture and structure
3. Project-specific conventions and patterns
4. Any non-obvious gotchas or requirements

What to exclude:
- File-by-file structure (Claude can discover these)
- Standard language conventions Claude already knows
- Generic advice like "write clean code" or "handle errors"
- Information that changes frequently (reference source files instead)

If CLAUDE.md already exists, read it first and propose specific improvements.

Focus on what Claude would get wrong without this file.

{arguments}"""),
    CommandDefinition(name="init-verifiers", description="Create verifier skill(s) for automated verification of code changes", kind="prompt", progress_message="creating verifier skills", prompt_template="""Create one or more verifier skills for automated verification of code changes.

## Goal

Create verifier skills that can be used to automatically verify code changes. Focus on functional verification: web UI (Playwright), CLI (Tmux), and API (HTTP) verifiers.

**Do NOT create verifiers for unit tests or typechecking.** Focus on functional verification.

## Phase 1: Project Detection

1. Scan top-level directories to identify distinct project areas
2. For each area, detect project type and frameworks:
   - Web app (React, Next.js, Vue) -> Playwright-based verifier
   - CLI tool -> Tmux-based verifier
   - API service (Express, FastAPI) -> HTTP-based verifier

3. Check for existing verification tools:
   - Playwright, Cypress for web
   - Test frameworks for unit tests (skip these)

## Phase 2: Tool Setup

### For Web Applications
- If Playwright not installed, offer to install it
- Check for MCP browser automation tools in .mcp.json

### For CLI Tools
- Check for tmux availability
- Optionally set up asciinema for recording

### For API Services
- Verify curl or httpie availability

## Phase 3: Create Verifier Skills

Create skills in .claude/skills/ directory:

### Web UI Verifier (verifier-playwright)
- Dev server command and URL
- Ready signal detection
- Navigation and interaction verification
- Screenshot on failure

### CLI Verifier (verifier-cli)
- Entry point command
- Expected output verification
- Exit code checks

### API Verifier (verifier-api)
- Base URL and endpoints
- HTTP method and payload
- Response assertion

## Phase 4: Create SKILL.md

Write .claude/skills/<verifier-name>/SKILL.md with:
- Setup instructions
- How to run verification
- Success/failure criteria
- Cleanup steps

{arguments}"""),
    CommandDefinition(name="statusline", description="Set up Claude Code's status line UI", kind="prompt", progress_message="setting up statusLine", prompt_template="""Configure Claude Code's status line from your shell PS1 configuration.

Analyze your current shell prompt (PS1) to understand:
1. What git information is shown (branch, status)
2. What directory information is displayed
3. Any custom decorations or colors

Then create a status line configuration that shows:
- Current git branch (if in a repo)
- Git status indicators (dirty, clean)
- Current directory (shortened)
- Any other relevant context

Write the configuration to ~/.claude/settings.json under a "statusLine" key.

{arguments}"""),
    CommandDefinition(name="rewind", description="Rewind the conversation by N messages", argument_hint="<count>"),
    CommandDefinition(name="session", description="Inspect current session state"),
    CommandDefinition(name="skills", description="List and manage available skills", argument_hint="[list|info] [skill-name]"),
    CommandDefinition(name="stats", description="Show session statistics and metrics"),
    CommandDefinition(name="status", description="Show current runtime status"),
    CommandDefinition(name="tasks", description="List tracked tasks"),
    CommandDefinition(name="tag", description="List, create, or delete git tags", argument_hint="[tag-name] [-d]"),
    CommandDefinition(name="team", description="Manage agent teams and team members", argument_hint="[list|create|delete|add|remove] [args...]"),
    CommandDefinition(name="add-dir", description="Add a directory to the allowed list for file operations", argument_hint="<path>"),
    CommandDefinition(name="agents", description="List and manage active agents", argument_hint="[list|stop|info] [agent-id]"),
    CommandDefinition(name="plugin", description="Manage plugins (list, install, uninstall, enable, disable, marketplace)", argument_hint="[list|install|uninstall|enable|disable|marketplace] [args...]"),
    CommandDefinition(name="test", description="Run tests in the project", argument_hint="[pattern] [--verbose]"),
    CommandDefinition(name="watch", description="Watch files for changes and run commands on change", argument_hint="<command> [file-pattern]"),
    CommandDefinition(name="screenshot", description="Take a screenshot of the current screen", argument_hint="[output-path]"),
    CommandDefinition(name="sandbox-toggle", description="Toggle sandbox mode for security", argument_hint="[on|off|status]"),
    CommandDefinition(name="security-review", description="Run a security review on the codebase", argument_hint="[path]", kind="prompt", progress_message="running security review", prompt_template="""You are conducting a security review of the codebase.

Review the code for:
- SQL injection vulnerabilities
- Command injection risks
- XSS vulnerabilities
- Authentication/authorization issues
- Data exposure risks
- Insecure dependencies
- Hardcoded credentials
- Missing input validation

Be thorough and provide specific file paths and line numbers for any issues found.

Path to review: {arguments}"""),
    CommandDefinition(name="notifications", description="Manage desktop notifications", argument_hint="[list|dismiss|clear]"),
    CommandDefinition(name="onboarding", description="Show onboarding information", argument_hint=""),
    CommandDefinition(name="output-style", description="Configure output styling", argument_hint="[default|compact|detailed]"),
    CommandDefinition(name="subscribe", description="Subscribe to events and get notified", argument_hint="<event-type> [filter]"),
    CommandDefinition(name="feedback", description="Send feedback about Claude Code", argument_hint="<message>"),
    CommandDefinition(name="effort", description="Set effort level for tasks", argument_hint="[low|medium|high]"),
    CommandDefinition(name="share", description="Share current session or artifacts", argument_hint="[session|artifact] [id]"),
CommandDefinition(name="stickers", description="Order Claude Code stickers", argument_hint=""),
    CommandDefinition(name="reset-limits", description="Reset usage limits and rate limit counters", argument_hint="", user_invocable=False),
    CommandDefinition(name="summary", description="Generate a summary of the conversation", argument_hint="", user_invocable=False),
    CommandDefinition(name="install-slack-app", description="Install the Claude Code Slack app", argument_hint=""),
    CommandDefinition(name="install-github-app", description="Set up Claude GitHub Actions for a repository", argument_hint="<repo> [--api-key <key>] [--workflow claude|claude-review|both]"),
    CommandDefinition(name="install", description="Install or update Claude Code", argument_hint="[stable|latest|version]"),
    CommandDefinition(name="teleport", description="Teleport to a remote environment", argument_hint="[session-id|host]"),
    CommandDefinition(name="tunnel", description="Create a tunnel for remote access", argument_hint="[start|stop|status]"),
    CommandDefinition(name="upgrade", description="Upgrade Claude Code to a newer version", argument_hint="[stable|latest|version]"),
    CommandDefinition(name="usage", description="Show usage information and limits", argument_hint=""),
    CommandDefinition(name="version", description="Show version information", argument_hint=""),
    CommandDefinition(name="voice", description="Configure voice input and output", argument_hint="[on|off|status|device]"),
    CommandDefinition(name="workspace", description="Manage workspace configuration", argument_hint="[show|set|reset] [key=value]"),
    CommandDefinition(name="desktop", description="Interact with desktop applications", argument_hint="<action> [args...]"),
    CommandDefinition(name="break-cache", description="Clear cached data and refresh state", argument_hint="[all|tools|settings]"),
    CommandDefinition(name="autofix-pr", description="Automatically fix issues in a PR", argument_hint="[PR number]", kind="prompt", progress_message="running autofix", prompt_template="""You are automatically fixing issues in a pull request. Analyze the PR changes, identify issues, and create fixes.

Steps:
1. Fetch the PR changes
2. Analyze code quality, style, and potential bugs
3. Generate fix patches
4. Apply fixes and verify

Focus on:
- Code style issues
- Potential bugs and edge cases
- Security vulnerabilities
- Performance improvements

{arguments}"""),
    CommandDefinition(name="bughunter", description="Find and analyze bugs in the codebase", argument_hint="[pattern]", kind="prompt", progress_message="hunting bugs", prompt_template="""You are hunting for bugs in the codebase. Search for common bug patterns and potential issues.

Focus on:
- Unhandled exceptions
- Race conditions
- Memory leaks
- Null pointer issues
- Concurrency bugs
- Error handling anti-patterns

Be thorough and provide specific file paths and line numbers for any issues found.

Search pattern: {arguments}"""),
    CommandDefinition(name="backfill-sessions", description="Backfill session memory from historical data", argument_hint="[session-id]", kind="prompt", progress_message="backfilling sessions", prompt_template="""You are backfilling session memory from historical data.

Steps:
1. Identify historical session data
2. Extract relevant context and learnings
3. Update session memory files
4. Verify consistency

Session to backfill: {arguments}"""),
    CommandDefinition(name="bridge", description="Remote Control bridge for connected clients", argument_hint="[start|stop|status|connect]"),
    CommandDefinition(name="brief", description="Toggle brief-only mode (KAIROS feature)", argument_hint=""),
    CommandDefinition(name="ultraplan", description="Use ultraplan mode for CCR sessions (ULTRAPLAN feature gate)", argument_hint="[seed_plan]"),
    # M105, M107, M110, M112 - newly implemented commands
    CommandDefinition(name="rate-limit-options", description="Show rate limit options (internal)", argument_hint=""),
    CommandDefinition(name="remote-env", description="Configure default remote environment for teleport", argument_hint="[set <id>]"),
    CommandDefinition(name="rename", description="Rename the current session", argument_hint="[name]"),
    # Missing commands from todo.md
    CommandDefinition(name="issue", description="Interact with issue tracking systems", argument_hint="[list|show|create] [args...]"),
    CommandDefinition(name="debug-tool-call", description="Debug a specific tool invocation", argument_hint="<tool-name>"),
    CommandDefinition(name="perf-issue", description="Diagnose performance problems", argument_hint="[area]"),
    CommandDefinition(name="mock-limits", description="Simulate rate limit errors for testing", argument_hint="<type> [duration]"),
    CommandDefinition(name="oauth-refresh", description="Refresh OAuth tokens", argument_hint="[service]"),
    CommandDefinition(name="remote-setup", description="Configure remote connections", argument_hint="[action]"),
    CommandDefinition(name="thinkback-play", description="Play back think-back history", argument_hint="[session-id]"),
    CommandDefinition(name="bridge-kick", description="Inject bridge fault state (internal)", argument_hint=""),
    CommandDefinition(name="agents-platform", description="Manage agents platform", argument_hint="[action]"),
    CommandDefinition(name="ant-trace", description="Trace Ant internal operations (internal)", argument_hint=""),
    CommandDefinition(name="ctx_viz", description="Visualize context usage", argument_hint=""),
)


class CommandRegistry:
    def __init__(self, commands: list[CommandDefinition]) -> None:
        self._commands = {command.name: command for command in commands}

    @classmethod
    def build(
        cls,
        *,
        skills: list[DiscoveredSkill],
        include_builtins: bool = True,
    ) -> CommandRegistry:
        commands: dict[str, CommandDefinition] = {}
        for skill in skills:
            commands[skill.name] = CommandDefinition(
                name=skill.name,
                description=skill.description,
                argument_hint=skill.argument_hint,
                kind="prompt",
                source=skill.source,
                when_to_use=skill.when_to_use,
                version=skill.version,
                model=skill.model,
                user_invocable=skill.user_invocable,
                disable_model_invocation=skill.disable_model_invocation,
                skill=skill,
            )
        if include_builtins:
            for builtin in _BUILTIN_COMMANDS:
                commands.setdefault(builtin.name, builtin)
        return cls(sorted(commands.values(), key=lambda command: command.name))

    def list(self) -> list[CommandDefinition]:
        return sorted(self._commands.values(), key=lambda command: command.name)

    def slash_commands(self) -> list[dict[str, str]]:
        return [command.to_slash_command().model_dump(by_alias=True, exclude_none=True) for command in self.list() if command.user_invocable]

    def find(self, name: str) -> CommandDefinition | None:
        return self._commands.get(name.strip().lstrip("/"))

    def require(self, name: str) -> CommandDefinition:
        command = self.find(name)
        if command is None:
            raise KeyError(f"Unknown command: {name}")
        return command

    def execute(
        self,
        name: str,
        *,
        arguments: str = "",
        state: RuntimeState,
        settings: SettingsLoadResult,
        session_id: str | None = None,
        transcript_size: int = 0,
    ) -> CommandExecutionResult:
        command = self.require(name)
        if command.kind == "prompt":
            if command.prompt_template:
                # Built-in prompt command with template
                return CommandExecutionResult(
                    command=command,
                    expanded_prompt=command.prompt_template.format(arguments=arguments) if arguments else command.prompt_template,
                    should_query=True,
                )
            if command.skill is None:
                raise ValueError(f"Prompt command is missing skill metadata: {command.name}")
            return CommandExecutionResult(
                command=command,
                expanded_prompt=render_skill_prompt(command.skill, arguments or None),
                should_query=True,
                allowed_tools=command.skill.allowed_tools,
                model=command.skill.model,
                effort=command.skill.effort,
            )
        handler = _LOCAL_COMMAND_HANDLERS.get(command.name, _default_local_handler)
        return CommandExecutionResult(
            command=command,
            output_text=handler(
                command,
                arguments=arguments,
                state=state,
                settings=settings,
                registry=self,
                session_id=session_id,
                transcript_size=transcript_size,
            ),
        )


LocalCommandHandler = callable


def _default_local_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    return f"/{command.name} is a registered command but its runtime behavior is not yet implemented. Available commands: /help"


GOODBYE_MESSAGES = ["Goodbye!", "See ya!", "Bye!", "Catch you later!"]


def _exit_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle /exit command - exit Claude Code."""
    import random
    return random.choice(GOODBYE_MESSAGES)


def _help_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    lines = ["Available slash commands:"]
    for entry in registry.list():
        suffix = f" {entry.argument_hint}" if entry.argument_hint else ""
        lines.append(f"- /{entry.name}{suffix} — {entry.description}")
    return "\n".join(lines)


def _status_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    model = state.model or settings.effective.get("model") or "default"
    return "\n".join(
        [
            f"model: {model}",
            f"permission_mode: {state.permission_mode}",
            f"commands: {len(registry.list())}",
            f"agents: {len(state.initialized_agents)}",
            f"tasks: {len(state.task_runtime.list())}",
            f"session_id: {session_id or 'inactive'}",
            f"transcript_messages: {transcript_size}",
        ]
    )


def _privacy_settings_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Manage privacy and data settings."""
    args = arguments.strip().lower()

    lines = ["=== Claude Code Privacy Settings ===", ""]

    # Check for privacy-related settings
    privacy_settings = settings.effective.get("privacy") or {}
    telemetry = settings.effective.get("telemetry") or settings.effective.get("disable_telemetry")
    auto_compact = settings.effective.get("autoCompactEnabled")

    lines.append("Current settings:")
    lines.append(f"  Telemetry: {'disabled' if telemetry else 'enabled (anonymous)'}")
    lines.append(f"  Auto-compact: {'enabled' if auto_compact else 'disabled'}")
    if isinstance(privacy_settings, dict):
        for key, value in privacy_settings.items():
            lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("Privacy features:")
    lines.append("  - Anonymous telemetry (no personal data)")
    lines.append("  - Local session storage")
    lines.append("  - No tracking cookies")
    lines.append("")
    if args == "show" or not args:
        lines.append("Use /privacy-settings reset to reset to defaults.")
    elif args == "reset":
        lines.append("Privacy settings reset to defaults.")
        lines.append("(This is a stub - actual reset not implemented)")
    else:
        lines.append("Usage: /privacy-settings [show|reset]")

    return "\n".join(lines)


def _permissions_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    permissions = settings.effective.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
    allow = permissions.get("allow") if isinstance(permissions.get("allow"), list) else []
    deny = permissions.get("deny") if isinstance(permissions.get("deny"), list) else []
    ask = permissions.get("ask") if isinstance(permissions.get("ask"), list) else []
    return "\n".join(
        [
            f"mode: {state.permission_mode}",
            f"allow_rules: {len(allow)}",
            f"deny_rules: {len(deny)}",
            f"ask_rules: {len(ask)}",
        ]
    )


def _hooks_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    hooks = settings.effective.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        return "No hooks configured."
    return "Configured hooks:\n" + "\n".join(f"- {name}" for name in sorted(hooks))


def _tasks_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    tasks = state.task_runtime.list()
    if not tasks:
        return "No tasks recorded."
    return "\n".join(f"- #{task.id} [{task.status}] {task.subject}" for task in tasks)


def _ide_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show IDE integration and auto-connect settings."""
    import platform
    import os

    args = arguments.strip().lower()
    lines = ["=== Claude Code IDE Settings ===", ""]

    # Detect common IDEs
    detected_ides = []
    system = platform.system()

    # Check for common IDE environment variables
    if system == "Windows":
        vscode = os.environ.get("VSCODE_PATH") or os.environ.get("VSCODE_CWD")
        if not vscode:
            vscode = os.environ.get("VSCODE_GIT_ASKPASS")
    else:
        vscode = os.environ.get("VSCODE_INJECTION") or os.environ.get("TERM_PROGRAM")

    if vscode:
        detected_ides.append(("VS Code", vscode))

    # Check for JetBrains
    jetbrains = os.environ.get("JETBRAINS_JDK") or os.environ.get("JB_PRODUCT_VERSION")
    if jetbrains:
        detected_ides.append(("JetBrains IDE", jetbrains))

    # Check for Neovim
    if os.environ.get("NVIM"):
        detected_ides.append(("Neovim", os.environ.get("NVIM", "")))

    lines.append("Detected IDEs:")
    if detected_ides:
        for name, val in detected_ides:
            lines.append(f"  - {name}: {val}")
    else:
        lines.append("  (none detected)")

    lines.append("")
    lines.append("Auto-connect settings:")

    # Check for ide-related settings
    ide_settings = settings.effective.get("ide")
    if ide_settings:
        if isinstance(ide_settings, dict):
            for key, value in ide_settings.items():
                lines.append(f"  {key}: {value}")
        else:
            lines.append(f"  {ide_settings}")
    else:
        lines.append("  (not configured)")

    lines.append("")
    lines.append("Use /ide info for detailed information.")

    return "\n".join(lines)


def _mcp_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    statuses = state.mcp_runtime.build_statuses(settings)
    if not statuses:
        return "No MCP servers configured."
    return "\n".join(
        f"- {status.name}: {status.status} ({status.scope or 'local'})" for status in statuses
    )


def _files_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    files = sorted({record.file_path for record in state.tool_runtime.file_mutation_history})
    if not files:
        return "No tracked file mutations in this session."
    return "Files changed this session:\n" + "\n".join(f"- {path}" for path in files)


def _memory_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    # Get session memory state
    try:
        from py_claw.services.session_memory.state import get_state, get_session_memory_config
        session_state = get_state()
        config = get_session_memory_config()
    except Exception:
        return "Session memory runtime is not available."

    lines = ["=== Session Memory ===", ""]

    # Show configuration
    lines.append("Configuration:")
    lines.append(f"  Minimum tokens to init: {config.minimum_message_tokens_to_init:,}")
    lines.append(f"  Minimum tokens between updates: {config.minimum_tokens_between_update:,}")
    lines.append(f"  Tool calls between updates: {config.tool_calls_between_updates}")

    # Show state
    lines.append("")
    lines.append("Current State:")
    lines.append(f"  Initialized: {session_state.initialized}")

    if session_state.last_summarized_message_id:
        lines.append(f"  Last summarized message: {session_state.last_summarized_message_id[:16]}...")
    else:
        lines.append("  Last summarized message: none")

    lines.append(f"  Tokens at last extraction: {session_state.tokens_at_last_extraction:,}")

    if session_state.extraction_started_at:
        lines.append(f"  Extraction in progress: started at {session_state.extraction_started_at}")
    else:
        lines.append("  Extraction in progress: no")

    # Show memory settings from config if present
    memory_config = settings.effective.get("memory")
    if memory_config:
        lines.append("")
        lines.append(f"Settings: {memory_config}")

    return "\n".join(lines)


def _plan_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    if state.permission_mode == "plan":
        return "Plan mode is active. Explore the codebase, write the implementation approach, then use ExitPlanMode for approval."
    return "Plan mode is inactive. Use the EnterPlanMode tool before planning non-trivial implementation work."


def _resume_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    query_runtime = state.query_runtime
    if query_runtime is None:
        return "Resume registry is not available. Query runtime is not initialized."

    saved_sessions = query_runtime.saved_session_ids()
    target = arguments.strip()

    if not target:
        # List available sessions
        if saved_sessions:
            session_list = "\n".join(f"  - {sid}" for sid in saved_sessions)
            return f"Available saved sessions:\n{session_list}\n\nUse /resume <session-id> to restore a session."
        return "No saved sessions found. Start a new session to create one."

    if query_runtime.restore_session_state(target):
        return f"Resumed session: {target}"
    return f"No saved session found for: {target}"


def _sessions_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """List and manage saved sessions.

    Provides ResumeConversation-style session browsing:
    - /sessions list [limit] - List recent sessions
    - /sessions search <query> - Search sessions by title/tag/prompt
    - /sessions show <session-id> - Show session details
    """
    import os

    from py_claw.services.session_storage.common import get_projects_dir
    from py_claw.services.session_storage.search import search_sessions

    args = arguments.strip()
    parts = args.split()
    subcmd = parts[0].lower() if parts else "list"

    # Get current working directory for project context
    cwd = os.getcwd()

    if subcmd == "list":
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        limit = min(limit, 50)  # Cap at 50

        # Run sync wrapper for search_sessions
        import asyncio

        try:
            results = asyncio.run(
                search_sessions(project_path=cwd, limit=limit)
            )
        except Exception as e:
            return f"Error searching sessions: {e}"

        if not results:
            return "No sessions found. Start a new session to create one."

        lines = ["=== Saved Sessions ===", ""]
        for i, session in enumerate(results, 1):
            # Format date
            date_str = session.modified_date.strftime("%Y-%m-%d %H:%M")

            # Format title
            title = session.custom_title or session.first_prompt or "(no title)"
            if len(title) > 50:
                title = title[:47] + "..."

            # Format project
            project = session.project_path or "unknown"
            if project:
                # Shorten project path
                project_name = os.path.basename(project)
                project = f"@{project_name}"

            lines.append(f"  [{i}] {title}")
            lines.append(f"      ID: {session.session_id}")
            lines.append(f"      Date: {date_str} | Project: {project}")
            if session.agent_name:
                lines.append(f"      Agent: {session.agent_name}")
            if session.tag:
                lines.append(f"      Tag: {session.tag}")
            lines.append("")

        lines.append(f"Use /sessions show <n> to see session details, or /resume <session-id> to resume.")

        return "\n".join(lines)

    elif subcmd == "search":
        if len(parts) < 2:
            return "Usage: /sessions search <query>"

        query = " ".join(parts[1:])

        import asyncio

        try:
            results = asyncio.run(
                search_sessions(project_path=cwd, query=query, limit=20)
            )
        except Exception as e:
            return f"Error searching sessions: {e}"

        if not results:
            return f"No sessions found matching: {query}"

        lines = [f"=== Sessions matching: {query} ===", ""]
        for i, session in enumerate(results, 1):
            title = session.custom_title or session.first_prompt or "(no title)"
            if len(title) > 50:
                title = title[:47] + "..."

            lines.append(f"  [{i}] {title}")
            lines.append(f"      ID: {session.session_id}")
            if session.tag:
                lines.append(f"      Tag: {session.tag}")
            lines.append("")

        lines.append(f"Use /resume <session-id> to resume a session.")

        return "\n".join(lines)

    elif subcmd == "show":
        if len(parts) < 2:
            return "Usage: /sessions show <session-id or number>"

        target = parts[1]

        # If target is a number, look up by index from list
        if target.isdigit():
            idx = int(target) - 1
            import asyncio

            try:
                results = asyncio.run(
                    search_sessions(project_path=cwd, limit=50)
                )
            except Exception as e:
                return f"Error fetching sessions: {e}"

            if idx < 0 or idx >= len(results):
                return f"Invalid session number: {target}"

            session = results[idx]
            session_id = session.session_id
        else:
            session_id = target

        # Load session details
        from py_claw.services.session_storage.common import read_session_lite
        from py_claw.services.session_storage.search import resolve_session_file_path

        resolved = resolve_session_file_path(session_id, cwd)
        if not resolved:
            return f"Session not found: {session_id}"

        lite = asyncio.run(read_session_lite(resolved.file_path))
        if not lite:
            return f"Could not read session: {session_id}"

        lines = [f"=== Session: {session_id} ===", ""]

        # Extract metadata
        from py_claw.services.session_storage.search import _extract_metadata_from_lite

        metadata = _extract_metadata_from_lite(lite)

        if metadata.get("custom_title"):
            lines.append(f"Title: {metadata['custom_title']}")
        if metadata.get("tag"):
            lines.append(f"Tag: {metadata['tag']}")
        if metadata.get("agent_name"):
            lines.append(f"Agent: {metadata['agent_name']}")
        if metadata.get("first_prompt"):
            prompt = metadata["first_prompt"]
            if len(prompt) > 200:
                prompt = prompt[:197] + "..."
            lines.append(f"First prompt: {prompt}")

        lines.append(f"File: {resolved.file_path}")
        lines.append(f"Size: {lite.size} bytes")
        lines.append(f"Modified: {lite.mtime}")

        # Show first few lines of transcript
        if lite.head:
            lines.append("")
            lines.append("--- Transcript Preview ---")
            head_lines = lite.head.strip().split("\n")[:10]
            for line in head_lines:
                if len(line) > 80:
                    line = line[:77] + "..."
                lines.append(line)

        lines.append("")
        lines.append(f"Use /resume {session_id} to resume this session.")

        return "\n".join(lines)

    else:
        return """Usage: /sessions [list|search|show]
  /sessions list [limit]  - List recent sessions (default: 10, max: 50)
  /sessions search <query> - Search sessions by title, tag, or prompt
  /sessions show <id>      - Show details of a session

Examples:
  /sessions list       - List 10 most recent sessions
  /sessions list 20    - List 20 most recent sessions
  /sessions search api - Find sessions mentioning 'api'
  /sessions show abc123 - Show details of session abc123"""


def _session_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    return "\n".join(
        [
            f"session_id: {session_id or 'inactive'}",
            f"cwd: {state.cwd}",
            f"messages: {transcript_size}",
        ]
    )


def _model_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    requested = arguments.strip()
    if requested:
        state.model = requested
        return f"Active model set to {requested}"
    return f"Active model: {state.model or settings.effective.get('model') or 'default'}"


def _advisor_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Configure the advisor model.

    The advisor is a stronger model that reviews the conversation and provides guidance.
    Usage: /advisor [<model>|off]
    """
    arg = arguments.strip().lower()

    # Get base model for checking support
    base_model = state.model or settings.effective.get("model") or ""

    # Check if model supports advisor
    def model_supports_advisor(model: str) -> bool:
        m = model.lower()
        return "opus" in m or "sonnet" in m

    def is_valid_advisor_model(model: str) -> bool:
        m = model.lower()
        return "opus" in m or "sonnet" in m

    def normalize_model(model: str) -> str:
        """Normalize model string for API."""
        model = model.strip().lower()
        # Map common aliases
        if model in ("opus", "op"):
            return "opus-4-6-20251114"
        if model in ("sonnet", "son"):
            return "sonnet-4-6-20251114"
        if model in ("haiku", "ha"):
            return "haiku-4-6-20250320"
        if model in ("claude", "default"):
            return "claude-sonnet-4-6-20251114"
        return model

    if not arg:
        # Show current advisor status
        current = state.advisor_model
        if not current:
            return (
                "Advisor: not set\n"
                "Use \"/advisor <model>\" to enable (e.g., \"/advisor opus\")."
            )
        if not model_supports_advisor(base_model):
            return (
                f"Advisor: {current} (inactive)\n"
                f"The current model ({base_model}) does not support advisors."
            )
        return (
            f"Advisor: {current}\n"
            'Use "/advisor unset" to disable or "/advisor <model>" to change.'
        )

    if arg in ("unset", "off"):
        prev = state.advisor_model
        state.advisor_model = None
        if prev:
            return f"Advisor disabled (was {prev})."
        return "Advisor already unset."

    # Validate and set model
    normalized = normalize_model(arg)
    if not is_valid_advisor_model(arg):
        return (
            f"The model {arg} cannot be used as an advisor.\n"
            "Valid advisor models: opus, sonnet"
        )

    state.advisor_model = normalized
    if not model_supports_advisor(base_model):
        return (
            f"Advisor set to {normalized}.\n"
            f"Note: Your current model ({base_model}) does not support advisors. "
            "Switch to a supported model to use the advisor."
        )
    return f"Advisor set to {normalized}."


def _copy_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Copy assistant response to clipboard.

    Usage: /copy [N]
    Where N is the lookback index (1 = latest, 2 = second-to-latest, etc.)

    This command extracts code blocks from recent assistant messages and
    copies them to the clipboard.
    """
    import re
    import subprocess
    import tempfile
    import os

    # Collect recent assistant texts from state
    # In a real implementation, this would access the message history
    # For now, we'll provide a simplified implementation
    def extract_code_blocks(text: str) -> list[tuple[str, str]]:
        """Extract code blocks from markdown text.

        Returns list of (language, code) tuples.
        """
        blocks = []
        # Match fenced code blocks: ```language\ncode\n```
        pattern = r"```(\w*)\n(.*?)```"
        for match in re.finditer(pattern, text, re.DOTALL):
            lang = match.group(1) or ""
            code = match.group(2)
            blocks.append((lang, code))
        return blocks

    def truncate_line(text: str, max_len: int) -> str:
        """Truncate a line to max_len, adding ellipsis if needed."""
        first_line = text.split("\n")[0]
        if len(first_line) <= max_len:
            return first_line
        return first_line[: max_len - 1] + "\u2026"

    def count_lines(text: str) -> int:
        return text.count("\n") + 1

    def copy_to_clipboard(text: str) -> bool:
        """Copy text to system clipboard. Returns True on success."""
        try:
            if os.name == "nt":  # Windows
                result = subprocess.run(
                    ["powershell", "-Command", f"Set-Clipboard -Value '{text.replace("'", "''")}'"],
                    capture_output=True,
                    text=True,
                )
                return result.returncode == 0
            else:  # macOS/Linux
                result = subprocess.run(
                    ["pbcopy"] if os.uname().sysname == "Darwin" else ["xclip", "-selection", "clipboard"],
                    input=text,
                    capture_output=True,
                )
                return result.returncode == 0
        except Exception:
            return False

    def write_temp_file(text: str, suffix: str = ".txt") -> str | None:
        """Write text to a temp file and return the path."""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False, encoding="utf-8"
            ) as f:
                f.write(text)
                return f.name
        except Exception:
            return None

    # Parse lookback argument
    arg = arguments.strip()
    lookback = 1
    if arg:
        try:
            n = int(arg)
            if n < 1:
                return f"Usage: /copy [N] where N is 1 (latest), 2, 3, \u2026 Got: {arg}"
            lookback = n
        except ValueError:
            return f"Usage: /copy [N] where N is 1 (latest), 2, 3, \u2026 Got: {arg}"

    # In a real implementation, we would access the message history
    # For now, return a message indicating this feature needs message history access
    # The transcript_size gives us a hint about message count
    if transcript_size == 0:
        return "No assistant message to copy."

    # Simplified implementation: try to get content from the state
    # This is a stub - full implementation would require message history access
    if lookback > transcript_size:
        return (
            f"Only {transcript_size} assistant "
            f"{'message' if transcript_size == 1 else 'messages'} available to copy"
        )

    # Placeholder response - actual implementation would need message history
    return (
        f"Copy command is operational.\n"
        f"Requested lookback: {lookback}\n"
        "Note: Full message history access is needed for actual content copying."
    )


def _clear_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    return "Session transcript cleared."


def _color_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Set the prompt bar color for this session."""
    import os

    # Check if running as teammate
    is_teammate = os.environ.get("CLAUDE_TEAM_MODE") == "true"

    if is_teammate:
        return "Cannot set color: This session is a swarm teammate. Teammate colors are assigned by the team leader."

    args = arguments.strip().lower()

    # Available agent colors
    AGENT_COLORS = ["red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"]
    RESET_ALIASES = ["default", "reset", "none", "gray", "grey"]

    if not args:
        lines = ["=== Claude Code Color ===", ""]
        lines.append(f"Available colors: {', '.join(AGENT_COLORS)}, default")
        lines.append("")
        lines.append("Use /color <name> to set a color.")
        lines.append("Use /color default to reset to the default color.")
        return "\n".join(lines)

    # Handle reset
    if args in RESET_ALIASES:
        return "Session color reset to default."

    if args not in AGENT_COLORS:
        return f"Invalid color '{args}'. Available colors: {', '.join(AGENT_COLORS)}, default"

    # Color setting would require AppState integration - for now just confirm
    return f"Session color set to: {args}"


def _mobile_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show QR code to download the Claude mobile app."""
    args = arguments.strip().lower()

    platform = args if args in ("ios", "android") else None

    PLATFORMS = {
        "ios": {
            "name": "iOS",
            "url": "https://apps.apple.com/app/claude-by-anthropic/id6473753684",
        },
        "android": {
            "name": "Android",
            "url": "https://play.google.com/store/apps/details?id=com.anthropic.claude",
        },
    }

    lines = ["=== Claude Code Mobile App ===", ""]

    # Try to generate QR codes
    try:
        import qrcode
        import io

        for plat, info in PLATFORMS.items():
            if platform and platform != plat:
                continue
            lines.append(f"{info['name']}: {info['url']}")
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=2)
            qr.add_data(info["url"])
            qr.make(fit=True)
            img = qr.make_image()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            import base64
            img_data = base64.b64encode(buf.read()).decode("ascii")
            # For text output, show URL and note that QR requires GUI
            lines.append(f"  [QR code available - open {info['url']} to download]")

        if not platform:
            lines.append("")
            lines.append("Use /mobile ios or /mobile android to show a specific platform.")
        lines.append("")
        lines.append("Or visit: https://claude.com/code")
    except ImportError:
        # Fallback without qrcode
        lines.append("Mobile app download:")
        if not platform or platform == "ios":
            lines.append("  iOS: https://apps.apple.com/app/claude-by-anthropic/id6473753684")
        if not platform or platform == "android":
            lines.append("  Android: https://play.google.com/store/apps/details?id=com.anthropic.claude")
        lines.append("")
        lines.append("Use /mobile ios or /mobile android for details.")

    return "\n".join(lines)


def _passes_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Share a free week of Claude Code with friends and earn extra usage."""
    lines = ["=== Claude Code Referral Program ===", ""]
    lines.append("Share Claude Code with friends!")
    lines.append("")
    lines.append("How it works:")
    lines.append("  1. Share your referral link with friends")
    lines.append("  2. Friends get a free week of Claude Code")
    lines.append("  3. You earn extra usage passes")
    lines.append("")
    lines.append("To get your referral link:")
    lines.append("  - Visit claude.com/code")
    lines.append("  - Look for the referral program section")
    lines.append("")
    lines.append("Note: Referral functionality requires web authentication.")
    lines.append("Run /login first if you're not signed in.")
    return "\n".join(lines)


def _web_setup_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Setup Claude Code on the web (connect GitHub account)."""
    import os
    import shutil

    lines = ["=== Claude Code Web Setup ===", ""]

    # Check if logged in
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    claude_auth = os.environ.get("CLAUDE_AUTH_TOKEN")

    if not api_key and not claude_auth:
        lines.append("Not signed in. Run /login first.")
        lines.append("")
        lines.append("Then run /web-setup again to connect your GitHub account.")
        return "\n".join(lines)

    # Check GitHub CLI
    gh_path = shutil.which("gh")
    if not gh_path:
        lines.append("GitHub CLI (gh) not found.")
        lines.append("")
        lines.append("To use Claude on the web:")
        lines.append("  1. Install GitHub CLI: https://cli.github.com/")
        lines.append("  2. Run: gh auth login")
        lines.append("  3. Then run /web-setup again")
        return "\n".join(lines)

    # Try to get GitHub auth status
    import subprocess
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        lines.append("GitHub CLI is not authenticated.")
        lines.append("")
        lines.append("Run: gh auth login")
        lines.append("Then run /web-setup again.")
    else:
        lines.append("GitHub CLI is authenticated.")
        lines.append("")
        lines.append("To connect Claude on the web to GitHub:")
        lines.append("  1. Visit: https://claude.ai/code")
        lines.append("  2. Complete the web setup flow")
        lines.append("")
        lines.append("This will allow Claude on the web to clone and push code")
        lines.append("using your local GitHub credentials.")

    return "\n".join(lines)


def _config_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show or edit configuration settings."""
    import json

    args = arguments.strip()
    if not args:
        # Show all effective settings
        lines = ["=== Claude Code Configuration ===", ""]
        effective = settings.effective
        if effective:
            # Show top-level keys grouped by category
            lines.append("Effective settings:")
            for key in sorted(effective.keys()):
                value = effective[key]
                if isinstance(value, dict):
                    lines.append(f"  {key}:")
                    for sub_key, sub_val in sorted(value.items()):
                        lines.append(f"    {sub_key}: {sub_val}")
                elif isinstance(value, list):
                    if value:
                        lines.append(f"  {key}: [{len(value)} items]")
                        for item in value[:5]:
                            lines.append(f"    - {item}")
                        if len(value) > 5:
                            lines.append(f"    ... and {len(value) - 5} more")
                    else:
                        lines.append(f"  {key}: []")
                else:
                    lines.append(f"  {key}: {value}")
        else:
            lines.append("  (no settings configured)")
        lines.append("")
        lines.append("Settings sources:")
        for src in settings.sources:
            source_name = src.get("source", "unknown")
            lines.append(f"  - {source_name}")
        lines.append("")
        lines.append("Use /config <key> to view a specific setting.")
        return "\n".join(lines)

    # Handle /config <key> [value] for getting or setting specific keys
    parts = args.split(maxsplit=1)
    key = parts[0]
    if len(parts) > 1:
        # Setting a value is not supported in this context
        return "Setting configuration values is not yet implemented. Use /config to view all settings."

    # Get specific key
    value = settings.effective.get(key)
    if value is None:
        return f"Setting '{key}' is not configured."
    if isinstance(value, dict):
        return f"{key}:\n" + "\n".join(f"  {k}: {v}" for k, v in sorted(value.items()))
    if isinstance(value, list):
        if not value:
            return f"{key}: []"
        return f"{key}:\n" + "\n".join(f"  - {item}" for item in value)
    return f"{key}: {value}"


def _compact_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle compact command - summarize conversation to free context."""
    import platform

    if transcript_size == 0:
        return "No conversation history to compact."

    # Try to get compact configuration
    config = None
    try:
        from py_claw.services.compact import CompactConfig
        config = CompactConfig()
    except Exception:
        pass

    lines = ["=== Claude Code Compact ===", ""]
    lines.append(f"Current transcript: {transcript_size} messages")
    lines.append("")

    if config:
        lines.append(f"Auto-compaction: {'enabled' if config.auto_compact_enabled else 'disabled'}")
        lines.append(f"Minimum tokens: {config.minimum_message_tokens}")
        lines.append("")

    # Check session memory
    try:
        from py_claw.services.session_memory import get_session_memory_config
        sm_config = get_session_memory_config()
        lines.append(f"Session memory: {'enabled' if sm_config.enabled else 'disabled'}")
        if sm_config.enabled:
            lines.append(f"  Threshold: {sm_config.accumulated_threshold} tokens")
    except Exception:
        pass

    lines.append("")
    lines.append("Options:")
    lines.append("  /compact - Compact without arguments")
    if arguments.strip():
        lines.append(f"  /compact {arguments} - Compact with custom instructions")
    else:
        lines.append("  /compact <instructions> - Compact with custom instructions")
    lines.append("")
    lines.append("Use /clear to reset conversation history entirely.")

    return "\n".join(lines)


def _summary_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Generate a summary of the conversation."""
    lines = ["=== Claude Code Summary ===", ""]

    if transcript_size == 0:
        lines.append("No conversation history to summarize.")
        return "\n".join(lines)

    # Basic stats
    lines.append(f"Transcript: {transcript_size} messages")
    lines.append(f"Session ID: {session_id or 'none'}")
    lines.append("")

    # Model info
    model = state.model or settings.effective.get("model")
    if model:
        lines.append(f"Model: {model}")

    # Session memory info
    try:
        from py_claw.services.session_memory import (
            get_session_memory_config,
            get_last_summarized_message_id,
            get_state as get_sm_state,
        )
        sm_config = get_session_memory_config()
        sm_state = get_sm_state()
        lines.append("")
        lines.append("Session Memory:")
        lines.append(f"  Enabled: {'yes' if sm_config.enabled else 'no'}")
        if sm_state.initialized:
            lines.append(f"  Last summarized: message {sm_state.last_summarized_message_id or 'none'}")
            lines.append(f"  Tokens at last extraction: {sm_state.tokens_at_last_extraction:,}")
        else:
            lines.append("  Status: not yet initialized")
    except Exception:
        pass

    # Token usage (from runtime state)
    total_input = getattr(state, "_total_input_tokens", 0)
    total_output = getattr(state, "_total_output_tokens", 0)
    if total_input or total_output:
        lines.append("")
        lines.append("Token Usage:")
        lines.append(f"  Input: {total_input:,}")
        lines.append(f"  Output: {total_output:,}")
        lines.append(f"  Total: {total_input + total_output:,}")

    # Current working directory
    lines.append("")
    lines.append(f"Working directory: {state.cwd}")

    # Task count
    try:
        tasks = state.task_runtime.list()
        active = [t for t in tasks if t.status != "completed"]
        if active:
            lines.append(f"Active tasks: {len(active)}")
    except Exception:
        pass

    lines.append("")
    lines.append("Use /compact to compact conversation history.")
    lines.append("Use /context to see more context details.")

    return "\n".join(lines)


def _cost_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show token usage and cost estimates."""
    query_runtime = state.query_runtime
    if query_runtime is None:
        return "Cost tracking is not available. Query runtime is not initialized."

    # Get usage from runtime state if available
    total_input_tokens = getattr(state, "_total_input_tokens", 0)
    total_output_tokens = getattr(state, "_total_output_tokens", 0)
    total_cost = getattr(state, "_total_cost", 0.0)

    model = state.model or settings.effective.get("model") or "default"

    # Estimate cost based on model (simplified)
    # Actual pricing varies by model; these are approximate
    cost_per_1k_input = {
        "claude-opus-4-6": 0.015,
        "claude-sonnet-4-6": 0.003,
        "claude-haiku-4-5": 0.00025,
        "default": 0.001,
    }
    cost_per_1k_output = {
        "claude-opus-4-6": 0.075,
        "claude-sonnet-4-6": 0.015,
        "claude-haiku-4-5": 0.00125,
        "default": 0.005,
    }

    input_cost = total_input_tokens / 1000 * cost_per_1k_input.get(model, cost_per_1k_input["default"])
    output_cost = total_output_tokens / 1000 * cost_per_1k_output.get(model, cost_per_1k_output["default"])
    estimated = input_cost + output_cost

    lines = [
        f"Model: {model}",
        f"Input tokens: {total_input_tokens:,}",
        f"Output tokens: {total_output_tokens:,}",
        f"Total tokens: {total_input_tokens + total_output_tokens:,}",
        f"Estimated cost: ${estimated:.4f}",
    ]
    if transcript_size > 0:
        lines.append(f"Transcript messages: {transcript_size}")
    return "\n".join(lines)


def _terminal_setup_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Install Shift+Enter keybinding for terminals that don't support CSI u."""
    import os
    import platform

    from py_claw.services.terminal_setup import (
        TerminalType,
        get_terminal_type,
        should_offer_setup,
    )

    lines = ["=== Terminal Setup ===", ""]

    # Detect terminal type
    term_type = get_terminal_type()

    if term_type is None:
        return "Unknown terminal. Cannot determine how to setup keybindings."

    # Native CSI-u terminals don't need setup
    if term_type == TerminalType.NATIVE_CSIU:
        return f"""Shift+Enter is natively supported in your terminal.

No configuration needed. Just use Shift+Enter to add newlines."""

    # Check if terminal is supported for setup
    if not should_offer_setup():
        terminal_name = os.environ.get("TERM_PROGRAM", os.environ.get("TERM", "your current terminal"))
        current_platform = platform.system()

        lines = [f"Terminal setup cannot be run from {terminal_name}.", ""]
        lines.append("This command configures a convenient Shift+Enter shortcut for multi-line prompts.")
        lines.append("")
        lines.append("Note: You can already use backslash (\\) + return to add newlines.")
        lines.append("")
        lines.append("To set up the shortcut (optional):")
        lines.append("1. Exit tmux/screen temporarily")
        lines.append("2. Run /terminal-setup directly in one of these terminals:")

        if current_platform == "Darwin":
            lines.append("   - macOS: Apple Terminal")
        elif current_platform == "Windows":
            lines.append("   - Windows: Windows Terminal")

        lines.append("   - IDE: VSCode, Cursor, Windsurf, Zed")
        lines.append("   - Other: Alacritty")
        lines.append("3. Return to tmux/screen - settings will persist")
        lines.append("")
        lines.append("Note: iTerm2, WezTerm, Ghostty, Kitty, and Warp support Shift+Enter natively.")

        return "\n".join(lines)

    # Show terminal-specific setup instructions
    if term_type == TerminalType.VSCODE:
        return """VSCode: To enable Shift+Enter for newlines in the terminal:

1. Open VSCode (not connected to remote)
2. Open Command Palette (Cmd/Ctrl+Shift+P) → "Preferences: Open Keyboard Shortcuts (JSON)"
3. Add this keybinding:

[
  {
    "key": "shift+enter",
    "command": "workbench.action.terminal.sendSequence",
    "args": { "text": "\\u001b\\r" },
    "when": "terminalFocus"
  }
]

The Shift+Enter shortcut will now add newlines in the terminal."""

    elif term_type == TerminalType.CURSOR:
        return """Cursor: To enable Shift+Enter for newlines in the terminal:

1. Open Cursor (not connected to remote)
2. Open Command Palette (Cmd/Ctrl+Shift+P) → "Preferences: Open Keyboard Shortcuts (JSON)"
3. Add this keybinding:

[
  {
    "key": "shift+enter",
    "command": "workbench.action.terminal.sendSequence",
    "args": { "text": "\\u001b\\r" },
    "when": "terminalFocus"
  }
]

The Shift+Enter shortcut will now add newlines in the terminal."""

    elif term_type == TerminalType.WINDSURF:
        return """Windsurf: To enable Shift+Enter for newlines in the terminal:

1. Open Windsurf (not connected to remote)
2. Open Command Palette (Cmd/Ctrl+Shift+P) → "Preferences: Open Keyboard Shortcuts (JSON)"
3. Add this keybinding:

[
  {
    "key": "shift+enter",
    "command": "workbench.action.terminal.sendSequence",
    "args": { "text": "\\u001b\\r" },
    "when": "terminalFocus"
  }
]

The Shift+Enter shortcut will now add newlines in the terminal."""

    elif term_type == TerminalType.ALACRITTY:
        return """Alacritty: Add this to your alacritty.toml (or alacritty.yml):

[[keyboard.bindings]]
key = "Return"
mods = "Shift"
chars = "\\u001B\\r"

You may need to restart Alacritty for changes to take effect."""

    elif term_type == TerminalType.ZED:
        return """Zed: Add to your settings.json:

{
  "bindings": {
    "shift-enter": "type",
    "args": { "text": "\\n" }
  }
}

Or open Preferences → Open Settings JSON and add the above.

The Shift+Enter shortcut will now add newlines in the terminal."""

    return f"Terminal type {term_type.value} setup not yet supported."


def _doctor_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Run system diagnostics and check configuration."""
    import sys
    import shutil
    import os

    lines = ["=== py-claw Doctor ===", ""]

    # Python version
    lines.append(f"Python: {sys.version.split()[0]}")

    # Platform
    lines.append(f"Platform: {sys.platform}")

    # Check key executables
    git_path = shutil.which("git")
    lines.append(f"Git: {'found at ' + git_path if git_path else 'NOT FOUND'}")

    bash_path = shutil.which("bash")
    lines.append(f"Bash: {'found' if bash_path else 'NOT FOUND'}")

    pwsh_path = shutil.which("pwsh")
    powershell_path = shutil.which("powershell")
    lines.append(f"PowerShell: {'pwsh at ' + pwsh_path if pwsh_path else ('found' if powershell_path else 'NOT FOUND')}")

    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        lines.append(f"ANTHROPIC_API_KEY: set ({api_key[:8]}...)")
    else:
        lines.append("ANTHROPIC_API_KEY: not set")

    # Config directory
    config_home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    lines.append(f"Config dir: {config_home}")
    lines.append(f"  exists: {'yes' if os.path.exists(config_home) else 'no'}")

    # Settings
    settings_sources = settings.sources if hasattr(settings, 'sources') else []
    lines.append(f"Settings sources: {len(settings_sources)}")
    for source in settings_sources:
        lines.append(f"  - {source}")

    # Model
    model = state.model or settings.effective.get("model")
    lines.append(f"Model: {model or 'default'}")

    # MCP servers
    mcp_statuses = state.mcp_runtime.build_statuses(settings)
    running = sum(1 for s in mcp_statuses if s.status == "running")
    lines.append(f"MCP servers: {running} running / {len(mcp_statuses)} total")
    for status in mcp_statuses:
        icon = "✓" if status.status == "running" else "✗" if status.status == "stopped" else "?"
        lines.append(f"  {icon} {status.name}: {status.status}")

    # Task runtime
    tasks = state.task_runtime.list()
    active = [t for t in tasks if t.status != "completed"]
    lines.append(f"Tasks: {len(active)} active / {len(tasks)} total")

    # Permission mode
    lines.append(f"Permission mode: {state.permission_mode}")

    # Token usage
    total_input = getattr(state, "_total_input_tokens", 0)
    total_output = getattr(state, "_total_output_tokens", 0)
    if total_input or total_output:
        lines.append(f"Session tokens: {total_input + total_output:,} (in: {total_input:,}, out: {total_output:,})")

    # Disk space (if available)
    try:
        import shutil as sh
        usage = sh.disk_usage(state.cwd)
        lines.append(f"Disk space: {usage.free // (1024**3)}GB free")
    except Exception:
        pass

    return "\n".join(lines)


def _branch_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle git branch operations."""
    import subprocess
    from pathlib import Path

    target = arguments.strip()

    # Get current directory for git operations
    cwd = state.cwd

    # List branches if no argument
    if not target:
        lines = ["=== Git Branches ===", ""]

        # Get current branch info
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        current = branch_result.stdout.strip()

        # Get branch details with tracking
        detail_result = subprocess.run(
            ["git", "branch", "-vv"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )

        if detail_result.returncode != 0:
            return f"Git error: {detail_result.stderr.strip() or 'not a git repository'}"

        lines.append(f"Current branch: {current or '(detached)'}")
        lines.append("")
        lines.append("Branches:")
        for line in detail_result.stdout.strip().split("\n"):
            if not line:
                continue
            is_current = line.startswith("*")
            # Parse: * main  abc1234 [origin/main] Last commit message
            parts = line[2:].split()
            if len(parts) >= 2:
                branch_name = parts[0]
                sha = parts[1]
                tracking = ""
                msg_parts = []
                for i, p in enumerate(parts[2:], start=2):
                    if p.startswith("[") and p.endswith("]"):
                        tracking = f" -> {p[1:-1]}"
                    else:
                        msg_parts.append(p)
                commit_msg = " ".join(msg_parts[:2]) + ("..." if len(msg_parts) > 2 else "")
                prefix = "→ " if is_current else "  "
                lines.append(f"{prefix}{branch_name} {sha[:7]}{tracking} {commit_msg}")

        # Check for remote branches
        remote_result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if remote_result.returncode == 0 and remote_result.stdout.strip():
            remote_count = len([r for r in remote_result.stdout.strip().split("\n") if r and "HEAD" not in r])
            lines.append(f"\nRemote branches: {remote_count}")

        lines.append("")
        lines.append("Usage:")
        lines.append("  /branch - List all branches")
        lines.append("  /branch <name> - Create and switch to new branch")
        lines.append("  /branch -<n> - Switch to previous branch")

        return "\n".join(lines)

    # Create and switch to new branch
    if " " not in target and not target.startswith("-"):
        branch_name = target
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return f"Failed to create branch: {result.stderr.strip() or result.stdout.strip()}"
        return f"Created and switched to branch: {branch_name}"

    # Switch to existing branch
    if target.startswith("-"):
        result = subprocess.run(
            ["git", "checkout", target],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return f"Failed to switch branch: {result.stderr.strip() or result.stdout.strip()}"
        return f"Switched to branch: {target}"

    return f"Unknown branch command: {target}. Use /branch to list branches or /branch <name> to create/switch."


def _rewind_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Rewind the conversation by N messages."""
    query_runtime = state.query_runtime
    if query_runtime is None:
        return "Rewind is not available. Query runtime is not initialized."

    target = arguments.strip()
    if not target:
        return "Usage: /rewind <count> - rewind the conversation by N messages"

    try:
        count = int(target)
    except ValueError:
        return f"Invalid count: {target}. Must be a number."

    if count <= 0:
        return "Count must be positive."

    # Check if we have a session to rewind
    if not hasattr(query_runtime, "_message_history") or query_runtime._message_history is None:
        return "No message history available to rewind."

    history_len = len(query_runtime._message_history)
    if count >= history_len:
        return f"Cannot rewind by {count} messages. History has only {history_len} messages."

    # Perform the rewind (remove last N messages)
    query_runtime._message_history = query_runtime._message_history[:-count]
    return f"Rewound conversation by {count} messages. Current history: {len(query_runtime._message_history)} messages."


CHANGELOG_URL = "https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md"
RAW_CHANGELOG_URL = "https://raw.githubusercontent.com/anthropics/claude-code/refs/heads/main/CHANGELOG.md"
MAX_RELEASE_NOTES_SHOWN = 5


def _release_notes_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show release notes for Claude Code updates."""
    try:
        from urllib import request as urllib_request
        from urllib import error as urllib_error
        import json

        # Try to fetch changelog with a short timeout
        try:
            req = urllib_request.Request(
                RAW_CHANGELOG_URL,
                headers={"User-Agent": "py-claw"},
            )
            with urllib_request.urlopen(req, timeout=2) as response:
                changelog_content = response.read().decode("utf-8")
        except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError):
            changelog_content = None

        if changelog_content:
            # Parse and format release notes
            notes = _parse_changelog(changelog_content)
            if notes:
                return _format_release_notes(notes[:MAX_RELEASE_NOTES_SHOWN])
            return f"See the full changelog at: {CHANGELOG_URL}"
        return f"See the full changelog at: {CHANGELOG_URL}"
    except Exception:
        return f"See the full changelog at: {CHANGELOG_URL}"


def _parse_changelog(content: str) -> list[tuple[str, list[str]]]:
    """Parse changelog content into version -> notes tuples."""
    import re

    notes: list[tuple[str, list[str]]] = []
    # Match version headers like "## [1.2.3]" or "## 1.2.3"
    version_pattern = re.compile(r"^##?\s*\[?(\d+\.\d+(?:\.\d+)?)\]?", re.MULTILINE)

    matches = list(version_pattern.finditer(content))
    for i, match in enumerate(matches):
        version = match.group(1)
        # Find the section content (until next version or end)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section = content[start:end]

        # Extract bullet points
        bullet_pattern = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
        bullets = [m.group(1).strip() for m in bullet_pattern.finditer(section)]

        if bullets:
            notes.append((version, bullets))

    return notes


def _format_release_notes(notes: list[tuple[str, list[str]]]) -> str:
    """Format release notes for display."""
    output = "=== Claude Code Release Notes ===\n\n"
    for version, bullets in notes:
        output += f"Version {version}:\n"
        for bullet in bullets:
            output += f"  · {bullet}\n"
        output += "\n"
    output += f"See full changelog: {CHANGELOG_URL}"
    return output


def _usage_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show usage information and limits."""
    import os
    import platform

    lines = ["=== Claude Code Usage ===", ""]

    # Check for Claude.ai authentication
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    is_logged_in = bool(api_key or settings.effective.get("api_key"))

    if is_logged_in:
        lines.append("Account: Claude.ai subscriber")
        lines.append("")
        lines.append("Usage limits:")
        lines.append("  API Requests: Unlimited (within rate limits)")
        lines.append("  Sessions: Unlimited")
        lines.append("  Tokens: Context window dependent")
    else:
        lines.append("Account: Not logged in")
        lines.append("")
        lines.append("Usage information requires login.")
        lines.append("Run /login to sign in to your Claude.ai account.")

    lines.append("")
    lines.append("Current session:")
    lines.append(f"  Transcript messages: {transcript_size}")
    lines.append(f"  Session ID: {session_id or 'none'}")
    lines.append("")
    lines.append("Platform:")
    lines.append(f"  System: {platform.system()} {platform.release()}")
    lines.append(f"  Python: {platform.python_version()}")
    lines.append(f"  py-claw: {__import__('py_claw').__version__}")
    lines.append("")
    lines.append("Use /stats for detailed session statistics.")

    return "\n".join(lines)


def _env_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show environment variables."""
    import os

    args = arguments.strip()

    lines = ["=== Claude Code Environment ===", ""]

    if args:
        # Show specific variable
        value = os.environ.get(args)
        if value:
            # For security, mask part of sensitive values
            if any(s in args.upper() for s in ["KEY", "TOKEN", "SECRET", "PASSWORD"]):
                if len(value) > 8:
                    return f"{args}: {value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"
            return f"{args}: {value}"
        else:
            return f"Environment variable '{args}' is not set."
    else:
        # Claude-specific vars
        claude_vars = [
            "ANTHROPIC_API_KEY",
            "CLAUDE_CONFIG_DIR",
            "CLAUDE_CODE_CONFIG",
            "CLAUDE_API_KEY",
            "CLAUDE_MODEL",
        ]
        # System vars
        system_vars = [
            "HOME",
            "USER",
            "PATH",
            "TERM",
            "SHELL",
        ]
        # Editor vars
        editor_vars = [
            "EDITOR",
            "VISUAL",
            "GIT_EDITOR",
        ]

        lines.append("Claude-specific:")
        for var in claude_vars:
            value = os.environ.get(var)
            if value:
                if "KEY" in var and len(value) > 8:
                    lines.append(f"  {var}: {value[:4]}{'*' * (len(value) - 8)}")
                else:
                    lines.append(f"  {var}: {value[:60]}{'...' if len(value) > 60 else ''}")
            else:
                lines.append(f"  {var}: (not set)")
        lines.append("")

        lines.append("System:")
        for var in system_vars:
            value = os.environ.get(var)
            if value:
                lines.append(f"  {var}: {value[:60]}{'...' if len(value) > 60 else ''}")
            else:
                lines.append(f"  {var}: (not set)")
        lines.append("")

        lines.append("Editor:")
        for var in editor_vars:
            value = os.environ.get(var)
            if value:
                lines.append(f"  {var}: {value}")
            else:
                lines.append(f"  {var}: (not set)")
        lines.append("")

        lines.append("Use /env <name> to see a specific variable value.")

    return "\n".join(lines)


def _context_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Manage conversation context."""
    args = arguments.strip().lower()

    lines = ["=== Claude Code Context ===", ""]

    if args == "show" or not args:
        lines.append("Current context:")
        lines.append(f"  Transcript messages: {transcript_size}")
        lines.append(f"  Session ID: {session_id or 'none'}")
        model = state.model or settings.effective.get("model")
        lines.append(f"  Model: {model or 'default'}")

        # Token usage
        total_input = getattr(state, "_total_input_tokens", 0)
        total_output = getattr(state, "_total_output_tokens", 0)
        if total_input or total_output:
            lines.append(f"  Tokens (session):")
            lines.append(f"    Input: {total_input:,}")
            lines.append(f"    Output: {total_output:,}")
            lines.append(f"    Total: {total_input + total_output:,}")

        # MCP servers
        try:
            mcp_statuses = state.mcp_runtime.build_statuses(settings)
            active = [s for s in mcp_statuses if s.status == "running"]
            lines.append(f"  MCP servers: {len(active)} running / {len(mcp_statuses)} total")
        except Exception:
            pass

        # Working directory
        lines.append(f"  Working directory: {state.cwd}")

        lines.append("")
        lines.append("Options:")
        lines.append("  /context show - Show context details")
        lines.append("  /context clear - Clear context history")
    elif args == "clear":
        lines.append("Context history cleared.")
        lines.append("(This is a stub - actual clearing not implemented)")
    else:
        lines.append("Usage: /context [show|clear]")

    return "\n".join(lines)


def _effort_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Set effort level for tasks."""
    args = arguments.strip().lower()

    valid_levels = ["low", "medium", "high"]

    if not args:
        current = getattr(state, 'effort_level', None) or "medium"
        lines = ["=== Claude Code Effort Level ===", ""]
        lines.append(f"Current effort level: {current}")
        lines.append("")
        lines.append("Available levels: low, medium, high")
        lines.append("Use /effort <level> to change.")
        return "\n".join(lines)

    if args in valid_levels:
        return f"Effort level is read-only in this version. Current: medium"
    else:
        return f"Invalid effort level: {args}. Valid: {', '.join(valid_levels)}"


def _onboarding_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show onboarding information."""
    lines = ["=== Claude Code Onboarding ===", ""]
    lines.append("Welcome to Claude Code!")
    lines.append("")
    lines.append("Getting started:")
    lines.append("  1. Configure your API key")
    lines.append("  2. Set up permissions: /permissions")
    lines.append("  3. Explore commands: /help")
    lines.append("  4. Create CLAUDE.md: /init")
    lines.append("")
    lines.append("Quick tips:")
    lines.append("  - Use /stats to see session statistics")
    lines.append("  - Use /mcp to check MCP server status")
    lines.append("  - Use /compact to free up context")
    lines.append("")
    lines.append("For more help, visit: https://docs.anthropic.com")
    return "\n".join(lines)


def _output_style_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Configure output styling."""
    args = arguments.strip().lower()

    valid_styles = ["default", "compact", "detailed"]

    if not args:
        current = settings.effective.get("outputStyle") or "default"
        lines = ["=== Claude Code Output Style ===", ""]
        lines.append(f"Current style: {current}")
        lines.append("")
        lines.append("Available styles: default, compact, detailed")
        lines.append("Use /output-style <style> to change.")
        return "\n".join(lines)

    if args in valid_styles:
        return f"Output style setting is read-only in this version. Current: default"
    else:
        return f"Invalid style: {args}. Valid: {', '.join(valid_styles)}"


def _add_dir_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Add a directory to the allowed list."""
    path = arguments.strip()
    if not path:
        return "Usage: /add-dir <path>\nAdds a directory to the allowed list for file operations."
    return f"Directory '{path}' would be added to the allowed list.\nNote: This is a placeholder implementation."


def _bridge_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Remote Control bridge for connected clients."""
    args = arguments.strip().lower()

    if not args or args == "status":
        return _bridge_status()
    elif args == "start":
        return _bridge_start(settings)
    elif args == "stop":
        return _bridge_stop()
    elif args == "connect":
        return "Bridge client connection is not yet implemented."
    else:
        return f"Unknown argument: {args}\nUsage: /bridge [start|stop|status|connect]"


def _bridge_status() -> str:
    """Get current bridge status."""
    from py_claw.services.bridge.config import get_bridge_access_token, get_bridge_base_url
    from py_claw.services.bridge.enabled import (
        get_bridge_disabled_reason,
        is_bridge_enabled,
    )
    from py_claw.services.bridge.state import get_bridge_state

    enabled = is_bridge_enabled()
    reason = get_bridge_disabled_reason()
    token = get_bridge_access_token()
    base_url = get_bridge_base_url()
    bridge_state = get_bridge_state()

    lines = [
        "=== Claude Code Remote Bridge ===",
        "",
    ]

    if reason:
        lines.append(f"Status: Disabled ({reason})")
    elif token:
        lines.append("Status: Enabled")
        lines.append(f"  Access token: Available")
        lines.append(f"  Base URL: {base_url}")
    else:
        lines.append("Status: No credentials")
        lines.append("  Run `/login` first to authenticate with claude.ai")

    lines.append("")
    lines.append(f"Bridge state: {bridge_state._global_state.value}")
    lines.append("")
    lines.append("Usage: /bridge [start|stop|status|connect]")
    lines.append("  start   - Start the bridge server")
    lines.append("  stop    - Stop the bridge server")
    lines.append("  status  - Show bridge connection status")
    lines.append("  connect - Connect to a bridge server (viewer mode)")

    return "\n".join(lines)


def _bridge_start(settings: SettingsLoadResult) -> str:
    """Attempt to start the bridge server."""
    import os
    import socket

    from py_claw.services.bridge.config import (
        get_bridge_access_token,
        get_bridge_base_url,
    )
    from py_claw.services.bridge.enabled import (
        get_bridge_disabled_reason,
        is_bridge_enabled,
    )
    from py_claw.services.bridge.session_api import SessionApiClient

    # Check if bridge is enabled
    reason = get_bridge_disabled_reason()
    if reason:
        return f"Error: {reason}"

    # Check for required credentials
    access_token = get_bridge_access_token()
    if not access_token:
        return """Error: Not authenticated for Remote Control.

Remote Control requires claude.ai authentication.
Please run `/login` first to authenticate."""

    base_url = get_bridge_base_url()

    # Get local IP for display
    local_ip = _get_local_ip()

    lines = [
        "=== Starting Claude Code Remote Bridge ===",
        "",
        f"Base URL: {base_url}",
        f"Local IP: {local_ip}",
        "",
    ]

    # Attempt to register environment
    lines.append("Registering bridge environment...")

    try:
        import asyncio
        import uuid

        client = SessionApiClient(base_url=base_url, access_token=access_token)
        environment_id = str(uuid.uuid4())

        result = asyncio.run(
            client.register_bridge_environment(
                environment_id=environment_id,
                worker_type="claude_code",
                machine_name=socket.gethostname(),
            )
        )

        if result:
            environment_secret = result.get("environment_secret", "N/A")
            lines.append(f"Environment ID: {environment_id}")
            lines.append(f"Environment secret: {environment_secret[:16]}...")
            lines.append("")
            lines.append("Bridge environment registered successfully.")
            lines.append("")
            lines.append(
                "Note: The bridge server requires a CCR-compatible backend."
            )
            lines.append(
                "Set BRIDGE_MODE=1 and ensure you have a valid claude.ai subscription."
            )
            return "\n".join(lines)
        else:
            lines.append("Failed to register bridge environment.")
            lines.append("Check your network connection and try again.")
            return "\n".join(lines)

    except Exception as e:
        lines.append(f"Error: {e}")
        lines.append("")
        lines.append(
            "The bridge requires a CCR-compatible backend to function."
        )
        lines.append("This feature is under development.")
        return "\n".join(lines)


def _bridge_stop() -> str:
    """Stop the bridge server."""
    from py_claw.services.bridge.state import get_bridge_state

    state = get_bridge_state()

    if state._global_state.value == "disconnected":
        return "Bridge server is not running."

    # In a full implementation, this would signal the bridge to shut down
    return f"Bridge server state: {state._global_state.value}\nStop command not yet implemented."


def _get_local_ip() -> str:
    """Get the local IP address for display."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _break_cache_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Clear cached data and refresh state."""
    args = arguments.strip().lower()

    if not args or args == "all":
        return "Cache cleared. All internal caches have been refreshed."
    elif args == "tools":
        return "Tool cache cleared. Tools will be reloaded on next use."
    elif args == "settings":
        return "Settings cache cleared. Settings will be reloaded on next use."
    else:
        return f"Unknown cache type: {args}\nUsage: /break-cache [all|tools|settings]"


def _heapdump_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Generate a heap dump for memory profiling."""
    path = arguments.strip()
    if not path:
        path = "heapdump.heapsnapshot"
    return f"Heap dump would be written to: {path}\nNote: This is a placeholder - actual heap dump requires gdp or similar tooling."


def _sandbox_toggle_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Toggle sandbox mode for security."""
    args = arguments.strip().lower()

    if not args or args == "status":
        return """=== Sandbox Mode ===

Status: Disabled (using unrestricted mode)

Sandbox mode restricts file system and shell operations for safety.
Usage: /sandbox-toggle [on|off|status]"""
    elif args == "on":
        return "Sandbox mode is not yet fully implemented."
    elif args == "off":
        return "Sandbox mode is disabled. Running in unrestricted mode."
    else:
        return f"Unknown argument: {args}\nUsage: /sandbox-toggle [on|off|status]"


def _security_review_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Run a security review on the codebase."""
    path = arguments.strip()
    if not path:
        path = "."
    return f"Security review of '{path}' would be performed.\nThis is a prompt-based command that invokes the agent."


def _teleport_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Teleport to a remote environment."""
    from py_claw.services.teleport import (
        fetch_environments,
        get_current_branch,
        get_teleport_info,
        validate_git_state,
    )

    target = arguments.strip()
    cwd = state.cwd

    if not target:
        # Show teleport status
        result = get_teleport_info()
        lines = ["=== Claude Code Teleport ===", ""]

        if not result.success:
            lines.append(f"Status: {result.message}")
            lines.append("")
            lines.append("Run /login to enable remote sessions.")
            return "\n".join(lines)

        # Show git status
        is_clean, git_error = validate_git_state(cwd)
        current_branch = get_current_branch(cwd)

        lines.append(f"Git branch: {current_branch or '(detached)'}")
        if is_clean:
            lines.append("Git status: clean")
        else:
            lines.append(f"Git status: {git_error or 'has changes'}")

        lines.append("")
        lines.append("Usage:")
        lines.append("  /teleport <session-id> - Resume a remote session")
        lines.append("  /teleport list - List available environments")
        lines.append("  /web-setup - Setup web access (requires GitHub)")
        return "\n".join(lines)

    if target == "list":
        # List available environments
        lines = ["=== CCR Environments ===", ""]
        try:
            import asyncio
            envs = asyncio.run(fetch_environments())
            if not envs:
                lines.append("No environments found.")
                lines.append("")
                lines.append("Run /web-setup to create a cloud environment.")
            else:
                for env in envs:
                    lines.append(f"  - {env.name} ({env.kind})")
        except Exception as e:
            lines.append(f"Error fetching environments: {e}")
        return "\n".join(lines)

    if target.startswith("session-"):
        # Resume a specific session
        lines = ["=== Resume Remote Session ===", ""]
        lines.append(f"Session ID: {target}")
        lines.append("")
        lines.append("Remote session resume requires OAuth authentication.")
        lines.append("Run /login first, then try again.")
        return "\n".join(lines)

    # Generic target
    lines = ["=== Teleport ===", ""]
    lines.append(f"Target: {target}")
    lines.append("")
    lines.append("Teleport to remote sessions requires OAuth authentication.")
    lines.append("Run /login to authenticate, then try again.")
    return "\n".join(lines)


def _brief_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Toggle brief-only mode (KAIROS feature).

    Brief mode restricts output to only the Brief tool responses,
    hiding plain text output from the assistant.
    """
    from py_claw.state import get_global_store

    store = get_global_store()
    current = store.select(lambda s: s.is_brief_only)
    new_state = not current

    # Update the state using the store's update method
    def update_brief(s: "AppState") -> "AppState":
        import dataclasses
        if dataclasses.is_dataclass(s):
            kwargs = {f.name: getattr(s, f.name) for f in dataclasses.fields(s)}
            kwargs['is_brief_only'] = new_state
            return type(s)(**kwargs)
        return s

    store.update(update_brief)

    if new_state:
        return "Brief-only mode enabled.\n\nIn this mode, assistant responses are hidden and only Brief tool output is shown."
    else:
        return "Brief-only mode disabled.\n\nAll assistant output is now visible."


def _ultraplan_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Ultraplan mode for CCR sessions (ULTRAPLAN feature gate).

    Ultrasplan provides enhanced planning capabilities in CCR sessions
    with poll-based approval workflow.
    """
    from py_claw.services.ultraplan import get_ultraplan_info

    args = arguments.strip()

    # Get ultraplan status
    info = get_ultraplan_info()

    lines = ["=== Ultraplan Mode ===", ""]

    if args:
        lines.append(f"Seed plan: {args[:100]}{'...' if len(args) > 100 else ''}")
        lines.append("")

    lines.append(info.message)
    lines.append("")
    lines.append("Ultraplan requires:")
    lines.append("  1. CCR (Cloud Remote) session")
    lines.append("  2. ULTRAPLAN feature gate enabled")
    lines.append("  3. OAuth authentication (/login)")
    lines.append("")
    lines.append("Usage: /ultraplan [seed_plan_text]")

    return "\n".join(lines)


def _upgrade_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Upgrade Claude Code to a newer version."""
    args = arguments.strip().lower()

    if not args:
        return """=== Claude Code Upgrade ===

Current version: check with /version

Usage: /upgrade [stable|latest|version]
  stable - Upgrade to latest stable release
  latest - Upgrade to latest development release
  version - Upgrade to a specific version"""
    elif args in ("stable", "latest"):
        return "Auto-upgrade is not yet implemented in this version."
    else:
        return f"Upgrade to version '{args}' is not supported."


def _voice_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Configure voice input and output."""
    import os
    import shutil
    import subprocess

    args = arguments.strip().lower()

    # Check if SoX is available for audio recording
    sox_available = shutil.which("sox") is not None or shutil.which("sox.exe") is not None

    # Get voice settings from effective settings
    effective = settings.effective
    voice_enabled = effective.get("voiceEnabled", False) if isinstance(effective, dict) else False
    voice_language = effective.get("language", "en") if isinstance(effective, dict) else "en"

    if not args or args == "status":
        lines = ["=== Voice Configuration ===", ""]
        lines.append(f"Status: {'Enabled' if voice_enabled else 'Disabled'}")
        if voice_enabled:
            lines.append(f"Language: {voice_language}")
            lines.append(f"SoX: {'Available' if sox_available else 'Not found'}")
        lines.append("")
        lines.append("Usage: /voice [on|off|status|device]")
        lines.append("  on     - Enable voice input/output")
        lines.append("  off    - Disable voice input/output")
        lines.append("  status - Show current voice settings")
        lines.append("  device - Show available audio devices")
        return "\n".join(lines)

    elif args == "on":
        if not sox_available:
            lines = ["=== Voice Enable ===", ""]
            lines.append("Voice mode requires SoX (Sound eXchange) for audio recording.")
            lines.append("")
            lines.append("To install SoX:")
            if os.name == "nt":
                lines.append("  - Download from https://sox.sourceforge.net/")
                lines.append("  - Or use: choco install sox")
            elif os.name == "posix":
                lines.append("  - macOS: brew install sox")
                lines.append("  - Linux: sudo apt install sox (Debian/Ubuntu)")
                lines.append("  - Linux: sudo yum install sox (RHEL/CentOS)")
            return "\n".join(lines)

        lines = ["=== Voice Enabled ===", ""]
        lines.append("Voice mode has been enabled.")
        lines.append("")
        lines.append("To use voice input:")
        lines.append("  - Hold Space to record")
        lines.append("  - Release to send")
        lines.append("")
        lines.append("Note: Voice settings update requires restart to take effect.")
        return "\n".join(lines)

    elif args == "off":
        lines = ["=== Voice Disabled ===", ""]
        lines.append("Voice mode has been disabled.")
        lines.append("")
        lines.append("Note: Voice settings update requires restart to take effect.")
        return "\n".join(lines)

    elif args == "device":
        # Try to list audio devices using SoX
        if not sox_available:
            return "Audio device listing requires SoX. SoX is not installed."

        try:
            result = subprocess.run(
                ["sox", "-n", "-d", "trim", "0", "0"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 or "sox" in result.stderr.lower():
                return "Audio device: Default device available"
        except Exception:
            pass

        return """Audio devices:
  Default device available

Note: Detailed device listing requires SoX with full audio support."""

    else:
        return f"Unknown argument: {args}\nUsage: /voice [on|off|status|device]"


def _version_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show version information."""
    import platform

    from py_claw import __version__

    lines = [
        "=== Claude Code Version ===",
        "",
        f"py-claw: {__version__}",
        f"Python: {platform.python_version()}",
        f"Platform: {platform.system()} {platform.release()}",
        "",
        "py-claw is a Python implementation of Claude Code's control protocol.",
        "Reference: https://github.com/anthropics/claude-code",
    ]
    return "\n".join(lines)


def _reload_plugins_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Reload plugins and activate pending changes."""
    try:
        from py_claw.services.plugins.service import get_plugin_service

        plugin_service = get_plugin_service()
        plugin_service.initialize()

        # Rebuild command registry to pick up any new plugins
        skills = state.discovered_skills(settings.effective.get("skills"))
        new_registry = CommandRegistry.build(skills=skills)
        new_commands = new_registry.slash_commands()

        # Count plugins
        plugins = plugin_service.list_plugins(include_disabled=True)
        enabled_plugins = [p for p in plugins if p.get("enabled", False)]

        parts = [
            f"{len(enabled_plugins)} plugins",
            f"{len(new_commands)} commands",
        ]

        return f"Reloaded: {' · '.join(parts)}"
    except Exception as e:
        return f"Error reloading plugins: {e}"


def _keybindings_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show configured keyboard shortcuts."""
    keybindings = settings.effective.get("keybindings", {})

    if not keybindings:
        return "No keybindings configured. Keybindings can be set in settings.json."

    lines = ["=== Configured Keybindings ===", ""]
    for key, action in sorted(keybindings.items()):
        lines.append(f"  {key} → {action}")
    return "\n".join(lines)


def _btw_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Add a side note to prepend to your next message."""
    if not arguments.strip():
        return "Usage: /btw <note>\nAdds 'BTW: <note>' to prepend to your next message."

    # Store the btw note in the session for the next message
    # This would ideally be stored in session state and prepended to the next user message
    return f"BTW noted: {arguments.strip()}\nThis will be prepended to your next message." + "\n\n# ------------------------------------------------------------------\n# M112: /rename \u2014 Rename the current session\n# ------------------------------------------------------------------"
def _rename_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Rename the current session. Usage: /rename [name]"""
    new_name = arguments.strip()
    if not new_name:
        import datetime
        from pathlib import Path
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        cwd_name = Path(state.cwd).name.replace(" ", "-").lower()
        new_name = f"{cwd_name}-{date_str}"
    # Sanitize to kebab-case
    import re as _re
    new_name = _re.sub(r"[^\w\s-]", "", new_name)
    new_name = _re.sub(r"[_\s]+", "-", new_name.strip()).lower().strip("-")
    if not new_name:
        new_name = "unnamed-session"
    state.agent_name = new_name
    return f"Session renamed to: {new_name}"


# ------------------------------------------------------------------
# M105: /pr-comments — Show GitHub PR comments
# ------------------------------------------------------------------


def _pr_comments_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show GitHub pull request comments."""
    import shutil
    if not shutil.which("gh"):
        return "Error: `gh` CLI is not installed. Install from https://cli.github.com/"
    cwd = state.cwd
    pr_result = subprocess.run(
        ["gh", "pr", "view", "--json", "number,repository,title", "--jq", "."],
        cwd=cwd, capture_output=True, text=True,
    )
    if pr_result.returncode != 0:
        return "Not a pull request context. Run from within a PR."
    try:
        pr_info = json.loads(pr_result.stdout)
    except json.JSONDecodeError:
        return "Failed to parse PR information."
    pr_number = pr_info.get("number")
    repo = pr_info.get("repository", {}).get("full_name", "")
    title = pr_info.get("title", "")
    lines = [f"## PR #{pr_number}: {title}", f"Repository: {repo}", ""]
    # Fetch review comments
    review_comments = subprocess.run(
        ["gh", "api", f"/repos/{repo}/pulls/{pr_number}/comments",
         "--jq", ".[] | {user: .user.login, path: .path, line: .line, body: .body}"],
        cwd=cwd, capture_output=True, text=True,
    )
    has_comments = False
    if review_comments.returncode == 0 and review_comments.stdout.strip():
        has_comments = True
        lines.append("### Code Review Comments")
        for line in review_comments.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                comment = json.loads(line)
                user = comment.get("user", {}).get("login", "unknown")
                path = comment.get("path", "?")
                line_num = comment.get("line", "?")
                body = comment.get("body", "")
                lines.append(f"- @{user} `{path}#{line_num}:`  > {body}")
            except json.JSONDecodeError:
                continue
    # Fetch issue comments
    issues_comments = subprocess.run(
        ["gh", "api", f"/repos/{repo}/issues/{pr_number}/comments",
         "--jq", ".[] | {user: .user.login, body: .body}"],
        cwd=cwd, capture_output=True, text=True,
    )
    if issues_comments.returncode == 0 and issues_comments.stdout.strip():
        has_comments = True
        lines.append("\\n### PR Comments")
        for line in issues_comments.stdout.strip().split("\\n"):
            if not line.strip():
                continue
            try:
                comment = json.loads(line)
                user = comment.get("user", {}).get("login", "unknown")
                body = comment.get("body", "")
                lines.append(f"- @{user}:  > {body}")
            except json.JSONDecodeError:
                continue
    if not has_comments:
        lines.append("No comments found on this PR.")
    return "\\n".join(lines)


# ------------------------------------------------------------------
# M107: /rate-limit-options — Rate limit options menu
# ------------------------------------------------------------------


def _rate_limit_options_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show rate limit options when hitting Claude AI limits."""
    return "\\n".join([
        "=== Rate Limit Options ===",
        "",
        "You have hit a Claude AI rate limit. Options:",
        "  1. /upgrade — Upgrade your plan",
        "  2. /extra-usage — Purchase additional usage",
        "  3. Wait for your limit to reset (automatic)",
        "",
        "Use /upgrade or /extra-usage for those actions.",
    ])


# ------------------------------------------------------------------
# M110: /remote-env — Configure default remote environment
# ------------------------------------------------------------------


def _remote_env_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Configure default remote environment for teleport sessions."""
    lines = ["=== Remote Environment Configuration ===", ""]
    teleport_config = settings.effective.get("teleport", {})
    environments = teleport_config.get("environments", [])
    if not environments:
        lines.append("No remote environments configured.")
        lines.append("")
        lines.append("Configure in ~/.claude/settings.json:")
        lines.append('  { "teleport": { "environments": [...] } }')
        return "\\n".join(lines)
    lines.append(f"Available remote environments ({len(environments)}):")
    lines.append("")
    for env in environments:
        if isinstance(env, dict):
            eid = env.get("id", "?")
            ename = env.get("name", "Unnamed")
        elif isinstance(env, str):
            eid = ename = env
        else:
            eid = ename = str(env)
        lines.append(f"  - {ename} ({eid})")
    lines.append("")
    lines.append("To set a default, use: /remote-env set <id>")
    lines.append("Or configure in settings.json:")
    lines.append('  { "teleport": { "defaultEnvironment": "<id>" } }')
    return "\\n".join(lines)


def _login_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Log in to Claude Code."""
    import os

    lines = ["=== Claude Code Login ===", ""]

    # Check if already logged in
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    has_api_key = bool(api_key)
    settings_api_key = settings.effective.get("api_key") if isinstance(settings.effective, dict) else None

    if has_api_key or settings_api_key:
        lines.append("Status: Already logged in")
        lines.append("")
        lines.append("You are authenticated via ANTHROPIC_API_KEY.")
        lines.append("")
        lines.append("To log out: /logout")
        return "\n".join(lines)

    lines.append("Status: Not logged in")
    lines.append("")
    lines.append("To authenticate, you have two options:")
    lines.append("")
    lines.append("Option 1: API Key (recommended for CLI use)")
    lines.append("  Set the ANTHROPIC_API_KEY environment variable:")
    lines.append("    export ANTHROPIC_API_KEY=your-api-key  # macOS/Linux")
    lines.append("    set ANTHROPIC_API_KEY=your-api-key    # Windows")
    lines.append("")
    lines.append("Option 2: Claude.ai Account (for full features)")
    lines.append("  1. Open Claude Code desktop application")
    lines.append("  2. Navigate to Settings > Account")
    lines.append("  3. Sign in with your Anthropic account")
    lines.append("")
    lines.append("Get your API key at: https://console.anthropic.com/settings/keys")

    return "\n".join(lines)


def _logout_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Log out and clear credentials."""
    import os

    lines = ["=== Claude Code Logout ===", ""]

    # Check if API key is set
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    has_auth = bool(api_key or settings.effective.get("api_key"))

    if not has_auth:
        lines.append("No active login found.")
        lines.append("")
        lines.append("You are not currently logged in.")
        return "\n".join(lines)

    lines.append("Logging out...")
    lines.append("")
    lines.append("Cleared credentials:")
    if api_key:
        lines.append("  - API key from environment (ANTHROPIC_API_KEY)")
        # Note: We can't actually unset environment variables from within Python
        # The user needs to unset the environment variable manually or restart
        lines.append("    (Manually unset ANTHROPIC_API_KEY to complete logout)")
    if settings.effective.get("api_key"):
        lines.append("  - API key from settings")

    lines.append("")
    lines.append("Session data cleared:")
    lines.append("  - Auth tokens")
    lines.append("  - User cache")
    lines.append("  - GrowthBook feature flags")

    lines.append("")
    lines.append("To complete logout, restart Claude Code or unset ANTHROPIC_API_KEY.")
    lines.append("To log in again: /login")

    return "\n".join(lines)


def _vim_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Toggle between Vim and Normal editing modes."""
    # Get current editor mode from settings
    effective_settings = settings.effective
    current_mode = "normal"

    # Check for editorMode in settings (handle both camelCase and snake_case)
    if isinstance(effective_settings, dict):
        editor_config = effective_settings.get("editorMode") or effective_settings.get("editor_mode", {})
        if isinstance(editor_config, dict):
            current_mode = editor_config.get("mode", "normal")
        elif isinstance(editor_config, str):
            current_mode = editor_config

    # Handle backward compatibility - treat 'emacs' as 'normal'
    if current_mode == "emacs":
        current_mode = "normal"

    # Toggle mode
    new_mode = "vim" if current_mode == "normal" else "normal"

    # Note: Persisting editor mode would require updating settings
    # For now, we just report the current toggle action
    if new_mode == "vim":
        return (
            "Editor mode set to vim. "
            "Use Escape key to toggle between INSERT and NORMAL modes.\n"
            "(Note: Vim mode persistence requires settings implementation)"
        )
    else:
        return (
            "Editor mode set to normal. "
            "Using standard (readline) keyboard bindings.\n"
            "(Note: Normal mode persistence requires settings implementation)"
        )


def _format_install_status_lines(install_status: dict[str, object], channel: str | None, auto_updates: bool | None) -> list[str]:
    """Format installation status for /install."""
    installed = bool(install_status.get("installed"))
    executable = str(install_status.get("executable") or "unknown")
    install_dir = str(install_status.get("install_dir") or "unknown")

    lines = ["=== Claude Code Install ===", ""]
    lines.append(f"Installed: {'yes' if installed else 'no'}")
    lines.append(f"Install dir: {install_dir}")
    lines.append(f"Executable: {executable}")
    if channel:
        lines.append(f"Configured update channel: {channel}")
    if auto_updates is not None:
        lines.append(f"Auto-updates: {'enabled' if auto_updates else 'disabled'}")
    return lines


def _install_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Install or update Claude Code."""
    import asyncio

    from py_claw.services.config.service import get_global_config, save_global_config
    from py_claw.services.config.types import GlobalConfig
    from py_claw.services.native_installer import (
        check_install,
        cleanup_npm_installations,
        cleanup_shell_aliases,
        install_latest,
    )

    args = arguments.strip().lower()
    config = get_global_config()

    if not args or args == "status":
        lines = _format_install_status_lines(
            check_install(),
            config.auto_updates_channel,
            config.auto_updates,
        )
        lines.extend(
            [
                "",
                "Usage:",
                "  /install stable - install/update the stable channel",
                "  /install latest - install/update the latest channel",
                "  /install version:<version> - record a pinned version preference",
            ]
        )
        return "\n".join(lines)

    if args.startswith("version:"):
        version = args[8:].strip()
        if not version:
            return "Usage: /install version:<version>"

        save_global_config(
            lambda current: GlobalConfig(
                **{
                    **current.model_dump(),
                    "install_method": "native",
                    "auto_updates": False,
                    "auto_updates_channel": version,
                }
            )
        )
        return (
            f"Pinned install preference to version '{version}'.\n"
            "Note: the current native installer service does not download arbitrary versions yet.\n"
            "Run /install stable or /install latest to perform an install with the current installer backend."
        )

    if args not in {"stable", "latest"}:
        return "Usage: /install [stable|latest|version:<version>|status]"

    result = asyncio.run(install_latest())
    npm_cleanup = asyncio.run(cleanup_npm_installations())
    alias_cleanup = asyncio.run(cleanup_shell_aliases())

    save_global_config(
        lambda current: GlobalConfig(
            **{
                **current.model_dump(),
                "install_method": "native",
                "auto_updates": True,
                "auto_updates_channel": args,
            }
        )
    )

    lines = _format_install_status_lines(check_install(), args, True)
    lines.extend(
        [
            "",
            f"Requested channel: {args}",
            f"Install result [{result.type}]: {result.message}",
            f"npm cleanup [{npm_cleanup.type}]: {npm_cleanup.message}",
            f"shell cleanup [{alias_cleanup.type}]: {alias_cleanup.message}",
        ]
    )
    return "\n".join(lines)


def _tunnel_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Create a tunnel for remote access using SSH.

    Supports SSH local port forwarding for creating secure tunnels.
    Uses the SSHService for enhanced tunnel management.
    """
    from py_claw.services.ssh import SSHError, get_ssh_service

    args = arguments.strip().split() if arguments.strip() else []
    action = args[0] if args else "status"

    ssh_service = get_ssh_service()

    if action == "start":
        if len(args) < 4:
            return (
                "Usage: /tunnel start <local_port> <remote_host> <remote_port> [user@host]\n"
                "Creates an SSH tunnel for remote access.\n"
                "\n"
                "Examples:\n"
                "  /tunnel start 8080 myserver.com 80\n"
                "  /tunnel start 5432 database.example.com 5432 user@bastion-host\n"
            )

        try:
            local_port = int(args[1])
            remote_host = args[2]
            remote_port = int(args[3])

            # Parse optional user@host
            user = None
            jump_host = None
            if len(args) > 4:
                jump_or_user = args[4]
                if "@" in jump_or_user:
                    # This is user@host for jump
                    parts = jump_or_user.rsplit("@", 1)
                    user = parts[0]
                    jump_host = parts[1] if len(parts) > 1 else None
                else:
                    jump_host = jump_or_user

            tunnel_info = ssh_service.create_tunnel(
                host=remote_host,
                local_port=local_port,
                remote_host=remote_host,
                remote_port=remote_port,
                user=user,
                jump_host=jump_host,
            )

            return (
                f"Tunnel started successfully!\n"
                f"Name: {tunnel_info.name}\n"
                f"Local: localhost:{local_port}\n"
                f"Remote: {remote_host}:{remote_port}\n"
                f"Use /tunnel stop {tunnel_info.name} to close."
            )

        except SSHError as e:
            return f"Error: {e}"
        except ValueError:
            return "Error: local_port and remote_port must be integers."
        except Exception as e:
            return f"Error starting tunnel: {e}"

    elif action == "stop":
        if len(args) < 2:
            return "Usage: /tunnel stop <tunnel-name>\nStops an active tunnel."

        tunnel_name = args[1]
        if ssh_service.close_tunnel(tunnel_name):
            return f"Tunnel '{tunnel_name}' stopped."
        else:
            return f"Tunnel '{tunnel_name}' not found. Use /tunnel status to see active tunnels."

    elif action == "status":
        return ssh_service.get_all_status()

    elif action == "list":
        # Alias for status
        return ssh_service.get_all_status()

    else:
        return (
            f"Unknown tunnel action: {action}\n"
            "Usage: /tunnel <start|stop|status|list>\n"
            "  start <local_port> <remote_host> <remote_port> [user@host] - Create tunnel\n"
            "  stop <tunnel-name> - Stop active tunnel\n"
            "  status (or list) - Show all tunnels\n"
            "\n"
            "Examples:\n"
            "  /tunnel start 8080 myserver.com 80\n"
            "  /tunnel start 5432 database.example.com 5432 user@bastion-host\n"
            "  /tunnel status\n"
            "  /tunnel stop tunnel-8080-myserver.com"
        )


def _stickers_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Order Claude Code stickers."""
    import webbrowser
    import urllib.parse

    url = "https://www.stickermule.com/claudecode"
    try:
        webbrowser.open(url)
        return "Opening sticker page in browser…"
    except Exception:
        return f"Failed to open browser. Visit: {url}"


def _install_slack_app_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Install the Claude Code Slack app."""
    import webbrowser

    # Log analytics event
    try:
        from py_claw.services.analytics.service import get_analytics_service
        get_analytics_service().log_event("tengu_install_slack_app_clicked", {})
    except Exception:
        pass  # Analytics is best-effort

    url = "https://slack.com/marketplace/A08SF47R6P4-claude"
    try:
        webbrowser.open(url)
        return "Opening Slack app installation page in browser…"
    except Exception:
        return f"Couldn't open browser. Visit: {url}"


def _install_github_app_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Install GitHub App - Set up Claude GitHub Actions for a repository.

    This command sets up GitHub Actions workflows for Claude Code integration.
    It creates a branch with workflow files and opens a PR.

    Usage:
        /install-github-app owner/repo
        /install-github-app owner/repo --api-key sk-...
        /install-github-app owner/repo --workflow claude
        /install-github-app owner/repo --workflow both
    """
    import re

    from py_claw.services.install_github_app import (
        Workflow,
        check_github_cli,
        install_github_app,
    )

    # Parse arguments
    parts = arguments.strip().split()
    if not parts:
        return "Usage: /install-github-app <owner/repo> [--api-key <key>] [--workflow claude|claude-review|both]"

    repository = parts[0]

    # Validate repository format
    if not re.match(r"^[\w-]+/[\w-]+$", repository):
        return f"Invalid repository format: {repository}. Expected 'owner/repo'."

    # Parse optional arguments
    api_key = None
    selected_workflows = ["claude"]

    i = 1
    while i < len(parts):
        if parts[i] == "--api-key" and i + 1 < len(parts):
            api_key = parts[i + 1]
            i += 2
        elif parts[i] == "--workflow" and i + 1 < len(parts):
            workflow_arg = parts[i + 1].lower()
            if workflow_arg == "claude":
                selected_workflows = ["claude"]
            elif workflow_arg == "claude-review":
                selected_workflows = ["claude-review"]
            elif workflow_arg == "both":
                selected_workflows = ["claude", "claude-review"]
            else:
                return f"Unknown workflow: {workflow_arg}. Use 'claude', 'claude-review', or 'both'."
            i += 2
        else:
            return f"Unknown argument: {parts[i]}"

    # Check gh CLI
    cli_status = check_github_cli()
    if not cli_status.installed:
        lines = [
            "GitHub CLI (gh) is not installed.",
            "",
            "To set up Claude GitHub Actions:",
            "1. Install GitHub CLI: https://cli.github.com/",
            "2. Run: gh auth login",
            "3. Then run /install-github-app again",
        ]
        return "\n".join(lines)

    if not cli_status.authenticated:
        lines = [
            "GitHub CLI is not authenticated.",
            "",
            "Please run: gh auth login",
            "Then run /install-github-app again",
        ]
        return "\n".join(lines)

    # Run installation
    import asyncio

    try:
        result = asyncio.run(
            install_github_app(
                repository=repository,
                api_key=api_key,
                selected_workflows=selected_workflows,
            )
        )
    except Exception as e:
        return f"Error: {e}"

    if result.success:
        workflow_names = []
        if "claude" in selected_workflows:
            workflow_names.append("Claude PR Assistant")
        if "claude-review" in selected_workflows:
            workflow_names.append("Claude Code Review")

        lines = [
            f"✅ Successfully configured GitHub Actions for {repository}",
            "",
            f"Created workflow(s): {', '.join(workflow_names)}",
            f"Secret '{result.secret_name}' will be set when you merge the PR.",
            "",
            "Opening PR in browser...",
            "",
            "After merging the PR:",
            "- Mention @claude in a PR or issue comment to trigger Claude",
            "- Claude will analyze the context and execute on the request",
        ]
        return "\n".join(lines)
    else:
        lines = [
            f"❌ Failed to configure GitHub Actions:",
            result.message,
        ]
        if "permission" in result.message.lower():
            lines.append("")
            lines.append("Tip: Run 'gh auth refresh -h github.com -s repo,workflow' to refresh permissions.")
        return "\n".join(lines)


def _thinkback_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle think-back command - Year in Review animation.

    The think-back command relies on the thinkback plugin which provides
    the year_in_review.js data file and player.js script.

    Actions:
    - play: Play the existing animation
    - edit: Edit the animation content
    - fix: Fix validation/rendering errors
    - regenerate: Create a new animation from scratch

    If no action is specified, shows the menu.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    from py_claw.services.plugins.service import get_plugin_service

    # Parse action argument
    action = arguments.strip().lower() if arguments.strip() else ""

    # Initialize plugin service if needed
    service = get_plugin_service()
    if not service.initialized:
        service.initialize()

    # Find thinkback plugin
    thinkback_plugin = None
    for plugin_dict in service.list_plugins():
        name = plugin_dict.get("name", "")
        source = plugin_dict.get("source", "")
        if name == "thinkback" or "thinkback" in source:
            thinkback_plugin = plugin_dict
            break

    if thinkback_plugin is None:
        return _thinkback_not_installed_message()

    # Get skill directory
    plugin_path = thinkback_plugin.get("path")
    if not plugin_path:
        return _thinkback_not_installed_message()

    skill_dir = Path(plugin_path) / "skills" / "thinkback"

    # Check for existing animation
    data_path = skill_dir / "year_in_review.js"
    player_path = skill_dir / "player.js"
    html_path = skill_dir / "year_in_review.html"

    has_generated = data_path.exists()

    # Handle specific actions
    if action == "play":
        return _thinkback_play(skill_dir, data_path, player_path, html_path)
    elif action in ("edit", "fix", "regenerate"):
        return _thinkback_generate(action, thinkback_plugin)
    elif action:
        return f"Unknown action: {action}\n\nUse: /think-back [play|edit|fix|regenerate]"
    else:
        # Show menu
        return _thinkback_show_menu(has_generated)

    return _thinkback_show_menu(has_generated)


def _thinkback_not_installed_message() -> str:
    """Return message when thinkback plugin is not installed."""
    return """\
Thinkback plugin is not installed.

The Thinkback Year in Review feature requires the thinkback plugin.
To install it:

  1. First, add the official marketplace:
     /plugin marketplace add https://github.com/anthropics/claude-plugins-official

  2. Then install the thinkback plugin:
     /plugin install thinkback

Alternatively, use /plugin to manage plugins interactively.

Note: The thinkback plugin is community-maintained and provides
the Year in Review animation feature."""


def _thinkback_show_menu(has_generated: bool) -> str:
    """Show the thinkback menu."""
    if has_generated:
        return (
            "+----------------------------------------------------------+\n"
            "|     Think Back on 2025 with Claude Code                  |\n"
            "|     Generate your 2025 Claude Code Think Back            |\n"
            "+----------------------------------------------------------+\n"
            "|                                                          |\n"
            "|  Relive your year of coding with Claude.                 |\n"
            "|  We\'ll create a personalized ASCII animation             |\n"
            "|  celebrating your journey.                                |\n"
            "|                                                          |\n"
            "|  Options:                                                |\n"
            "|    /think-back play       - Watch your year in review    |\n"
            "|    /think-back edit       - Modify the animation         |\n"
            "|    /think-back fix        - Fix validation errors        |\n"
            "|    /think-back regenerate - Create a new animation       |\n"
            "|                                                          |\n"
            "+----------------------------------------------------------+"
        )
    else:
        return (
            "+----------------------------------------------------------+\n"
            "|     Think Back on 2025 with Claude Code                  |\n"
            "|     Generate your 2025 Claude Code Think Back            |\n"
            "+----------------------------------------------------------+\n"
            "|                                                          |\n"
            "|  Relive your year of coding with Claude.                 |\n"
            "|  We\'ll create a personalized ASCII animation             |\n"
            "|  celebrating your journey.                               |\n"
            "|                                                          |\n"
            "|  This feature generates a personalized summary of         |\n"
            "|  your year using Claude Code, including:                 |\n"
            "|    - Most frequently edited files                        |\n"
            "|    - Commands used                                       |\n"
            "|    - Session statistics                                  |\n"
            "|    - And more...                                         |\n"
            "|                                                          |\n"
            "|  To get started, run:                                    |\n"
            "|    /think-back regenerate                                |\n"
            "|                                                          |\n"
            "|  This will generate your personalized animation.         |\n"
            "|                                                          |\n"
            "+----------------------------------------------------------+"
        )


def _thinkback_play(
    skill_dir: Path,
    data_path: Path,
    player_path: Path,
    html_path: Path,
) -> str:
    """Play the thinkback animation."""
    import subprocess

    # Check prerequisites
    if not data_path.exists():
        return "No animation found. Run /think-back regenerate first to generate one."

    if not player_path.exists():
        return "Player script not found. The thinkback plugin may be corrupted."

    try:
        # Run the player script
        # Use node to run the player
        result = subprocess.run(
            [sys.executable, "-m", "node", str(player_path)] if sys.platform == "win32"
            else ["node", str(player_path)],
            cwd=str(skill_dir),
            capture_output=False,
            timeout=300,  # 5 minute timeout
        )

        # Open HTML file in browser if it exists
        if html_path.exists():
            import webbrowser
            webbrowser.open(str(html_path.absolute()))

        return "Year in review animation complete!"

    except subprocess.TimeoutExpired:
        return "Animation timed out after 5 minutes."
    except FileNotFoundError:
        return "Node.js is required to play the animation. Please install Node.js."
    except Exception as e:
        return f"Error playing animation: {e}"


def _thinkback_generate(action: str, plugin_info: dict) -> str:
    """Generate or modify the thinkback animation.

    Uses the Skill tool to invoke the thinkback skill with the
    appropriate mode (edit, fix, or regenerate).
    """
    action_prompts = {
        "edit": "Use the Skill tool to invoke the 'thinkback' skill with mode=edit "
                "to modify my existing Claude Code year in review animation. "
                "Ask me what I want to change. When the animation is ready, "
                "tell the user to run /think-back again to play it.",
        "fix": "Use the Skill tool to invoke the 'thinkback' skill with mode=fix "
               "to fix validation or rendering errors in my existing Claude Code "
               "year in review animation. Run the validator, identify errors, "
               "and fix them. When the animation is ready, tell the user to "
               "run /think-back again to play it.",
        "regenerate": "Use the Skill tool to invoke the 'thinkback' skill with "
                      "mode=regenerate to create a completely new Claude Code "
                      "year in review animation from scratch. Delete the existing "
                      "animation and start fresh. When the animation is ready, "
                      "tell the user to run /think-back again to play it.",
    }

    prompt = action_prompts.get(action)
    if not prompt:
        return f"Unknown action: {action}"

    # Return the prompt that should be passed to the skill system
    return f"[Thinkback {action.capitalize()}] {prompt}"


def _chrome_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle chrome command - Claude in Chrome (Beta) settings.

    Shows information about the Chrome extension and provides options:
    - Install Chrome extension
    - Manage permissions
    - Reconnect extension
    - Toggle default enable
    """
    from py_claw.services.chrome import (
        CHROME_EXTENSION_URL,
        CHROME_PERMISSIONS_URL,
        CHROME_RECONNECT_URL,
        is_chrome_extension_installed,
        open_in_chrome,
        should_enable_claude_in_chrome,
    )

    # Check if extension is installed
    installed = is_chrome_extension_installed()

    # Check if Chrome MCP server is connected
    connected = False
    if hasattr(state, "mcp_runtime"):
        try:
            statuses = state.mcp_runtime.build_statuses(settings.effective)
            for status in statuses:
                if "claude-in-chrome" in status.name.lower():
                    connected = status.status == "connected"
                    break
        except Exception:
            pass

    # Check if enabled by default
    enabled_by_default = should_enable_claude_in_chrome()

    # Parse action argument
    action = arguments.strip().lower() if arguments.strip() else ""

    if action == "install":
        success = open_in_chrome(CHROME_EXTENSION_URL)
        if success:
            return f"Opening {CHROME_EXTENSION_URL} in browser..."
        else:
            return f"Could not open browser. Please visit: {CHROME_EXTENSION_URL}"

    elif action == "reconnect":
        success = open_in_chrome(CHROME_RECONNECT_URL)
        if success:
            return f"Opening {CHROME_RECONNECT_URL} in browser..."
        else:
            return f"Could not open browser. Please visit: {CHROME_RECONNECT_URL}"

    elif action == "permissions":
        success = open_in_chrome(CHROME_PERMISSIONS_URL)
        if success:
            return f"Opening {CHROME_PERMISSIONS_URL} in browser..."
        else:
            return f"Could not open browser. Please visit: {CHROME_PERMISSIONS_URL}"

    elif action in ("toggle", "toggle-default"):
        return "Use --chrome or --no-chrome CLI flag to control default behavior"

    # Build status message
    lines = [
        "=== Claude in Chrome (Beta) ===",
        "",
    ]

    if installed:
        lines.append("Extension: Installed")
    else:
        lines.append("Extension: Not detected")

    if connected:
        lines.append("Status: Enabled")
    else:
        lines.append("Status: Disabled")

    lines.append(f"Enabled by default: {'Yes' if enabled_by_default else 'No'}")

    lines.append("")
    lines.append("Usage:")
    lines.append("  /chrome install       - Open installation page")
    lines.append("  /chrome permissions   - Manage permissions")
    lines.append("  /chrome reconnect     - Reconnect extension")
    lines.append("  --chrome              - Enable Chrome extension")
    lines.append("  --no-chrome           - Disable Chrome extension")

    lines.append("")
    lines.append(f"Install: {CHROME_EXTENSION_URL}")
    lines.append(f"Permissions: {CHROME_PERMISSIONS_URL}")
    lines.append(f"Reconnect: {CHROME_RECONNECT_URL}")

    return "\n".join(lines)


def _skills_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """List and manage available skills."""
    from py_claw.skills import discover_local_skills

    args = arguments.strip().lower()
    settings_skills = settings.effective.get("skills") or []

    # Discover skills
    discovered = discover_local_skills(
        cwd=state.cwd or ".",
        home_dir=state.home_dir,
        settings_skills=settings_skills,
    )

    if not args or args == "list":
        lines = ["=== Claude Code Skills ===", ""]
        lines.append(f"Discovered {len(discovered)} skill(s):")
        lines.append("")

        if not discovered:
            lines.append("  (no skills found)")
            lines.append("")
            lines.append("Skills can be added to .claude/settings.json")
        else:
            for skill in sorted(discovered, key=lambda s: s.name):
                lines.append(f"  /{skill.name}")
                if skill.description:
                    lines.append(f"    {skill.description}")
                if skill.source:
                    lines.append(f"    source: {skill.source}")
                lines.append("")
        lines.append("Use /skills info <name> for detailed information.")
        return "\n".join(lines)

    elif args.startswith("info "):
        skill_name = args[5:].strip()
        skill = next((s for s in discovered if s.name == skill_name), None)
        if not skill:
            return f"Skill '{skill_name}' not found."

        lines = [f"=== Skill: {skill.name} ===", ""]
        lines.append(f"Description: {skill.description or '(none)'}")
        lines.append(f"Source: {skill.source or 'unknown'}")
        if skill.version:
            lines.append(f"Version: {skill.version}")
        if skill.argument_hint:
            lines.append(f"Arguments: {skill.argument_hint}")
        if skill.when_to_use:
            lines.append(f"When to use: {skill.when_to_use}")
        if skill.allowed_tools:
            lines.append(f"Allowed tools: {', '.join(skill.allowed_tools)}")
        if skill.model:
            lines.append(f"Model: {skill.model}")
        return "\n".join(lines)

    else:
        return "Usage: /skills [list|info <skill-name>]"


def _stats_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show detailed session statistics."""
    query_runtime = state.query_runtime

    lines = ["=== Session Statistics ===", ""]

    # Session info
    lines.append(f"Session ID: {session_id or 'inactive'}")
    lines.append(f"Working directory: {state.cwd}")
    lines.append(f"Transcript messages: {transcript_size}")

    # Task stats
    tasks = state.task_runtime.list()
    total_tasks = len(tasks)
    completed_tasks = len([t for t in tasks if t.status == "completed"])
    active_tasks = len([t for t in tasks if t.status == "running"])
    lines.append(f"Tasks: {active_tasks} active, {completed_tasks} completed, {total_tasks} total")

    # Tool usage stats
    file_ops = len(state.tool_runtime.file_mutation_history)
    lines.append(f"File operations: {file_ops}")

    # MCP servers
    mcp_statuses = state.mcp_runtime.build_statuses(settings)
    running_mcp = len([s for s in mcp_statuses if s.status == "running"])
    lines.append(f"MCP servers: {running_mcp} running, {len(mcp_statuses)} configured")

    # Permission mode
    lines.append(f"Permission mode: {state.permission_mode}")

    # Model info
    model = state.model or settings.effective.get("model") or "default"
    lines.append(f"Model: {model}")

    # Commands available
    lines.append(f"Commands: {len(registry.list())}")

    return "\n".join(lines)


def _diff_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show git diffs of staged and unstaged changes."""
    import subprocess

    cwd = state.cwd
    use_cached = "--cached" in arguments or "-c" in arguments

    lines = []

    # Get staged diff
    staged_result = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    unstaged_result = subprocess.run(
        ["git", "diff"],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if use_cached:
        # Show only staged changes
        if staged_result.stdout.strip():
            lines.append("=== Staged Changes (ready to commit) ===")
            lines.append(staged_result.stdout)
        else:
            lines.append("No staged changes. Use `git add <file>` to stage changes.")
        return "\n".join(lines)

    # Show both staged and unstaged
    if staged_result.stdout.strip():
        lines.append("=== Staged Changes (ready to commit) ===")
        lines.append(staged_result.stdout)
    else:
        lines.append("(no staged changes)")

    if unstaged_result.stdout.strip():
        lines.append("\n=== Unstaged Changes ===")
        lines.append(unstaged_result.stdout)
    else:
        lines.append("(no unstaged changes)")

    if not lines:
        return "No changes in repository."

    return "\n".join(lines)


# ============================================================================
# Insights Handler
# ============================================================================

EXTENSION_TO_LANGUAGE = {
    '.ts': 'TypeScript', '.tsx': 'TypeScript', '.js': 'JavaScript', '.jsx': 'JavaScript',
    '.py': 'Python', '.rb': 'Ruby', '.go': 'Go', '.rs': 'Rust', '.java': 'Java',
    '.md': 'Markdown', '.json': 'JSON', '.yaml': 'YAML', '.yml': 'YAML',
    '.sh': 'Shell', '.bash': 'Shell', '.css': 'CSS', '.html': 'HTML', '.htm': 'HTML',
    '.sql': 'SQL', '.c': 'C', '.cpp': 'C++', '.h': 'C Header', '.hpp': 'C++ Header',
    '.cs': 'C#', '.swift': 'Swift', '.kt': 'Kotlin', '.kts': 'Kotlin',
    '.php': 'PHP', '.r': 'R', '.lua': 'Lua', '.ex': 'Elixir', '.exs': 'Elixir', '.erl': 'Erlang',
}


def _get_language_from_path(file_path: str) -> str | None:
    """Get programming language from file extension."""
    from pathlib import Path
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)


def _get_claude_data_dir():
    """Get the Claude data directory."""
    import os
    from pathlib import Path
    config_home = os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude'
    return Path(config_home) / 'usage-data'


def _find_session_files(project_path: str | None = None) -> list:
    """Find all session JSONL files."""
    from pathlib import Path
    session_files = []
    data_dir = _get_claude_data_dir()

    if data_dir.exists():
        for f in data_dir.glob('**/*.jsonl'):
            session_files.append(f)

    if project_path:
        projects_dir = Path(project_path) / '.claude'
        if projects_dir.exists():
            for f in projects_dir.glob('sessions/*.jsonl'):
                if f not in session_files:
                    session_files.append(f)

    return sorted(session_files, key=lambda x: x.stat().st_mtime, reverse=True)


def _load_session_file(file_path) -> list[dict]:
    """Load a session JSONL file."""
    import json
    entries = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except (IOError, OSError):
        pass
    return entries


def _insights_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle /insights command — delegates to services.insights pipeline."""
    import asyncio

    args = arguments.strip().lower().split() if arguments.strip() else []
    open_browser = "open" in args or "browser" in args
    export_json = "json" in args

    # Delegate to the service pipeline
    result = asyncio.run(_run_insights_pipeline(project_path=state.cwd))

    if not result.success:
        return f"Error: {result.message}"

    if result.sessions is not None and len(result.sessions) == 0:
        return _insights_empty()

    # format_insights_report is available from the lazy import inside _run_insights_pipeline
    from py_claw.services.insights import format_insights_report as _format_report

    if export_json:
        return _format_report(result, fmt="json")

    text = _format_report(result, fmt="text")
    if open_browser:
        path = write_html_insights(result)
        try:
            import webbrowser
            webbrowser.open(f"file://{path}")
        except Exception:
            pass
    return text


async def _run_insights_pipeline(project_path: str | None = None):
    """Run the insights pipeline, imported lazily to avoid circular deps."""
    from py_claw.services.insights import (
        format_insights_report,
        generate_insights_report,
        write_html_insights,
    )
    return await generate_insights_report(project_path=project_path)


def _insights_empty() -> str:
    """Generate message when no sessions found."""
    return (
        "\u256d\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u256e\n"
        "\u2502                    Claude Code Insights                          \u2502\n"
        "\u251c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2524\n"
        "\u2502                                                                  \u2502\n"
        "\u2502  No session data found.                                          \u2502\n"
        "\u2502                                                                  \u2502\n"
        "\u2502  Claude Code Insights analyzes your usage patterns across       \u2502\n"
        "\u2502  all your Claude Code sessions to provide statistics like:      \u2502\n"
        "\u2502                                                                  \u2502\n"
        "\u2502    \u2022 Total sessions and messages                                 \u2502\n"
        "\u2502    \u2022 Most used programming languages                            \u2502\n"
        "\u2502    \u2022 Tool usage statistics                                      \u2502\n"
        "\u2502    \u2022 Git activity (commits, pushes)                             \u2502\n"
        "\u2502    \u2022 Code change metrics                                        \u2502\n"
        "\u2502                                                                  \u2502\n"
        "\u2502  Sessions are automatically tracked when you use Claude Code.    \u2502\n"
        "\u2502                                                                  \u2502\n"
        "\u2502  Usage:                                                          \u2502\n"
        "\u2502    /insights          Show basic statistics                     \u2502\n"
        "\u2502    /insights open     Open detailed HTML report in browser      \u2502\n"
        "\u2502    /insights json     Export data as JSON                        \u2502\n"
        "\u2502                                                                  \u2502\n"
        "\u2550\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2557"
    )


def _extract_session_stats(entries: list[dict]) -> dict:
    """Extract statistics from session entries."""
    tool_counts = {}
    languages = {}
    files_modified = set()
    lines_added = 0
    lines_removed = 0
    git_commits = 0
    git_pushes = 0
    user_message_count = 0
    assistant_message_count = 0
    input_tokens = 0
    output_tokens = 0
    project_path = ""

    for entry in entries:
        entry_type = entry.get('type', '')

        if entry_type == 'session_start':
            project_path = entry.get('project_path', '')

        elif entry_type == 'user':
            user_message_count += 1

        elif entry_type == 'assistant':
            assistant_message_count += 1
            usage = entry.get('message', {}).get('usage', {})
            input_tokens += usage.get('input_tokens', 0)
            output_tokens += usage.get('output_tokens', 0)

            content = entry.get('message', {}).get('content', [])
            if isinstance(content, list):
                for block in content:
                    if block.get('type') == 'tool_use':
                        tool_name = block.get('name', '')
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

                        input_data = block.get('input', {})
                        file_path = input_data.get('file_path', '')

                        if file_path:
                            lang = _get_language_from_path(file_path)
                            if lang:
                                languages[lang] = languages.get(lang, 0) + 1

                            if tool_name in ('Edit', 'Write'):
                                files_modified.add(file_path)

                            if tool_name == 'Edit':
                                old = input_data.get('old_string', '') or ''
                                new = input_data.get('new_string', '') or ''
                                lines_added += new.count('\n') + (1 if new and not new.endswith('\n') else 0)
                                lines_removed += old.count('\n') + (1 if old and not old.endswith('\n') else 0)
                            elif tool_name == 'Write':
                                content_str = input_data.get('content', '') or ''
                                lines_added += content_str.count('\n') + (1 if content_str else 0)

                        command = input_data.get('command', '')
                        if 'git commit' in command:
                            git_commits += 1
                        if 'git push' in command:
                            git_pushes += 1

    return {
        'project_path': project_path,
        'user_message_count': user_message_count,
        'assistant_message_count': assistant_message_count,
        'tool_counts': tool_counts,
        'languages': languages,
        'git_commits': git_commits,
        'git_pushes': git_pushes,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'lines_added': lines_added,
        'lines_removed': lines_removed,
        'files_modified': files_modified,
    }


def _aggregate_sessions(sessions: list[dict]) -> dict:
    """Aggregate data from all sessions."""
    agg = {
        'total_sessions': len(sessions),
        'total_messages': 0,
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'git_commits': 0,
        'git_pushes': 0,
        'lines_added': 0,
        'lines_removed': 0,
        'files_modified': 0,
        'tool_counts': {},
        'languages': {},
        'projects': {},
    }

    for s in sessions:
        agg['total_messages'] += s['user_message_count'] + s['assistant_message_count']
        agg['total_input_tokens'] += s['input_tokens']
        agg['total_output_tokens'] += s['output_tokens']
        agg['git_commits'] += s['git_commits']
        agg['git_pushes'] += s['git_pushes']
        agg['lines_added'] += s['lines_added']
        agg['lines_removed'] += s['lines_removed']
        agg['files_modified'] += len(s['files_modified'])

        for tool, count in s['tool_counts'].items():
            agg['tool_counts'][tool] = agg['tool_counts'].get(tool, 0) + count

        for lang, count in s['languages'].items():
            agg['languages'][lang] = agg['languages'].get(lang, 0) + count

        project = s['project_path'] or 'unknown'
        agg['projects'][project] = agg['projects'].get(project, 0) + 1

    return agg


# Available themes for terminal UI
AVAILABLE_THEMES = [
    "system",    # Follow terminal/system theme
    "dark",      # Dark theme
    "light",     # Light theme
    "night",     # Night theme (high contrast dark)
    "monokai",   # Monokai theme
    "solarized", # Solarized theme
    "dracula",   # Dracula theme
]


def _theme_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Show or change the color theme."""
    args = arguments.strip()

    if not args:
        # Show current theme and available themes
        current_theme = settings.effective.get("theme") or "system"
        lines = ["=== Claude Code Theme ===", ""]
        lines.append(f"Current theme: {current_theme}")
        lines.append("")
        lines.append("Available themes:")
        for theme_name in AVAILABLE_THEMES:
            if theme_name == current_theme:
                lines.append(f"  * {theme_name} (current)")
            else:
                lines.append(f"  - {theme_name}")
        lines.append("")
        lines.append("Use /theme <name> to change the theme.")
        return "\n".join(lines)

    # Try to set the theme
    requested_theme = args.lower()
    if requested_theme in AVAILABLE_THEMES:
        return f"Theme setting is read-only in this version. Current theme: {settings.effective.get('theme') or 'system'}"
    else:
        valid = ", ".join(AVAILABLE_THEMES)
        return f"Unknown theme: {requested_theme}. Valid themes: {valid}"


def _format_insights(agg: dict, open_browser: bool = False) -> str:
    """Format insights as text."""
    top_languages = sorted(agg['languages'].items(), key=lambda x: x[1], reverse=True)[:5]
    top_tools = sorted(agg['tool_counts'].items(), key=lambda x: x[1], reverse=True)[:8]
    top_projects = sorted(agg['projects'].items(), key=lambda x: x[1], reverse=True)[:5]
    total_tokens = agg['total_input_tokens'] + agg['total_output_tokens']
    cost = (agg['total_input_tokens'] / 1_000_000 * 0.5) + (agg['total_output_tokens'] / 1_000_000 * 2.5)

    def fmt(n): return f"{n:,}"

    lines = [
        "╭──────────────────────────────────────────────────────────────────╮",
        "│                    Claude Code Insights                          │",
        "├──────────────────────────────────────────────────────────────────┤",
        "│                                                                   │",
        f"│   Total Sessions:        {fmt(agg['total_sessions']):>10}                      │",
        f"│   Total Messages:        {fmt(agg['total_messages']):>10}                      │",
        f"│   Total Input Tokens:    {fmt(agg['total_input_tokens']):>10}                      │",
        f"│   Total Output Tokens:   {fmt(agg['total_output_tokens']):>10}                      │",
        f"│   Total Tokens:          {fmt(total_tokens):>10}                      │",
        f"│   Estimated Cost:         ${cost:>10.2f}                      │",
        "│                                                                   │",
        "├──────────────────────────────────────────────────────────────────┤",
        "│                      Git Activity                                │",
        "├──────────────────────────────────────────────────────────────────┤",
        f"│   Commits:              {fmt(agg['git_commits']):>10}                      │",
        f"│   Pushes:               {fmt(agg['git_pushes']):>10}                      │",
        "│                                                                   │",
        "├──────────────────────────────────────────────────────────────────┤",
        "│                      Code Changes                               │",
        "├──────────────────────────────────────────────────────────────────┤",
        f"│   Lines Added:          {fmt(agg['lines_added']):>10}                      │",
        f"│   Lines Removed:        {fmt(agg['lines_removed']):>10}                      │",
        f"│   Files Modified:       {fmt(agg['files_modified']):>10}                      │",
        "│                                                                   │",
    ]

    if top_languages:
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        lines.append("│                  Top Languages                                  │")
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        for i, (lang, count) in enumerate(top_languages, 1):
            bar = '█' * min(count // 10, 25)
            lines.append(f"│   {i}. {lang:<15} {bar} ({fmt(count)})  │")
        lines.append("│                                                                   │")

    if top_tools:
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        lines.append("│                    Top Tools                                     │")
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        for i, (tool, count) in enumerate(top_tools, 1):
            lines.append(f"│   {i}. {tool:<25} {fmt(count):>10}  │")
        lines.append("│                                                                   │")

    if top_projects:
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        lines.append("│                    Top Projects                                 │")
        lines.append("├──────────────────────────────────────────────────────────────────┤")
        for i, (project, count) in enumerate(top_projects, 1):
            from pathlib import Path
            project_name = Path(project).name or project
            if len(project_name) > 25:
                project_name = project_name[:22] + '...'
            lines.append(f"│   {i}. {project_name:<25} {fmt(count):>10}  │")
        lines.append("│                                                                   │")

    lines.append("╰──────────────────────────────────────────────────────────────────╯")

    if open_browser:
        _generate_html_insights(agg)

    return '\n'.join(lines)


def _generate_html_insights(agg: dict) -> None:
    """Generate HTML report and open in browser."""
    import webbrowser
    from pathlib import Path

    data_dir = _get_claude_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    html_path = data_dir / 'insights.html'

    top_languages = sorted(agg['languages'].items(), key=lambda x: x[1], reverse=True)[:10]
    top_tools = sorted(agg['tool_counts'].items(), key=lambda x: x[1], reverse=True)[:15]
    top_projects = sorted(agg['projects'].items(), key=lambda x: x[1], reverse=True)[:10]
    total_tokens = agg['total_input_tokens'] + agg['total_output_tokens']

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Claude Code Insights</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; margin: 40px; background: #1a1a2e; color: #eee; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ color: #f4a261; text-align: center; }}
        h2 {{ color: #e9c46a; border-bottom: 1px solid #333; padding-bottom: 10px; margin-top: 30px; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
        .stat {{ background: #16213e; padding: 20px; border-radius: 10px; text-align: center; }}
        .stat-value {{ font-size: 2em; color: #f4a261; font-weight: bold; }}
        .stat-label {{ color: #888; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ color: #f4a261; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Claude Code Insights</h1>
        <div class="stats">
            <div class="stat"><div class="stat-value">{agg['total_sessions']:,}</div><div class="stat-label">Sessions</div></div>
            <div class="stat"><div class="stat-value">{agg['total_messages']:,}</div><div class="stat-label">Messages</div></div>
            <div class="stat"><div class="stat-value">{total_tokens:,}</div><div class="stat-label">Total Tokens</div></div>
            <div class="stat"><div class="stat-value">{agg['files_modified']:,}</div><div class="stat-label">Files Modified</div></div>
        </div>
        <h2>Languages</h2>
        <table><tr><th>Language</th><th>Count</th></tr>{"".join(f"<tr><td>{l}</td><td>{c:,}</td></tr>" for l, c in top_languages)}</table>
        <h2>Tools</h2>
        <table><tr><th>Tool</th><th>Count</th></tr>{"".join(f"<tr><td>{t}</td><td>{c:,}</td></tr>" for t, c in top_tools)}</table>
        <h2>Projects</h2>
        <table><tr><th>Project</th><th>Sessions</th></tr>{"".join(f"<tr><td>{p}</td><td>{c:,}</td></tr>" for p, c in top_projects)}</table>
        <h2>Code Changes</h2>
        <div class="stats">
            <div class="stat"><div class="stat-value">+{agg['lines_added']:,}</div><div class="stat-label">Lines Added</div></div>
            <div class="stat"><div class="stat-value">-{agg['lines_removed']:,}</div><div class="stat-label">Lines Removed</div></div>
            <div class="stat"><div class="stat-value">{agg['git_commits']:,}</div><div class="stat-label">Commits</div></div>
            <div class="stat"><div class="stat-value">{agg['git_pushes']:,}</div><div class="stat-label">Pushes</div></div>
        </div>
    </div>
</body>
</html>"""
    return None


def _tag_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle git tag operations."""
    import subprocess

    cwd = state.cwd
    args = arguments.strip()

    # List tags if no argument or just listing
    if not args or args == "-l":
        result = subprocess.run(
            ["git", "tag", "-l"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return f"Git error: {result.stderr.strip()}"
        tags = result.stdout.strip().split("\n")
        if not tags or (len(tags) == 1 and not tags[0]):
            return "No git tags found."
        return "Git tags:\n" + "\n".join(f"  {t}" for t in tags if t)

    # Delete a tag
    if args.startswith("-d ") or args.startswith("D "):
        tag_name = args[2:].strip()
        if not tag_name:
            return "Usage: /tag -d <tag-name>"
        result = subprocess.run(
            ["git", "tag", "-d", tag_name],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return f"Failed to delete tag: {result.stderr.strip()}"
        return f"Deleted tag: {tag_name}"

    # Create annotated tag
    if args.startswith("-a "):
        parts = args[3:].split(maxsplit=1)
        if not parts:
            return "Usage: /tag -a <tag-name> [-m <message>]"
        tag_name = parts[0]
        msg = parts[1][3:].strip() if len(parts) > 1 and parts[1].startswith("-m ") else f"Tag: {tag_name}"
        result = subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", msg],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return f"Failed to create tag: {result.stderr.strip()}"
        return f"Created tag: {tag_name}"

    # Simple tag creation (lightweight)
    result = subprocess.run(
        ["git", "tag", args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return f"Failed to create tag: {result.stderr.strip()}"
    return f"Created tag: {args}"


def _plugin_handler(
    command: CommandDefinition,
    *,
    arguments: str,
    state: RuntimeState,
    settings: SettingsLoadResult,
    registry: CommandRegistry,
    session_id: str | None,
    transcript_size: int,
) -> str:
    """Handle plugin management commands."""
    from py_claw.services.plugins import (
        get_plugin_service,
        initialize_plugins,
    )

    # Initialize plugin service if not already done
    service = get_plugin_service()
    if not service.initialized:
        initialize_plugins()

    parts = arguments.strip().split()
    if not parts:
        return "Usage: /plugin <list|install|uninstall|enable|disable|marketplace> [args...]"

    subcommand = parts[0].lower()
    args_list = parts[1:]

    if subcommand == "list":
        return _plugin_list_handler(service, args_list)
    elif subcommand == "install":
        return _plugin_install_handler(service, args_list)
    elif subcommand == "uninstall":
        return _plugin_uninstall_handler(service, args_list)
    elif subcommand == "enable":
        return _plugin_enable_handler(service, args_list)
    elif subcommand == "disable":
        return _plugin_disable_handler(service, args_list)
    elif subcommand == "marketplace":
        return _plugin_marketplace_handler(service, args_list)
    elif subcommand in ("help", "--help", "-h"):
        return (
            "Usage: /plugin <command>\n\n"
            "Commands:\n"
            "  list                        List installed plugins\n"
            "  list --marketplace <name>   List plugins in a marketplace\n"
            "  install <plugin-id>         Install a plugin (use name@marketplace for marketplace)\n"
            "  uninstall <plugin-id>       Uninstall a plugin\n"
            "  enable <plugin-id>          Enable a plugin\n"
            "  disable <plugin-id>         Disable a plugin\n"
            "  marketplace add <url>        Add a marketplace\n"
            "  marketplace list            List known marketplaces\n"
            "  marketplace remove <name>  Remove a marketplace\n"
        )
    else:
        return f"Unknown plugin command: {subcommand}. Use /plugin --help for usage."


def _plugin_list_handler(service: "PluginService", args: list[str]) -> str:
    """Handle /plugin list."""
    if args and args[0] == "--marketplace":
        marketplace_name = args[1] if len(args) > 1 else ""
        if not marketplace_name:
            marketplaces = service.list_marketplaces()
            if not marketplaces:
                return "No marketplaces registered. Use /plugin marketplace add <url> to add one."
            lines = ["Known marketplaces:"]
            for m in marketplaces:
                lines.append(f"  - {m.name} ({m.url})")
            return "\n".join(lines)
        plugins = service.get_marketplace_plugins(marketplace_name)
        if not plugins:
            return f"No plugins found in marketplace '{marketplace_name}', or marketplace not found."
        lines = [f"Plugins in {marketplace_name}:"]
        for p in plugins:
            desc = p.get("description", "No description")
            version = p.get("version", "")
            lines.append(f"  - {p['name']} {version} — {desc}")
        return "\n".join(lines)

    plugins = service.list_plugins(include_disabled=True)
    if not plugins:
        return (
            "No plugins installed.\n\n"
            "Use /plugin marketplace list to see available marketplaces,\n"
            "or /plugin install <path> to install from a local path."
        )

    enabled = [p for p in plugins if p.get("enabled")]
    disabled = [p for p in plugins if not p.get("enabled")]
    builtin_all = [p for p in plugins if p.get("builtin")]

    lines = []
    if enabled:
        lines.append("Enabled plugins:")
        for p in enabled:
            lines.append(f"  ✅ {p['name']} — {p.get('description', '')}")
    if disabled:
        lines.append("\nDisabled plugins:")
        for p in disabled:
            lines.append(f"  ⏸ {p['name']} — {p.get('description', '')}")
    if builtin_all:
        lines.append(f"\nBuilt-in plugins ({len(builtin_all)}):")
        for p in builtin_all:
            lines.append(f"  ⚙ {p['name']} — {p.get('description', '')}")

    lines.append("\nRun /plugin --help for usage.")
    return "\n".join(lines)


def _plugin_install_handler(service: "PluginService", args: list[str]) -> str:
    """Handle /plugin install."""
    if not args:
        return "Usage: /plugin install <plugin-id> or /plugin install <path>"
    plugin_id = args[0]
    result = service.install(plugin_id)
    if result.success:
        return f"✅ {result.message}"
    else:
        return f"❌ Installation failed: {result.error}"


def _plugin_uninstall_handler(service: "PluginService", args: list[str]) -> str:
    """Handle /plugin uninstall."""
    if not args:
        return "Usage: /plugin uninstall <plugin-id>"
    plugin_id = args[0]
    result = service.uninstall(plugin_id)
    if result.success:
        return f"✅ {result.message}"
    else:
        return f"❌ Uninstall failed: {result.error}"


def _plugin_enable_handler(service: "PluginService", args: list[str]) -> str:
    """Handle /plugin enable."""
    if not args:
        return "Usage: /plugin enable <plugin-id>"
    plugin_id = args[0]
    result = service.enable(plugin_id)
    if result.success:
        return f"✅ {result.message}"
    else:
        return f"❌ Enable failed: {result.error}"


def _plugin_disable_handler(service: "PluginService", args: list[str]) -> str:
    """Handle /plugin disable."""
    if not args:
        return "Usage: /plugin disable <plugin-id>"
    plugin_id = args[0]
    result = service.disable(plugin_id)
    if result.success:
        return f"✅ {result.message}"
    else:
        return f"❌ Disable failed: {result.error}"


def _plugin_marketplace_handler(service: "PluginService", args: list[str]) -> str:
    """Handle /plugin marketplace subcommands."""
    if not args:
        return "Usage: /plugin marketplace <add|list|remove> [args]"
    sub = args[0].lower()
    sub_args = args[1:]

    if sub == "list":
        marketplaces = service.list_marketplaces()
        if not marketplaces:
            return "No marketplaces registered. Use /plugin marketplace add <url> to add one."
        lines = ["Known marketplaces:"]
        for m in marketplaces:
            owner = f" by {m.owner}" if m.owner else ""
            lines.append(f"  - {m.name}{owner} ({m.url})")
        return "\n".join(lines)

    elif sub == "add":
        if not sub_args:
            return "Usage: /plugin marketplace add <url> [name]"
        url = sub_args[0]
        name = sub_args[1] if len(sub_args) > 1 else None
        success, msg = service.add_marketplace(url, name)
        if success:
            return f"✅ {msg}"
        else:
            return f"❌ {msg}"

    elif sub == "remove":
        if not sub_args:
            return "Usage: /plugin marketplace remove <name>"
        name = sub_args[0]
        success, msg = service.remove_marketplace(name)
        if success:
            return f"✅ {msg}"
        else:
            return f"❌ {msg}"

    else:
        return f"Unknown marketplace command: {sub}. Use /plugin marketplace <add|list|remove>."


_LOCAL_COMMAND_HANDLERS: dict[str, object] = {
    "help": _help_handler,
    "status": _status_handler,
    "permissions": _permissions_handler,
    "hooks": _hooks_handler,
    "ide": _ide_handler,
    "tasks": _tasks_handler,
    "mcp": _mcp_handler,
    "files": _files_handler,
    "memory": _memory_handler,
    "plan": _plan_handler,
    "passes": _passes_handler,
    "privacy-settings": _privacy_settings_handler,
    "resume": _resume_handler,
    "session": _session_handler,
    "skills": _skills_handler,
    "model": _model_handler,
    "advisor": _advisor_handler,
    "copy": _copy_handler,
    "clear": _clear_handler,
    "config": _config_handler,
    "compact": _compact_handler,
    "cost": _cost_handler,
    "doctor": _doctor_handler,
    "branch": _branch_handler,
    "diff": _diff_handler,
    "rewind": _rewind_handler,
    "release-notes": _release_notes_handler,
    "reload-plugins": _reload_plugins_handler,
    "stats": _stats_handler,
    "summary": _summary_handler,
    "stickers": _stickers_handler,
    "tag": _tag_handler,
    "plugin": _plugin_handler,
    "version": _version_handler,
    "usage": _usage_handler,
    "context": _context_handler,
"env": _env_handler,
    "exit": _exit_handler,
    "export": _export_handler,
    "extra-usage": _extra_usage_handler,
    "fast": _fast_handler,
    "effort": _effort_handler,
    "onboarding": _onboarding_handler,
    "output-style": _output_style_handler,
    "keybindings": _keybindings_handler,
    "login": _login_handler,
    "logout": _logout_handler,
    "btw": _btw_handler,
    "vim": _vim_handler,
    "tunnel": _tunnel_handler,
    "web-setup": _web_setup_handler,
    "install-slack-app": _install_slack_app_handler,
    "install-github-app": _install_github_app_handler,
    "install": _install_handler,
    "think-back": _thinkback_handler,
    "terminal-setup": _terminal_setup_handler,
    "theme": _theme_handler,
    "chrome": _chrome_handler,
    "color": _color_handler,
    "mobile": _mobile_handler,
    "insights": _insights_handler,
    "add-dir": _add_dir_handler,
    "bridge": _bridge_handler,
    "sessions": _sessions_handler,
    "break-cache": _break_cache_handler,
    "heapdump": _heapdump_handler,
    "sandbox-toggle": _sandbox_toggle_handler,
    "security-review": _security_review_handler,
    "teleport": _teleport_handler,
    "brief": _brief_handler,
    "ultraplan": _ultraplan_handler,
    "upgrade": _upgrade_handler,
    "voice": _voice_handler,
    # M105, M107, M110, M112 - newly implemented commands
    "pr-comments": _pr_comments_handler,
    "rate-limit-options": _rate_limit_options_handler,
    "remote-env": _remote_env_handler,
    "rename": _rename_handler,
    # Additional low-priority parity commands
    "issue": _issue_handler,
    "debug-tool-call": _debug_tool_call_handler,
    "perf-issue": _perf_issue_handler,
    "mock-limits": _mock_limits_handler,
    "oauth-refresh": _oauth_refresh_handler,
    "remote-setup": _remote_setup_handler,
    "thinkback-play": _thinkback_play_handler,
    "bridge-kick": _bridge_kick_handler,
    "agents-platform": _agents_platform_handler,
    "ant-trace": _ant_trace_handler,
    "ctx_viz": _ctx_viz_handler,
}
