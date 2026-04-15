"""
Skill discovery service - main facade for dynamic/conditional skill discovery.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .state import get_skill_discovery_state, reset_skill_discovery_state, SkillDiscoveryState
from .types import SkillActivationType

if TYPE_CHECKING:
    from py_claw.skills import DiscoveredSkill


class SkillDiscoveryService:
    """
    Facade for dynamic and conditional skill discovery.

    Supports:
    - Always-on skills: loaded immediately on startup
    - Conditional skills: activated when matching current file paths
    - Dynamic skills: discovered from nested skill directories
    - Policy tier: skills from CLAUDE_CODE_POLICY_DIR
    - Bare mode: discover skills without project context
    """

    def __init__(self) -> None:
        self._state: SkillDiscoveryState = get_skill_discovery_state()
        self._initialized: bool = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(
        self,
        *,
        cwd: str | None = None,
        home_dir: str | None = None,
        settings_skills: list[str] | None = None,
    ) -> None:
        """
        Initialize skill discovery: load always-on and conditional skills.

        Args:
            cwd: Current working directory (project root)
            home_dir: User home directory
            settings_skills: Skills explicitly listed in settings
        """
        if self._initialized:
            return

        user_root = Path(home_dir).expanduser() if home_dir else Path.home()
        project_root = Path(cwd) if cwd else Path.cwd()

        # Load always-on skills from standard locations
        self._load_standard_skills(user_root, project_root, settings_skills)

        # Check for bare mode
        if self._is_bare_mode():
            self._load_bare_mode_skills(project_root)

        # Check for policy tier
        policy_dir = self._get_policy_skills_path()
        if policy_dir and policy_dir.exists():
            self._load_policy_skills(policy_dir)

        self._initialized = True

    def _load_standard_skills(
        self,
        user_root: Path,
        project_root: Path,
        settings_skills: list[str] | None,
    ) -> None:
        """Load skills from user and project standard locations."""
        from py_claw.skills import _load_skills_dir

        for base_dir, source in (
            (user_root / ".claude" / "skills", "userSettings"),
            (project_root / ".claude" / "skills", "projectSettings"),
        ):
            for skill in _load_skills_dir(base_dir, source=source):
                if skill.name not in self._state.all_skills:
                    self._state.add_always_skill(skill.name, skill)

    def _load_bare_mode_skills(self, project_root: Path) -> None:
        """Load skills in bare mode (no project context)."""
        from .dynamic import discover_skill_dirs_for_paths
        from py_claw.skills import DiscoveredSkill, parse_skill_document

        bare_skills_dir = project_root / ".claude" / "skills"
        if not bare_skills_dir.exists():
            return

        skill_dirs = discover_skill_dirs_for_paths(
            bare_skills_dir,
            repo_root=project_root,
            state=self._state,
        )

        for skill_dir in skill_dirs:
            name = skill_dir.name
            if name in self._state.all_skills:
                continue
            skill_file = skill_dir / "SKILL.md"
            try:
                raw_text = skill_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            parsed = parse_skill_document(raw_text)
            skill = DiscoveredSkill(
                name=name,
                description="",
                content=parsed.content,
                skill_path=str(skill_file),
                skill_root=str(skill_dir),
                source="bareMode",
            )
            self._state.add_always_skill(name, skill)

    def _load_policy_skills(self, policy_dir: Path) -> None:
        """Load skills from policy directory."""
        from .dynamic import discover_skill_dirs_for_paths
        from py_claw.skills import DiscoveredSkill, parse_skill_document

        skill_dirs = discover_skill_dirs_for_paths(
            policy_dir,
            repo_root=policy_dir,
            state=self._state,
        )

        for skill_dir in skill_dirs:
            name = skill_dir.name
            if name in self._state.all_skills:
                continue
            skill_file = skill_dir / "SKILL.md"
            try:
                raw_text = skill_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            parsed = parse_skill_document(raw_text)
            skill = DiscoveredSkill(
                name=name,
                description="",
                content=parsed.content,
                skill_path=str(skill_file),
                skill_root=str(skill_dir),
                source="policy",
            )
            self._state.add_always_skill(name, skill)

    def activate_for_paths(self, current_paths: list[str]) -> list[str]:
        """
        Activate conditional skills matching the given file paths.

        Args:
            current_paths: Current file paths being processed

        Returns:
            List of activated skill names
        """
        from .dynamic import activate_conditional_skills_for_paths

        conditional = self._state.get_conditional_skills()
        skill_dirs: list[Path] = []

        # Find skill directories for conditional skills
        for name, skill in conditional.items():
            skill_root = Path(skill.skill_root)
            if skill_root.exists():
                skill_dirs.append(skill_root)

        conditions = {
            name: self._state.get_condition(name)
            for name in conditional
            if self._state.get_condition(name)
        }

        return activate_conditional_skills_for_paths(
            skill_dirs,
            {name: skill for name, skill in conditional.items()},
            conditions,
            current_paths,
        )

    def get_active_skills(self) -> dict[str, "DiscoveredSkill"]:
        """Get all currently active skills (always + dynamic + activated conditional)."""
        return self._state.get_active_skills()

    def get_all_states(self) -> dict[str, "DiscoveredSkillState"]:
        """Get all skill states."""
        return self._state.get_all_states()

    def discover_nested_skills_dirs(self, base_dir: Path, *, source: str) -> None:
        """
        Discover and load nested skill directories under base_dir.

        Args:
            base_dir: Root directory to search within
            source: Source identifier for loaded skills
        """
        from .dynamic import discover_nested_skills_in_dir

        discover_nested_skills_in_dir(base_dir, source=source, repo_root=base_dir)

    @staticmethod
    def _is_bare_mode() -> bool:
        """Check if bare mode is enabled."""
        return os.environ.get("CLAUDE_CODE_BARE_MODE", "").lower() in ("1", "true", "yes")

    @staticmethod
    def _get_policy_skills_path() -> Path | None:
        """Get the policy skills directory path."""
        policy_dir = os.environ.get("CLAUDE_CODE_POLICY_DIR")
        if policy_dir:
            return Path(policy_dir)
        return None


def get_skill_discovery_service() -> SkillDiscoveryService:
    """Get the global skill discovery service instance."""
    global _skill_discovery_service
    if _skill_discovery_service is None:
        _skill_discovery_service = SkillDiscoveryService()
    return _skill_discovery_service


def reset_skill_discovery_service() -> None:
    """Reset the global skill discovery service (for testing)."""
    global _skill_discovery_service
    _skill_discovery_service = None
    reset_skill_discovery_state()


# ------------------------------------------------------------------
# Global singleton
# ------------------------------------------------------------------

_skill_discovery_service: SkillDiscoveryService | None = None


# Import here to avoid circular import
from .types import DiscoveredSkillState
