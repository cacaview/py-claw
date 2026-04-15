from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Literal

from py_claw.schemas.common import PermissionBehavior, PermissionRuleValue

PermissionRuleSource = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
    "session",
    "cliArg",
    "command",
]


@dataclass(slots=True)
class PermissionRule:
    source: PermissionRuleSource
    rule_behavior: PermissionBehavior
    rule_value: PermissionRuleValue


@dataclass(slots=True)
class PermissionTarget:
    tool_name: str
    content: str | None = None


def parse_permission_rule_value(rule: str) -> PermissionRuleValue:
    open_index = _find_first_unescaped(rule, "(")
    if open_index == -1:
        return PermissionRuleValue(toolName=rule)
    return PermissionRuleValue(toolName=rule[:open_index], ruleContent=rule[open_index + 1 : -1])


def permission_rule_value_to_string(rule_value: PermissionRuleValue) -> str:
    if rule_value.ruleContent is None:
        return rule_value.toolName
    return f"{rule_value.toolName}({rule_value.ruleContent})"


def matches_permission_rule(rule: PermissionRule, target: PermissionTarget) -> bool:
    if not _tool_name_matches(rule.rule_value.toolName, target.tool_name):
        return False

    pattern = rule.rule_value.ruleContent
    if pattern is None:
        return True
    if target.content is None:
        return False

    if rule.rule_value.toolName == "Bash" and pattern.endswith(":*"):
        return target.content.startswith(pattern[:-2])

    return fnmatchcase(target.content, pattern)


def _tool_name_matches(rule_tool_name: str, tool_name: str) -> bool:
    if rule_tool_name == tool_name:
        return True

    if not (rule_tool_name.startswith("mcp__") and tool_name.startswith("mcp__")):
        return False

    if rule_tool_name.endswith("__*"):
        return tool_name.startswith(rule_tool_name[:-3] + "__")

    if rule_tool_name.count("__") == 1:
        return tool_name.startswith(rule_tool_name + "__")

    return False


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
