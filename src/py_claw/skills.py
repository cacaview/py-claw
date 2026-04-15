from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from py_claw.schemas.common import EffortLevel


@dataclass(frozen=True, slots=True)
class DiscoveredSkill:
    name: str
    description: str
    content: str
    skill_path: str
    skill_root: str
    source: str
    argument_hint: str = ""
    when_to_use: str | None = None
    version: str | None = None
    model: str | None = None
    allowed_tools: list[str] | None = None
    effort: EffortLevel | None = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    # New fields for enhanced skill discovery
    paths: list[str] | None = None  # from paths: frontmatter for conditional activation
    hooks: dict | None = None  # hook configurations
    execution_context: str | None = None  # execution context hint
    agent: str | None = None  # agent name for agent-based skills
    display_name: str | None = None  # human-readable display name
    argument_names: list[str] | None = None  # named arguments
    shell: str | None = None  # shell inline execution config
    aliases: list[str] | None = None  # skill aliases
    context: dict | None = None  # additional context data


@dataclass(frozen=True, slots=True)
class ParsedSkillDocument:
    frontmatter: dict[str, object]
    content: str


def discover_local_skills(
    *,
    cwd: str,
    home_dir: str | None = None,
    settings_skills: list[str] | None = None,
    add_dirs: list[Path] | None = None,
) -> list[DiscoveredSkill]:
    catalog: dict[str, DiscoveredSkill] = {}
    user_root = Path(home_dir).expanduser() if home_dir is not None else Path.home()
    project_root = Path(cwd)

    # Standard locations
    for base_dir, source in (
        (user_root / ".claude" / "skills", "userSettings"),
        (project_root / ".claude" / "skills", "projectSettings"),
    ):
        for skill in _load_skills_dir(base_dir, source=source):
            catalog[skill.name] = skill

    # Policy tier (if CLAUDE_CODE_POLICY_DIR is set)
    policy_dir = get_policy_skills_path()
    if policy_dir and policy_dir.exists():
        for skill in _load_skills_dir(policy_dir, source="policy"):
            if skill.name not in catalog:
                catalog[skill.name] = skill

    # Additional directories (e.g., for nested discovery)
    if add_dirs:
        for base_dir in add_dirs:
            for skill in _load_skills_dir(base_dir, source="dynamic"):
                if skill.name not in catalog:
                    catalog[skill.name] = skill

    # Settings-only skills (no actual file)
    for name in sorted({str(item).strip() for item in (settings_skills or []) if str(item).strip()}):
        catalog.setdefault(
            name,
            DiscoveredSkill(
                name=name,
                description=f"Invoke the {name} skill",
                content="",
                skill_path="",
                skill_root="",
                source="settings",
            ),
        )

    return sorted(catalog.values(), key=lambda skill: skill.name)


def get_local_skill(
    name: str,
    *,
    cwd: str,
    home_dir: str | None = None,
    settings_skills: list[str] | None = None,
) -> DiscoveredSkill | None:
    normalized = name.strip().lstrip("/")
    if not normalized:
        return None
    for skill in discover_local_skills(cwd=cwd, home_dir=home_dir, settings_skills=settings_skills):
        if skill.name == normalized:
            return skill
    return None


def render_skill_prompt(skill: DiscoveredSkill, args: str | None = None) -> str:
    content = skill.content

    # Execute shell inline blocks if shell is enabled
    if skill.shell:
        content = execute_shell_in_prompt(content)

    if skill.skill_root:
        content = f"Base directory for this skill: {skill.skill_root}\n\n{content}"
    if skill.skill_root:
        content = content.replace("${CLAUDE_SKILL_DIR}", skill.skill_root.replace("\\", "/"))
    content = content.replace("${CLAUDE_SESSION_ID}", "")
    if args:
        return content.replace("$ARGUMENTS", args).replace("${ARGUMENTS}", args)
    return content.replace("$ARGUMENTS", "").replace("${ARGUMENTS}", "")


