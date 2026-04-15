from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py_claw.schemas.control import ControlSettingsSource
from py_claw.settings.merge import merge_settings
from py_claw.settings.validation import SettingsValidationIssue, validate_settings_data, validate_settings_text

SETTING_SOURCES: tuple[ControlSettingsSource, ...] = (
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
)


@dataclass(slots=True)
class SettingsLoadResult:
    effective: dict[str, Any]
    sources: list[dict[str, Any]]
    issues: list[SettingsValidationIssue] = field(default_factory=list)


def get_settings_file_path_for_source(
    source: ControlSettingsSource,
    *,
    cwd: str | None = None,
    home_dir: str | None = None,
) -> Path | None:
    project_root = Path(cwd or Path.cwd())
    user_home = Path(home_dir or Path.home())
    match source:
        case "userSettings":
            return user_home / ".claude" / "settings.json"
        case "projectSettings":
            return project_root / ".claude" / "settings.json"
        case "localSettings":
            return project_root / ".claude" / "settings.local.json"
        case "flagSettings" | "policySettings":
            return None


def load_settings_from_path(path: Path) -> tuple[dict[str, Any] | None, list[SettingsValidationIssue]]:
    if not path.exists():
        return None, []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [
            SettingsValidationIssue(
                file=str(path),
                path="",
                message=str(exc),
            )
        ]
    return validate_settings_text(content, str(path))


def load_settings_for_source(
    source: ControlSettingsSource,
    *,
    flag_settings: dict[str, Any] | None = None,
    policy_settings: dict[str, Any] | None = None,
    cwd: str | None = None,
    home_dir: str | None = None,
) -> tuple[dict[str, Any] | None, list[SettingsValidationIssue]]:
    if source == "flagSettings":
        if not flag_settings:
            return None, []
        return validate_settings_data(dict(flag_settings), "flagSettings")

    if source == "policySettings":
        if not policy_settings:
            return None, []
        return validate_settings_data(dict(policy_settings), "policySettings")

    path = get_settings_file_path_for_source(source, cwd=cwd, home_dir=home_dir)
    if path is None:
        return None, []
    return load_settings_from_path(path)


def get_settings_with_sources(
    *,
    flag_settings: dict[str, Any] | None = None,
    policy_settings: dict[str, Any] | None = None,
    cwd: str | None = None,
    home_dir: str | None = None,
) -> SettingsLoadResult:
    effective: dict[str, Any] = {}
    sources: list[dict[str, Any]] = []
    issues: list[SettingsValidationIssue] = []

    for source in SETTING_SOURCES:
        settings, source_issues = load_settings_for_source(
            source,
            flag_settings=flag_settings,
            policy_settings=policy_settings,
            cwd=cwd,
            home_dir=home_dir,
        )
        issues.extend(source_issues)
        if settings:
            sources.append({"source": source, "settings": settings})
            effective = merge_settings(effective, settings)

    return SettingsLoadResult(effective=effective, sources=sources, issues=issues)
