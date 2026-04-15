"""
Bundled skills initialization.

Loads and registers all bundled skills that ship with py-claw.

Reference: ClaudeCode-main/src/skills/bundled/index.ts
"""
from __future__ import annotations

import os
from pathlib import Path

from py_claw.services.skills.bundled_skills import (
    BundledSkillDefinition,
    register_bundled_skill,
)


def _load_skill_content(skill_name: str, filename: str = "SKILL.md") -> str:
    """Load skill content from bundled skill directory."""
    skill_dir = Path(__file__).parent / skill_name
    skill_file = skill_dir / filename
    if skill_file.exists():
        return skill_file.read_text(encoding="utf-8")
    return ""


def init_bundled_skills() -> None:
    """
    Initialize all bundled skills.

    Called at startup to register skills that ship with py-claw.
    """
    # Keybindings skill
    keybindings_content = _load_skill_content("keybindings")
    if keybindings_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="keybindings-help",
                description=(
                    "Use when the user wants to customize keyboard shortcuts, "
                    "rebind keys, add chord bindings, or modify ~/.claude/keybindings.json. "
                    "Examples: 'rebind ctrl+s', 'add a chord shortcut', "
                    "'change the submit key', 'customize keybindings'."
                ),
                content=keybindings_content,
                source="bundled",
                allowed_tools=["Read", "Edit", "Write"],
                user_invocable=False,
            )
        )

    # Loop skill
    loop_content = _load_skill_content("loop")
    if loop_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="loop",
                description=(
                    "Run a prompt or slash command on a recurring interval. "
                    "Examples: '/loop 5m /babysit-prs', 'check the deploy every 20m', "
                    "'/loop 1h /standup 1'."
                ),
                content=loop_content,
                source="bundled",
                allowed_tools=["CronCreate", "CronDelete", "CronList"],
                user_invocable=True,
            )
        )

    # Simplify skill
    simplify_content = _load_skill_content("simplify")
    if simplify_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="simplify",
                description=(
                    "Review changed code for reuse, quality, and efficiency, then fix any issues found. "
                    "Launches 3 parallel review agents (reuse, quality, efficiency)."
                ),
                content=simplify_content,
                source="bundled",
                allowed_tools=["Agent"],
                user_invocable=True,
            )
        )

    # Skillify skill
    skillify_content = _load_skill_content("skillify")
    if skillify_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="skillify",
                description=(
                    "Convert a session's repeatable process into a reusable skill. "
                    "Interviews user to capture workflow details."
                ),
                content=skillify_content,
                source="bundled",
                allowed_tools=["AskUserQuestion", "Write", "Read"],
                user_invocable=True,
            )
        )

    # Update-config skill
    update_config_content = _load_skill_content("update-config")
    if update_config_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="update-config",
                description=(
                    "Configure Claude Code via settings.json. Use for permissions, hooks, env vars, "
                    "MCP servers, and plugins. Examples: 'allow npm commands', 'add hook to run tests', "
                    "'set DEBUG=true'."
                ),
                content=update_config_content,
                source="bundled",
                allowed_tools=["Read", "Edit", "Write"],
                user_invocable=True,
            )
        )

    # Batch skill
    batch_content = _load_skill_content("batch")
    if batch_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="batch",
                description=(
                    "Research and plan a large-scale change, then execute it in parallel across "
                    "5-30 isolated worktree agents that each open a PR. "
                    "Examples: '/batch migrate react to vue', '/batch replace lodash with native'."
                ),
                content=batch_content,
                source="bundled",
                allowed_tools=["Agent", "EnterPlanMode", "ExitPlanMode", "Bash"],
                user_invocable=True,
            )
        )

    # Debug skill
    debug_content = _load_skill_content("debug")
    if debug_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="debug",
                description=(
                    "Debug your current Claude Code session by reading the debug log. "
                    "Includes error/warning analysis and troubleshooting guidance."
                ),
                content=debug_content,
                source="bundled",
                allowed_tools=["Read", "Grep", "Glob"],
                user_invocable=True,
            )
        )

    # Remember skill
    remember_content = _load_skill_content("remember")
    if remember_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="remember",
                description=(
                    "Review auto-memory entries and propose promotions to CLAUDE.md or CLAUDE.local.md. "
                    "Detects outdated, conflicting, and duplicate entries across memory layers."
                ),
                content=remember_content,
                source="bundled",
                allowed_tools=["Read", "Edit", "Write"],
                user_invocable=True,
            )
        )

    # Stuck skill
    stuck_content = _load_skill_content("stuck")
    if stuck_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="stuck",
                description=(
                    "Investigate frozen/stuck/slow Claude Code sessions on this machine. "
                    "Diagnose CPU, memory, and process state issues."
                ),
                content=stuck_content,
                source="bundled",
                allowed_tools=["Bash", "Read"],
                user_invocable=True,
            )
        )

    # Verify skill
    verify_content = _load_skill_content("verify")
    if verify_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="verify",
                description=(
                    "Verify a code change does what it should by running tests and checking behavior. "
                    "Use after implementing a change to confirm it works correctly."
                ),
                content=verify_content,
                source="bundled",
                allowed_tools=["Bash", "Read"],
                user_invocable=True,
            )
        )

    # Schedule Remote Agents skill
    schedule_content = _load_skill_content("scheduleRemoteAgents")
    if schedule_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="schedule",
                description=(
                    "Create, update, list, or run scheduled remote agents (triggers) that execute on a cron schedule. "
                    "Use when the user wants to schedule recurring tasks, set up automated workflows, or manage scheduled agents."
                ),
                content=schedule_content,
                source="bundled",
                allowed_tools=["RemoteTrigger", "AskUserQuestion"],
                user_invocable=True,
            )
        )

    # Lorem Ipsum skill
    lorem_content = _load_skill_content("loremIpsum")
    if lorem_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="lorem-ipsum",
                description=(
                    "Generate placeholder/filler text for testing long context handling, token counting, and context window limits. "
                    "Specify token count as argument (e.g., /lorem-ipsum 50000)."
                ),
                content=lorem_content,
                source="bundled",
                allowed_tools=["Read", "Write"],
                user_invocable=True,
            )
        )

    # Dream skill (KAIROS feature)
    dream_content = _load_skill_content("dream")
    if dream_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="dream",
                description=(
                    "Explore and visualize code architecture, patterns, and designs through creative analysis. "
                    "Use when exploring alternative approaches, imagining innovative solutions, or seeing code from a different perspective."
                ),
                content=dream_content,
                source="bundled",
                allowed_tools=["Read", "Glob", "Grep"],
                user_invocable=True,
            )
        )

    # Hunter skill (REVIEW_ARTIFACT feature)
    hunter_content = _load_skill_content("hunter")
    if hunter_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="hunter",
                description=(
                    "Track down bugs, code smells, and quality issues through systematic investigation. "
                    "Use when hunting for defects, performing code review, or looking for improvement opportunities."
                ),
                content=hunter_content,
                source="bundled",
                allowed_tools=["Read", "Grep", "Glob", "Agent"],
                user_invocable=True,
            )
        )

    # Skill Generator skill
    run_skill_gen_content = _load_skill_content("runSkillGenerator")
    if run_skill_gen_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="make-skill",
                description=(
                    "Create a new custom skill by interviewing the user about their workflow. "
                    "Use when user wants to create a skill, automate a repeatable process, or build a new slash command."
                ),
                content=run_skill_gen_content,
                source="bundled",
                allowed_tools=["AskUserQuestion", "Write", "Read"],
                user_invocable=True,
            )
        )

    # Claude API skill
    claude_api_content = _load_skill_content("claudeApi")
    if claude_api_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="claude-api",
                description=(
                    "API reference documentation for Claude Code SDKs. "
                    "Use when building applications with Claude, choosing models, or understanding API options."
                ),
                content=claude_api_content,
                source="bundled",
                allowed_tools=["Read"],
                user_invocable=True,
            )
        )

    # Claude API (camelCase alias)
    if claude_api_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="claudeApi",
                description=(
                    "API reference documentation for Claude Code SDKs. "
                    "Use when building applications with Claude, choosing models, or understanding API options."
                ),
                content=claude_api_content,
                source="bundled",
                allowed_tools=["Read"],
                user_invocable=True,
            )
        )

    # Claude API multi-language skill
    claude_api_multi_content = _load_skill_content("claude-api")
    if claude_api_multi_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="claudeApi-multi",
                description=(
                    "Multi-language API reference for Claude Code. "
                    "Auto-detects project language and provides relevant examples."
                ),
                content=claude_api_multi_content,
                source="bundled",
                allowed_tools=["Read"],
                user_invocable=True,
            )
        )

    # Claude in Chrome skill
    claude_in_chrome_content = _load_skill_content("claudeInChrome")
    if claude_in_chrome_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="claude-in-chrome",
                description=(
                    "Set up and troubleshoot the Claude in Chrome browser extension. "
                    "Use when the user wants to use Claude in Chrome or has extension issues."
                ),
                content=claude_in_chrome_content,
                source="bundled",
                allowed_tools=["Read"],
                user_invocable=True,
            )
        )

    # Claude in Chrome (camelCase alias)
    if claude_in_chrome_content:
        register_bundled_skill(
            BundledSkillDefinition(
                name="claudeInChrome",
                description=(
                    "Set up and troubleshoot the Claude in Chrome browser extension. "
                    "Use when the user wants to use Claude in Chrome or has extension issues."
                ),
                content=claude_in_chrome_content,
                source="bundled",
                allowed_tools=["Read"],
                user_invocable=True,
            )
        )
