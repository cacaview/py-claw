from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json

from pydantic import ValidationError as PydanticValidationError

from py_claw.settings.types import SettingsModel

FILE_PATTERN_TOOLS = {"Read", "Edit", "Write", "Glob", "Grep"}


@dataclass(slots=True)
class SettingsValidationIssue:
    path: str
    message: str
    file: str | None = None
    invalid_value: Any | None = None


@dataclass(slots=True)
class PermissionRuleValidationResult:
    valid: bool
    error: str | None = None
    suggestion: str | None = None


def validate_permission_rule(rule: str) -> PermissionRuleValidationResult:
    if not rule or rule.strip() == "":
        return PermissionRuleValidationResult(valid=False, error="Permission rule cannot be empty")

    open_count = _count_unescaped(rule, "(")
    close_count = _count_unescaped(rule, ")")
    if open_count != close_count:
        return PermissionRuleValidationResult(
            valid=False,
            error="Mismatched parentheses",
            suggestion="Ensure all opening parentheses have matching closing parentheses",
        )

    if _has_unescaped_empty_parens(rule):
        tool_name = rule.split("(", 1)[0]
        if not tool_name:
            return PermissionRuleValidationResult(
                valid=False,
                error="Empty parentheses with no tool name",
                suggestion="Specify a tool name before the parentheses",
            )
        return PermissionRuleValidationResult(
            valid=False,
            error="Empty parentheses",
            suggestion=f'Either specify a pattern or use just "{tool_name}" without parentheses',
        )

    tool_name, rule_content = _parse_permission_rule(rule)
    if not tool_name:
        return PermissionRuleValidationResult(valid=False, error="Tool name cannot be empty")

    if tool_name.startswith("mcp__"):
        if rule_content is not None or open_count > 0:
            return PermissionRuleValidationResult(
                valid=False,
                error="MCP rules do not support patterns in parentheses",
                suggestion=f'Use "{tool_name}" without parentheses',
            )
        return PermissionRuleValidationResult(valid=True)

    if tool_name[0] != tool_name[0].upper():
        return PermissionRuleValidationResult(
            valid=False,
            error="Tool names must start with uppercase",
            suggestion=f'Use "{tool_name[:1].upper()}{tool_name[1:]}"',
        )

    if rule_content is None:
        return PermissionRuleValidationResult(valid=True)

    if tool_name == "Bash":
        if ":*" in rule_content and not rule_content.endswith(":*"):
            return PermissionRuleValidationResult(
                valid=False,
                error="The :* pattern must be at the end",
                suggestion="Move :* to the end for prefix matching, or use * for wildcard matching",
            )
        if rule_content == ":*":
            return PermissionRuleValidationResult(
                valid=False,
                error="Prefix cannot be empty before :*",
                suggestion="Specify a command prefix before :*",
            )

    if tool_name in FILE_PATTERN_TOOLS and ":*" in rule_content:
        return PermissionRuleValidationResult(
            valid=False,
            error='The ":*" syntax is only for Bash prefix rules',
            suggestion="Use glob patterns like * or ** for file matching",
        )

    return PermissionRuleValidationResult(valid=True)


def filter_invalid_permission_rules(data: Any, file_path: str) -> list[SettingsValidationIssue]:
    if not isinstance(data, dict):
        return []
    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        return []

    issues: list[SettingsValidationIssue] = []
    for key in ("allow", "deny", "ask"):
        rules = permissions.get(key)
        if not isinstance(rules, list):
            continue

        filtered_rules: list[str] = []
        for rule in rules:
            if not isinstance(rule, str):
                issues.append(
                    SettingsValidationIssue(
                        file=file_path,
                        path=f"permissions.{key}",
                        message=f"Non-string value in {key} array was removed",
                        invalid_value=rule,
                    )
                )
                continue

            result = validate_permission_rule(rule)
            if not result.valid:
                message = f'Invalid permission rule "{rule}" was skipped'
                if result.error:
                    message += f": {result.error}"
                if result.suggestion:
                    message += f". {result.suggestion}"
                issues.append(
                    SettingsValidationIssue(
                        file=file_path,
                        path=f"permissions.{key}",
                        message=message,
                        invalid_value=rule,
                    )
                )
                continue
            filtered_rules.append(rule)

        permissions[key] = filtered_rules

    return issues


def validate_settings_data(data: Any, file_path: str) -> tuple[dict[str, Any] | None, list[SettingsValidationIssue]]:
    issues = filter_invalid_permission_rules(data, file_path)
    try:
        settings = SettingsModel.model_validate(data)
    except PydanticValidationError as exc:
        return None, issues + _format_validation_error(exc, file_path)
    return settings.model_dump(by_alias=True, exclude_none=True), issues


def validate_settings_text(content: str, file_path: str) -> tuple[dict[str, Any] | None, list[SettingsValidationIssue]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return None, [
            SettingsValidationIssue(
                file=file_path,
                path="",
                message=f"Invalid JSON: {exc.msg}",
            )
        ]
    return validate_settings_data(data, file_path)


def _format_validation_error(error: PydanticValidationError, file_path: str) -> list[SettingsValidationIssue]:
    issues: list[SettingsValidationIssue] = []
    for item in error.errors():
        path = ".".join(str(part) for part in item.get("loc", ()))
        issues.append(
            SettingsValidationIssue(
                file=file_path,
                path=path,
                message=item.get("msg", "Invalid settings value"),
                invalid_value=item.get("input"),
            )
        )
    return issues


def _parse_permission_rule(rule: str) -> tuple[str, str | None]:
    open_index = _find_first_unescaped(rule, "(")
    if open_index == -1:
        return rule, None
    return rule[:open_index], rule[open_index + 1 : -1]


def _has_unescaped_empty_parens(value: str) -> bool:
    for index in range(len(value) - 1):
        if value[index] == "(" and value[index + 1] == ")" and not _is_escaped(value, index):
            return True
    return False


def _count_unescaped(value: str, char: str) -> int:
    return sum(1 for index, current in enumerate(value) if current == char and not _is_escaped(value, index))


def _find_first_unescaped(value: str, char: str) -> int:
    for index, current in enumerate(value):
        if current == char and not _is_escaped(value, index):
            return index
    return -1


def _is_escaped(value: str, index: int) -> bool:
    backslash_count = 0
    cursor = index - 1
    while cursor >= 0 and value[cursor] == "\\":
        backslash_count += 1
        cursor -= 1
    return backslash_count % 2 == 1
