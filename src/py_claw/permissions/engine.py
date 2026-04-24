from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from py_claw.schemas.common import PermissionMode
from py_claw.settings.loader import SettingsLoadResult
from py_claw.permissions.rules import PermissionRule, PermissionTarget, matches_permission_rule
from py_claw.permissions.state import PermissionContext, build_permission_context
from py_claw.services.permissions.classifier_decision import classify_yolo_action

PermissionOutcome = Literal["allow", "deny", "ask"]


@dataclass(slots=True)
class PermissionEvaluation:
    behavior: PermissionOutcome
    mode: PermissionMode
    matched_rule: PermissionRule | None = None
    reason: str | None = None


class PermissionEngine:
    def __init__(self, context: PermissionContext) -> None:
        self.context = context

    @classmethod
    def from_settings(cls, settings: SettingsLoadResult, *, mode: PermissionMode = "default") -> "PermissionEngine":
        return cls(build_permission_context(settings, mode=mode))

    def evaluate(self, tool_name: str, content: str | None = None) -> PermissionEvaluation:
        target = PermissionTarget(tool_name=tool_name, content=content)

        deny_rule = self._find_matching_rule("deny", target)
        if deny_rule is not None:
            return PermissionEvaluation(
                behavior="deny",
                mode=self.context.mode,
                matched_rule=deny_rule,
                reason="deny_rule",
            )

        ask_rule = self._find_matching_rule("ask", target)
        if ask_rule is not None:
            return self._finalize_ask_result(
                PermissionEvaluation(
                    behavior="ask",
                    mode=self.context.mode,
                    matched_rule=ask_rule,
                    reason="ask_rule",
                )
            )

        if self.context.mode == "bypassPermissions":
            return PermissionEvaluation(behavior="allow", mode=self.context.mode, reason="mode")

        allow_rule = self._find_matching_rule("allow", target)
        if allow_rule is not None:
            return PermissionEvaluation(
                behavior="allow",
                mode=self.context.mode,
                matched_rule=allow_rule,
                reason="allow_rule",
            )

        # No rule matched - use YOLO classifier as fallback before defaulting to ask
        # This provides automatic allow/deny for known-safe/dangerous operations
        yolo_result = classify_yolo_action(
            messages=[],
            action=tool_name,
            tools=[],
            permission_context={"mode": self.context.mode},
            abort_signal=None,
        )
        if yolo_result["should_block"]:
            return PermissionEvaluation(
                behavior="deny",
                mode=self.context.mode,
                reason=f"yolo:{yolo_result['reason']}",
            )

        return self._finalize_ask_result(PermissionEvaluation(behavior="ask", mode=self.context.mode, reason="default"))

    def _finalize_ask_result(self, evaluation: PermissionEvaluation) -> PermissionEvaluation:
        if evaluation.behavior == "ask" and self.context.mode == "dontAsk":
            return PermissionEvaluation(behavior="deny", mode=self.context.mode, matched_rule=evaluation.matched_rule, reason="mode")
        return evaluation

    def _find_matching_rule(self, behavior: Literal["allow", "deny", "ask"], target: PermissionTarget) -> PermissionRule | None:
        for rule in self.context.rules_for_behavior(behavior):
            if matches_permission_rule(rule, target):
                return rule
        return None
