"""Init-verifiers command for py-claw.

Helps users create verifier skills for automated code verification.
Based on ClaudeCode-main/src/commands/init-verifiers.ts
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from py_claw.schemas.common import EffortLevel


@dataclass
class VerifierType:
    """Type of verifier."""

    id: str
    name: str
    description: str
    allowed_tools: list[str]


# Verifier types
VERIFIER_TYPES = {
    "playwright": VerifierType(
        id="playwright",
        name="Playwright",
        description="Web UI verification using Playwright",
        allowed_tools=[
            "Bash(npm:*)",
            "Bash(yarn:*)",
            "Bash(pnpm:*)",
            "Bash(bun:*)",
            "mcp__playwright__*",
            "Read",
            "Glob",
            "Grep",
        ],
    ),
    "cli": VerifierType(
        id="cli",
        name="CLI/Terminal",
        description="CLI tool verification using Tmux",
        allowed_tools=[
            "Bash",
            "Tmux",
            "Bash(asciinema:*)",
            "Read",
            "Glob",
            "Grep",
        ],
    ),
    "api": VerifierType(
        id="api",
        name="HTTP API",
        description="API verification using curl/httpie",
        allowed_tools=[
            "Bash(curl:*)",
            "Bash(http:*)",
            "Bash(npm:*)",
            "Bash(yarn:*)",
            "Read",
            "Glob",
            "Grep",
        ],
    ),
}


def detect_project_type(cwd: str) -> dict[str, Any]:
    """Detect the project type and stack.

    Args:
        cwd: Current working directory

    Returns:
        Dictionary with detected project information
    """
    result: dict[str, Any] = {
        "type": None,
        "languages": [],
        "package_managers": [],
        "frameworks": [],
        "has_playwright": False,
        "has_dev_server": False,
        "dev_server_command": None,
        "dev_server_url": None,
    }

    # Check for package.json
    pkg_json = Path(cwd) / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            result["type"] = "node"
            if "dependencies" in data or "devDependencies" in data:
                all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                result["languages"].append("JavaScript/TypeScript")

                # Detect package manager
                if "packageManager" in data:
                    result["package_managers"].append(data["packageManager"].split("@")[0])
                elif Path(cwd, "yarn.lock").exists():
                    result["package_managers"].append("yarn")
                elif Path(cwd, "pnpm-lock.yaml").exists():
                    result["package_managers"].append("pnpm")
                elif Path(cwd, "package-lock.json").exists():
                    result["package_managers"].append("npm")

                # Detect frameworks
                deps = list(all_deps.keys())
                if any("react" in d.lower() for d in deps):
                    result["frameworks"].append("React")
                if any("next" in d.lower() for d in deps):
                    result["frameworks"].append("Next.js")
                if any("vue" in d.lower() for d in deps):
                    result["frameworks"].append("Vue")
                if any("nuxt" in d.lower() for d in deps):
                    result["frameworks"].append("Nuxt")
                if any("express" in d.lower() for d in deps):
                    result["frameworks"].append("Express")
                if any("fastapi" in d.lower() for d in deps):
                    result["frameworks"].append("FastAPI")
                if any("django" in d.lower() for d in deps):
                    result["frameworks"].append("Django")
                if any("flask" in d.lower() for d in deps):
                    result["frameworks"].append("Flask")

                # Check for Playwright
                if any("playwright" in d.lower() for d in deps):
                    result["has_playwright"] = True

                # Check for dev server scripts
                scripts = data.get("scripts", {})
                dev_scripts = ["dev", "start", "develop"]
                for script in dev_scripts:
                    if script in scripts:
                        result["has_dev_server"] = True
                        result["dev_server_command"] = f"npm run {script}"
                        break
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    # Check for pyproject.toml (Python)
    pyproject = Path(cwd) / "pyproject.toml"
    if pyproject.exists():
        result["type"] = "python"
        if "python" not in result["languages"]:
            result["languages"].append("Python")

    # Check for Cargo.toml (Rust)
    cargo = Path(cwd) / "Cargo.toml"
    if cargo.exists():
        result["type"] = "rust"
        if "rust" not in result["languages"]:
            result["languages"].append("Rust")

    # Check for go.mod (Go)
    gomod = Path(cwd) / "go.mod"
    if gomod.exists():
        result["type"] = "go"
        if "go" not in result["languages"]:
            result["languages"].append("Go")

    return result


def create_verifier_skill(
    verifier_type: str,
    name: str,
    project_context: dict[str, Any],
    options: dict[str, Any],
) -> tuple[str, str]:
    """Create a verifier skill file.

    Args:
        verifier_type: Type of verifier (playwright, cli, api)
        name: Name of the verifier skill
        project_context: Detected project information
        options: Additional options for the verifier

    Returns:
        Tuple of (skill_content, skill_path)
    """
    verifier = VERIFIER_TYPES.get(verifier_type, VERIFIER_TYPES["cli"])
    skills_dir = Path(options.get("skills_dir", ".claude/skills"))
    skill_dir = skills_dir / name
    skill_file = skill_dir / "SKILL.md"

    # Build allowed tools list
    allowed_tools = verifier.allowed_tools.copy()

    # Build skill content based on verifier type
    if verifier_type == "playwright":
        content = _build_playwright_verifier(name, project_context, options)
    elif verifier_type == "api":
        content = _build_api_verifier(name, project_context, options)
    else:
        content = _build_cli_verifier(name, project_context, options)

    return content, str(skill_file)


def _build_playwright_verifier(
    name: str,
    project_context: dict[str, Any],
    options: dict[str, Any],
) -> str:
    """Build a Playwright-based verifier skill."""
    dev_server = project_context.get("dev_server_command", "npm run dev")
    dev_server_url = options.get("dev_server_url", "http://localhost:3000")

    return f"""---
