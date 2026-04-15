from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from py_claw.schemas.common import PermissionBehavior, PermissionMode
from py_claw.settings.loader import SettingsLoadResult
from py_claw.permissions.rules import PermissionRule, PermissionRuleSource, parse_permission_rule_value

PERMISSION_RULE_SOURCE_ORDER: tuple[PermissionRuleSource, ...] = (
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
    "cliArg",
    "command",
    "session",
)
_ALLOWED_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "bypassPermissions",
    "plan",
    "dontAsk",
}


@dataclass(slots=True)
class PermissionContext:
    mode: PermissionMode = "default"
    allow_rules: dict[PermissionRuleSource, list[PermissionRule]] = field(default_factory=dict)
    deny_rules: dict[PermissionRuleSource, list[PermissionRule]] = field(default_factory=dict)
    ask_rules: dict[PermissionRuleSource, list[PermissionRule]] = field(default_factory=dict)
    additional_directories: list[str] = field(default_factory=list)
    disable_bypass_permissions_mode: bool = False
    allow_managed_permission_rules_only: bool = False

    def rules_for_behavior(self, behavior: PermissionBehavior) -> list[PermissionRule]:
        source_map = _source_map_for_behavior(self, behavior)
        if self.allow_managed_permission_rules_only:
            return list(source_map.get("policySettings", ()))

        rules: list[PermissionRule] = []
        for source in PERMISSION_RULE_SOURCE_ORDER:
            rules.extend(source_map.get(source, ()))
        return rules


def build_permission_context(settings: SettingsLoadResult, *, mode: PermissionMode = "default") -> PermissionContext:
    permissions = settings.effective.get("permissions") if isinstance(settings.effective, dict) else None
    default_mode = _coerce_permission_mode((permissions or {}).get("defaultMode") if isinstance(permissions, dict) else None)
    disable_bypass_permissions_mode = (
        isinstance(permissions, dict) and permissions.get("disableBypassPermissionsMode") == "disable"
    )
    additional_directories = list((permissions or {}).get("additionalDirectories") or []) if isinstance(permissions, dict) else []
    allow_managed_permission_rules_only = settings.effective.get("allowManagedPermissionRulesOnly") is True

    context = PermissionContext(
        mode=_resolve_permission_mode(mode, default_mode, disable_bypass_permissions_mode),
        additional_directories=[directory for directory in additional_directories if isinstance(directory, str)],
        disable_bypass_permissions_mode=disable_bypass_permissions_mode,
        allow_managed_permission_rules_only=allow_managed_permission_rules_only,
    )

    for source_entry in settings.sources:
        source = source_entry.get("source")
        source_settings = source_entry.get("settings")
        if source not in PERMISSION_RULE_SOURCE_ORDER or not isinstance(source_settings, dict):
            continue
        if allow_managed_permission_rules_only and source != "policySettings":
            continue

        source_permissions = source_settings.get("permissions")
        if not isinstance(source_permissions, dict):
            continue

        for behavior in ("allow", "deny", "ask"):
            rules = source_permissions.get(behavior)
            if not isinstance(rules, list):
                continue
            parsed_rules = [
                PermissionRule(
                    source=source,
                    rule_behavior=behavior,
                    rule_value=parse_permission_rule_value(rule),
                )
                for rule in rules
                if isinstance(rule, str)
            ]
            if not parsed_rules:
                continue
            _source_map_for_behavior(context, behavior).setdefault(source, []).extend(parsed_rules)

    return context


def _resolve_permission_mode(
    mode: PermissionMode,
    default_mode: PermissionMode | None,
    disable_bypass_permissions_mode: bool,
) -> PermissionMode:
    resolved = default_mode if mode == "default" and default_mode is not None else mode
    if resolved == "bypassPermissions" and disable_bypass_permissions_mode:
        return "default"
    return resolved


def _coerce_permission_mode(value: Any) -> PermissionMode | None:
    if isinstance(value, str) and value in _ALLOWED_PERMISSION_MODES:
        return value
    return None


def _source_map_for_behavior(
    context: PermissionContext,
    behavior: PermissionBehavior,
) -> dict[PermissionRuleSource, list[PermissionRule]]:
    if behavior == "allow":
        return context.allow_rules
    if behavior == "deny":
        return context.deny_rules
    return context.ask_rules