def _load_skills_dir(base_dir: Path, *, source: str) -> list[DiscoveredSkill]:
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    discovered: list[DiscoveredSkill] = []
    seen_realpaths: set[str] = set()  # for symlink deduplication

    for candidate in sorted(base_dir.iterdir(), key=lambda path: path.name):
        if not candidate.is_dir():
            continue

        # Symlink deduplication via realpath
        try:
            real_path = str(candidate.resolve())
            if real_path in seen_realpaths:
                continue
            seen_realpaths.add(real_path)
        except OSError:
            continue

        skill_file = candidate / "SKILL.md"
        if not skill_file.exists() or not skill_file.is_file():
            continue
        try:
            raw_text = skill_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        parsed = parse_skill_document(raw_text)
        skill_name = candidate.name
        description = _coerce_string(parsed.frontmatter.get("description")) or _extract_description(parsed.content)
        discovered.append(
            DiscoveredSkill(
                name=skill_name,
                description=description or f"Invoke the {skill_name} skill",
                content=parsed.content,
                skill_path=str(skill_file.resolve()),
                skill_root=str(candidate.resolve()),
                source=source,
                argument_hint=_coerce_string(parsed.frontmatter.get("argument-hint")) or "",
                when_to_use=_coerce_string(parsed.frontmatter.get("when_to_use"))
                or _coerce_string(parsed.frontmatter.get("when-to-use")),
                version=_coerce_string(parsed.frontmatter.get("version")),
                model=_coerce_string(parsed.frontmatter.get("model")),
                allowed_tools=_parse_string_list(
                    parsed.frontmatter.get("allowed-tools")
                    or parsed.frontmatter.get("allowed_tools")
                ),
                effort=_parse_effort_level(parsed.frontmatter.get("effort")),
                user_invocable=_parse_bool(parsed.frontmatter.get("user-invocable"), default=True),
                disable_model_invocation=_parse_bool(
                    parsed.frontmatter.get("disable-model-invocation"),
                    default=False,
                ),
                # New frontmatter fields
                paths=_parse_string_list_field(parsed.frontmatter.get("paths")),
                hooks=_parse_dict_field(parsed.frontmatter.get("hooks")),
                execution_context=_coerce_string(parsed.frontmatter.get("execution-context")),
                agent=_coerce_string(parsed.frontmatter.get("agent")),
                display_name=_coerce_string(parsed.frontmatter.get("display-name")),
                argument_names=_parse_string_list_field(parsed.frontmatter.get("argument-names")),
                shell=_coerce_string(parsed.frontmatter.get("shell")),
                aliases=_parse_string_list_field(parsed.frontmatter.get("aliases")),
                context=_parse_dict_field(parsed.frontmatter.get("context")),
            )
        )
    return discovered


def parse_skill_document(text: str) -> ParsedSkillDocument:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        return ParsedSkillDocument(frontmatter={}, content=normalized)

    frontmatter_lines: list[str] = []
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            content = "\n".join(lines[index + 1 :])
            return ParsedSkillDocument(frontmatter=_parse_frontmatter(frontmatter_lines), content=content)
        frontmatter_lines.append(lines[index])
    return ParsedSkillDocument(frontmatter={}, content=normalized)


def _parse_frontmatter(lines: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    current_list_key: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key is not None:
            current = result.setdefault(current_list_key, [])
            if isinstance(current, list):
                current.append(_parse_scalar(stripped[2:].strip()))
            continue
        if ":" not in line:
            current_list_key = None
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            current_list_key = None
            continue
        if not value:
            result[key] = []
            current_list_key = key
            continue
        result[key] = _parse_scalar(value)
        current_list_key = None
    return result


def _parse_scalar(value: str) -> object:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",") if item.strip()]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _coerce_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _parse_string_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else None
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item).strip()]
        return result or None
    coerced = str(value).strip()
    return [coerced] if coerced else None


def _parse_effort_level(value: object) -> EffortLevel | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"low", "medium", "high", "max"}:
        return normalized
    return None


def _parse_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return default


def _extract_description(content: str) -> str | None:
    paragraph: list[str] = []
    in_code_block = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            if paragraph:
                break
            continue
        if in_code_block:
            continue
        if not line:
            if paragraph:
                break
            continue
        if line.startswith("#"):
            continue
        paragraph.append(line)
    if not paragraph:
        return None
    return " ".join(paragraph)