name: {name}
description: Automated web UI verification using Playwright
allowed-tools:
{_format_allowed_tools(VERIFIER_TYPES["playwright"].allowed_tools)}
---

# {name.replace("-", " ").title()}

You are a verification executor. You receive a verification plan and execute it EXACTLY as written.

## Project Context

- **Type**: {", ".join(project_context.get("frameworks", ["Unknown"]))}
- **Package Manager**: {", ".join(project_context.get("package_managers", ["npm"]))}
- **Dev Server**: {dev_server}

## Setup Instructions

1. Start the dev server: `{dev_server}`
2. Wait for the server to be ready at {dev_server_url}
3. Install Playwright if not already installed:
   - `npm install -D @playwright/test`
   - `npx playwright install`

## Verification Steps

1. Navigate to the specified URL
2. Perform the verification actions described in the plan
3. Take screenshots if required
4. Verify expected outcomes

## Reporting

Report PASS or FAIL for each step using the format specified in the verification plan.

## Cleanup

After verification:
1. Stop any dev servers started
2. Close any browser sessions
3. Report final summary

## Self-Update

If verification fails because this skill's instructions are outdated (dev server command/port/ready-signal changed, etc.) — not because the feature under test is broken — use AskUserQuestion to confirm and then Edit this SKILL.md with a minimal targeted fix.
"""


def _build_api_verifier(
    name: str,
    project_context: dict[str, Any],
    options: dict[str, Any],
) -> str:
    """Build an HTTP API verifier skill."""
    base_url = options.get("base_url", "http://localhost:8000")
    api_server = project_context.get("dev_server_command", "python -m uvicorn main:app --reload")

    return f"""---
name: {name}
description: Automated HTTP API verification
allowed-tools:
{_format_allowed_tools(VERIFIER_TYPES["api"].allowed_tools)}
---

# {name.replace("-", " ").title()}

You are a verification executor. You receive a verification plan and execute it EXACTLY as written.

## Project Context

- **Type**: {", ".join(project_context.get("frameworks", ["Unknown"]))}
- **Language**: {", ".join(project_context.get("languages", ["Python"]))}

## Setup Instructions

1. Start the API server: `{api_server}`
2. Wait for the server to be ready at {base_url}

## Verification Steps

1. Send HTTP requests as specified in the verification plan
2. Verify response status codes and body content
3. Check for expected data in responses

## Reporting

Report PASS or FAIL for each step using the format specified in the verification plan.

## Cleanup

After verification:
1. Stop any servers started
2. Report final summary

## Self-Update

If verification fails because this skill's instructions are outdated (API endpoint/port changed, etc.) — not because the feature under test is broken — use AskUserQuestion to confirm and then Edit this SKILL.md with a minimal targeted fix.
"""


def _build_cli_verifier(
    name: str,
    project_context: dict[str, Any],
    options: dict[str, Any],
) -> str:
    """Build a CLI/Terminal verifier skill."""
    entry_point = options.get("entry_point", "./main")

    return f"""---
name: {name}
description: Automated CLI tool verification
allowed-tools:
{_format_allowed_tools(VERIFIER_TYPES["cli"].allowed_tools)}
---

# {name.replace("-", " ").title()}

You are a verification executor. You receive a verification plan and execute it EXACTLY as written.

## Project Context

- **Type**: CLI Tool
- **Language**: {", ".join(project_context.get("languages", ["Unknown"]))}

## Setup Instructions

1. Build the project if needed
2. Verify the entry point exists at `{entry_point}`

## Verification Steps

1. Execute CLI commands as specified in the verification plan
2. Capture output
3. Verify expected results

## Reporting

Report PASS or FAIL for each step using the format specified in the verification plan.

## Cleanup

After verification:
1. Close any Tmux sessions
2. Report final summary

## Self-Update

If verification fails because this skill's instructions are outdated (command/path changed, etc.) — not because the feature under test is broken — use AskUserQuestion to confirm and then Edit this SKILL.md with a minimal targeted fix.
"""


def _format_allowed_tools(tools: list[str]) -> str:
    """Format allowed tools list for YAML."""
    return "\n".join(f"  - {tool}" for tool in tools)


def run_init_verifiers(cwd: str) -> dict[str, Any]:
    """Run the init-verifiers command.

    Args:
        cwd: Current working directory

    Returns:
        Dictionary with results
    """
    # Detect project type
    project_context = detect_project_type(cwd)

    skills_dir = Path(cwd) / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    return {
        "success": True,
        "project_context": project_context,
        "skills_dir": str(skills_dir),
        "available_verifier_types": {
            k: {"name": v.name, "description": v.description}
            for k, v in VERIFIER_TYPES.items()
        },
        "message": (
            "init-verifiers helps you create verifier skills for automated code verification. "
            "Run this command with --interactive or provide verifier type and options."
        ),
    }
