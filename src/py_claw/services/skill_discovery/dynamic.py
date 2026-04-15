"""
Dynamic skill discovery for nested skill directories and conditional activation.

Handles:
- Recursive skill directory discovery within project trees
- Conditional skill activation based on paths frontmatter
- Gitignore-aware discovery
- Symlink deduplication via realpath
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .state import get_skill_discovery_state, SkillDiscoveryState
from .types import SkillCondition

if TYPE_CHECKING:
    from py_claw.skills import DiscoveredSkill


# ------------------------------------------------------------------
# Gitignore checking
# ------------------------------------------------------------------


def _is_gitignored(path: Path, repo_root: Path) -> bool:
    """Check if a path is gitignored by walking up to repo_root."""
    try:
        resolved = path.resolve()
        repo_resolved = repo_root.resolve()
        rel = resolved.relative_to(repo_resolved)
        gitignore_path = repo_root / ".gitignore"
        if not gitignore_path.exists():
            return False
        gitignore_text = gitignore_path.read_text(encoding="utf-8")
        patterns = _parse_gitignore(gitignore_text)
        for part in rel.parts:
            for pattern in patterns:
                if _gitignore_match(part, pattern):
                    return True
    except (ValueError, OSError):
        pass
    return False


def _parse_gitignore(text: str) -> list[tuple[str, bool]]:
    """Parse .gitignore into list of (pattern, is_negated)."""
    patterns: list[tuple[str, bool]] = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        patterns.append((line, negated))
    return patterns


def _gitignore_match(name: str, pattern: str) -> bool:
    """Simple gitignore pattern match for a single path component."""
    if pattern.endswith("/"):
        return False  # Directory-only pattern, skip for single name
    if pattern == name:
        return True
    if "?" in pattern or "*" in pattern or "[" in pattern:
        regex = pattern.replace(".", r"\.").replace("?", ".").replace("*", ".*")
        return bool(re.match(f"^{regex}$", name))
    return False


# ------------------------------------------------------------------
# Dynamic discovery
# ------------------------------------------------------------------


def discover_skill_dirs_for_paths(
    base_dir: Path,
    *,
    repo_root: Path | None = None,
    state: SkillDiscoveryState | None = None,
    depth: int = 0,
    max_depth: int = 5,
) -> list[Path]:
    """
    Recursively discover skill directories within base_dir.

    Skips:
    - Directories that have already been discovered (tracked in state)
    - Gitignored directories
    - Node_modules, .git, __pycache__, .venv, and similar
    - Symlinks that resolve to already-seen paths (dedup via realpath)

    Args:
        base_dir: Root directory to search within
        repo_root: Root of the repository (for gitignore checking)
        state: Skill discovery state for tracking discovered dirs
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        List of discovered skill directory paths
    """
    if depth > max_depth:
        return []
    if state is None:
        state = get_skill_discovery_state()

    resolved = base_dir.resolve()
    resolved_str = str(resolved)

    # Skip if already discovered
    if state.is_dir_discovered(resolved_str):
        return []

    # Mark as discovered immediately to avoid reprocessing
    state.add_discovered_dir(resolved_str)

    if repo_root is None:
        repo_root = base_dir

    SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv", ".venv",
        "site-packages", ".tox", ".pytest_cache", ".mypy_cache",
        ".claude", ".claude-plugin", ".claude-skills",
    }

    discovered: list[Path] = []

    try:
        entries = list(base_dir.iterdir())
    except OSError:
        return []

    for entry in entries:
        name = entry.name
        if name in SKIP_DIRS or name.startswith("."):
            continue

        # Check if it's a skill directory
        if entry.is_dir():
            skill_file = entry / "SKILL.md"
            if skill_file.exists() and skill_file.is_file():
                # Skip if gitignored (only for non-user, non-project standard locations)
                if repo_root and not _is_gitignored(entry, repo_root):
                    discovered.append(entry)
            else:
                # Recurse into non-skill directories
                discovered.extend(
                    discover_skill_dirs_for_paths(
                        entry,
                        repo_root=repo_root,
                        state=state,
                        depth=depth + 1,
                        max_depth=max_depth,
                    )
                )

    return discovered


def activate_conditional_skills_for_paths(
    skill_dirs: list[Path],
    all_skills: dict[str, "DiscoveredSkill"],
    skill_conditions: dict[str, "SkillCondition"],
    current_paths: list[str],
) -> list[str]:
    """
    Activate conditional skills whose paths glob patterns match current_paths.

    Args:
        skill_dirs: Discovered skill directory paths
        all_skills: All known skills (name -> DiscoveredSkill)
        skill_conditions: Skill name -> SkillCondition mapping
        current_paths: Current file paths being processed

    Returns:
        List of activated skill names
    """
    state = get_skill_discovery_state()
    activated: list[str] = []

    for skill_dir in skill_dirs:
        name = skill_dir.name
        if name not in skill_conditions:
            continue
        condition = skill_conditions[name]
        if condition and condition.glob_patterns:
            if _match_any_pattern(current_paths, condition.glob_patterns):
                skill = state.activate_skill(name)
                if skill:
                    activated.append(name)

    return activated


def _match_any_pattern(paths: list[str], patterns: list[str]) -> bool:
    """Check if any path matches any of the glob patterns."""
    import fnmatch

    for path in paths:
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern):
                return True
            # Also check if pattern could match as a directory prefix
            if path.startswith(pattern.rstrip("/")):
                return True
    return False


def discover_nested_skills_in_dir(
    base_dir: Path,
    *,
    source: str,
    repo_root: Path | None = None,
    parent_condition: SkillCondition | None = None,
) -> dict[str, "DiscoveredSkill"]:
    """
    Discover skills in a directory including nested subdirectories.

    Args:
        base_dir: Base directory to search
        source: Source identifier (e.g., "userSettings", "projectSettings", "policy")
        repo_root: Repository root for gitignore checking
        parent_condition: Condition inherited from parent skill directory

    Returns:
        Dictionary of discovered skills (name -> DiscoveredSkill)
    """
    from py_claw.skills import _load_skills_dir, DiscoveredSkill

    state = get_skill_discovery_state()
    skills: dict[str, DiscoveredSkill] = {}

    # Discover skill directories recursively
    skill_dirs = discover_skill_dirs_for_paths(
        base_dir,
        repo_root=repo_root or base_dir,
        state=state,
    )

    # Load skills from discovered directories
    for skill_dir in skill_dirs:
        name = skill_dir.name
        if name in skills:
            continue  # Already loaded

        skill_file = skill_dir / "SKILL.md"
        try:
            raw_text = skill_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        from py_claw.skills import parse_skill_document
        parsed = parse_skill_document(raw_text)

        # Check for paths frontmatter (conditional skill)
        paths_value = parsed.frontmatter.get("paths")
        if paths_value is not None:
            from .types import SkillCondition
            paths_list = _parse_paths_list(paths_value)
            condition = SkillCondition.from_paths_list(paths_list)
            if condition.glob_patterns is None:
                # paths: [] or match-all means unconditional
                state.add_always_skill(name, DiscoveredSkill(
                    name=name,
                    description="",
                    content=parsed.content,
                    skill_path=str(skill_file),
                    skill_root=str(skill_dir),
                    source=source,
                ))
            else:
                state.add_conditional_skill(name, DiscoveredSkill(
                    name=name,
                    description="",
                    content=parsed.content,
                    skill_path=str(skill_file),
                    skill_root=str(skill_dir),
                    source=source,
                ), condition)
            skills[name] = state.all_skills[name].skill
        else:
            # Regular always-on skill
            skill = DiscoveredSkill(
                name=name,
                description="",
                content=parsed.content,
                skill_path=str(skill_file),
                skill_root=str(skill_dir),
                source=source,
            )
            state.add_always_skill(name, skill)
            skills[name] = skill

    return skills


def _parse_paths_list(value: object) -> list[str]:
    """Parse paths value from frontmatter into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.splitlines() if v.strip()]
    return []