def _parse_string_list_field(value: object) -> list[str] | None:
    """Parse a frontmatter value into a list of strings."""
    if value is None:
        return None
    if isinstance(value, list):
        result = [str(v).strip() for v in value if str(v).strip()]
        return result if result else None
    if isinstance(value, str):
        return [v.strip() for v in value.splitlines() if v.strip()] or None
    return None


def _parse_dict_field(value: object) -> dict | None:
    """Parse a frontmatter value into a dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return None


def get_policy_skills_path() -> Path | None:
    """Get the policy skills directory path from environment."""
    policy_dir = os.environ.get("CLAUDE_CODE_POLICY_DIR")
    if policy_dir:
        return Path(policy_dir)
    return None


def is_bare_mode() -> bool:
    """Check if bare mode is enabled via environment."""
    return os.environ.get("CLAUDE_CODE_BARE_MODE", "").lower() in ("1", "true", "yes")


def execute_shell_in_prompt(content: str) -> str:
    """
    Execute shell inline blocks (!... ) in skill prompt content.

    Shell blocks are of the form: !...shell command...!
    The shell command is executed and stdout is substituted back.

    Args:
        content: Skill prompt content potentially containing shell blocks

    Returns:
        Content with shell blocks replaced by command output
    """
    import re
    import subprocess

    def replace_shell_block(match: re.Match[str, str]) -> str:
        command = match.group(1).strip()
        if not command:
            return ""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            return f"[shell command timed out: {command[:50]}...]"
        except Exception as e:
            return f"[shell error: {str(e)[:50]}]"

    return re.sub(r"!([^!]+)!", replace_shell_block, content)


def estimate_skill_tokens(skill: DiscoveredSkill) -> int:
    """
    Estimate the token count for a skill's content.

    Uses a rough approximation: ~4 characters per token.

    Args:
        skill: The discovered skill

    Returns:
        Estimated token count
    """
    content = skill.content or ""
    # Rough approximation: 4 chars per token on average
    return len(content) // 4


def _load_commands_dir(base_dir: Path, *, source: str) -> list[DiscoveredSkill]:
    """
    Load skills from a legacy /commands/ directory.

    Supports namespace building from subdirectory structure:
        commands/docs/auth/login/SKILL.md -> name: "docs:auth:login"

    Args:
        base_dir: The commands directory root
        source: Source identifier

    Returns:
        List of discovered skills
    """
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    discovered: list[DiscoveredSkill] = []
    seen_realpaths: set[str] = set()

    def _walk_dir(current_dir: Path, namespace: list[str]) -> None:
        try:
            entries = list(current_dir.iterdir())
        except OSError:
            return

        for entry in sorted(entries, key=lambda p: p.name):
            if entry.name in {"node_modules", ".git", "__pycache__", ".venv", "venv"}:
                continue

            if entry.is_dir():
                # Check for SKILL.md in this directory
                skill_file = entry / "SKILL.md"
                if skill_file.exists() and skill_file.is_file():
                    try:
                        real_path = str(entry.resolve())
                        if real_path in seen_realpaths:
                            continue
                        seen_realpaths.add(real_path)
                    except OSError:
                        pass

                    skill_name_parts = namespace + [entry.name]
                    skill_name = ":".join(skill_name_parts)
                    try:
                        raw_text = skill_file.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        _walk_dir(entry, skill_name_parts)
                        continue
                    parsed = parse_skill_document(raw_text)
                    description = (
                        _coerce_string(parsed.frontmatter.get("description"))
                        or _extract_description(parsed.content)
                    )
                    discovered.append(
                        DiscoveredSkill(
                            name=skill_name,
                            description=description or f"Invoke the {skill_name} command",
                            content=parsed.content,
                            skill_path=str(skill_file.resolve()),
                            skill_root=str(entry.resolve()),
                            source=source,
                            argument_hint=_coerce_string(parsed.frontmatter.get("argument-hint")) or "",
                            when_to_use=_coerce_string(parsed.frontmatter.get("when_to_use"))
                            or _coerce_string(parsed.frontmatter.get("when-to-use")),
                        )
                    )
                else:
                    _walk_dir(entry, skill_name_parts)

    _walk_dir(base_dir, [])
    return discovered
