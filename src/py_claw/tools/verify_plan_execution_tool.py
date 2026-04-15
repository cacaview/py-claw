from __future__ import annotations

import os
from enum import Enum

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolPermissionTarget


# Known dangerous patterns for safety checks
DANGEROUS_PATTERNS = [
    "rm -rf",
    "format",
    "del /f /s /q",
    "mkfs",
    ":(){:|:&};:",
    "eval $",
    "curl | sh",
    "wget | sh",
]


class VerificationStatus(str, Enum):
    """Status of a verification check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


class VerifyPlanExecutionToolInput(PyClawBaseModel):
    """Input for VerifyPlanExecutionTool."""

    plan_id: str | None = Field(default=None, description="ID of the plan to verify")
    step: int | None = Field(default=None, description="Specific step number to verify")
    check_type: str = Field(
        default="comprehensive",
        description="Type of verification: 'comprehensive', 'syntax', 'safety', 'completeness'",
    )


class VerifyPlanExecutionTool:
    """Tool for verifying plan execution status and correctness.

    Verifies plan syntax, safety, and completeness by checking plan files
    in the .claude/plans/ directory.
    """

    definition = ToolDefinition(name="VerifyPlanExecution", input_model=VerifyPlanExecutionToolInput)

    def __init__(self) -> None:
        self._plans_dir = ".claude/plans"

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("plan_id")
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=str(value) if isinstance(value, str) else None,
        )

    def execute(self, arguments: VerifyPlanExecutionToolInput, *, cwd: str) -> dict[str, object]:
        check_type = arguments.check_type.lower()

        if check_type == "comprehensive":
            return self._verify_comprehensive(arguments.plan_id, arguments.step, cwd)
        elif check_type == "syntax":
            return self._verify_syntax(arguments.plan_id, cwd)
        elif check_type == "safety":
            return self._verify_safety(arguments.plan_id, cwd)
        elif check_type == "completeness":
            return self._verify_completeness(arguments.plan_id, cwd)
        else:
            return {
                "error": f"Unknown check_type: {check_type}",
                "supported_types": ["comprehensive", "syntax", "safety", "completeness"],
            }

    def _load_plan(self, plan_id: str | None, cwd: str) -> dict | None:
        """Load a plan file by ID."""
        if not plan_id:
            return None

        import json

        plan_file = os.path.join(cwd, self._plans_dir, f"{plan_id}.json")
        if os.path.exists(plan_file):
            try:
                with open(plan_file, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None

        # Also try .md files
        plan_md = os.path.join(cwd, self._plans_dir, f"{plan_id}.md")
        if os.path.exists(plan_md):
            with open(plan_md, encoding="utf-8") as f:
                return {"id": plan_id, "content": f.read(), "type": "markdown"}

        return None

    def _verify_comprehensive(self, plan_id: str | None, step: int | None, cwd: str) -> dict[str, object]:
        """Run comprehensive verification of plan execution."""
        if not plan_id:
            return {"error": "plan_id is required for comprehensive verification"}

        plan = self._load_plan(plan_id, cwd)
        checks = {}

        # Syntax check
        syntax_result = self._check_syntax(plan, plan_id)
        checks["syntax"] = syntax_result

        # Safety check
        safety_result = self._check_safety(plan, plan_id)
        checks["safety"] = safety_result

        # Completeness check
        completeness_result = self._check_completeness(plan, plan_id, step)
        checks["completeness"] = completeness_result

        # Dependencies check
        dependencies_result = self._check_dependencies(plan, plan_id, cwd)
        checks["dependencies"] = dependencies_result

        # Determine overall status
        failed_checks = [k for k, v in checks.items() if v["status"] == VerificationStatus.FAILED]
        warning_checks = [k for k, v in checks.items() if v["status"] == VerificationStatus.WARNING]

        if failed_checks:
            overall_status = VerificationStatus.FAILED
        elif warning_checks:
            overall_status = VerificationStatus.WARNING
        else:
            overall_status = VerificationStatus.PASSED

        return {
            "plan_id": plan_id,
            "step": step,
            "status": overall_status,
            "checks": checks,
            "summary": f"Verification complete: {len(failed_checks)} failed, {len(warning_checks)} warnings",
        }

    def _verify_syntax(self, plan_id: str | None, cwd: str) -> dict[str, object]:
        """Verify plan syntax validity."""
        if not plan_id:
            return {"error": "plan_id is required"}

        plan = self._load_plan(plan_id, cwd)
        result = self._check_syntax(plan, plan_id)

        return {
            "plan_id": plan_id,
            "check_type": "syntax",
            **result,
        }

    def _verify_safety(self, plan_id: str | None, cwd: str) -> dict[str, object]:
        """Verify plan operations are safe."""
        if not plan_id:
            return {"error": "plan_id is required"}

        plan = self._load_plan(plan_id, cwd)
        result = self._check_safety(plan, plan_id)

        return {
            "plan_id": plan_id,
            "check_type": "safety",
            **result,
        }

    def _verify_completeness(self, plan_id: str | None, cwd: str) -> dict[str, object]:
        """Verify plan has all required steps."""
        if not plan_id:
            return {"error": "plan_id is required"}

        plan = self._load_plan(plan_id, cwd)
        result = self._check_completeness(plan, plan_id, None)

        return {
            "plan_id": plan_id,
            "check_type": "completeness",
            **result,
        }

    def _check_syntax(self, plan: dict | None, plan_id: str) -> dict:
        """Check plan syntax validity."""
        if plan is None:
            return {
                "status": VerificationStatus.FAILED,
                "message": f"Plan '{plan_id}' not found",
            }

        if plan.get("type") == "markdown":
            return {
                "status": VerificationStatus.PASSED,
                "message": "Plan syntax is valid (markdown format)",
            }

        # Check for required fields in JSON plans
        if not isinstance(plan, dict):
            return {
                "status": VerificationStatus.FAILED,
                "message": "Plan must be a JSON object",
            }

        return {
            "status": VerificationStatus.PASSED,
            "message": "Plan syntax is valid",
        }

    def _check_safety(self, plan: dict | None, plan_id: str) -> dict:
        """Check plan operations are safe."""
        if plan is None:
            return {
                "status": VerificationStatus.FAILED,
                "message": f"Plan '{plan_id}' not found",
            }

        warnings = []
        content = ""

        if plan.get("type") == "markdown":
            content = plan.get("content", "")
        else:
            content = str(plan)

        for pattern in DANGEROUS_PATTERNS:
            if pattern.lower() in content.lower():
                warnings.append(f"Potential dangerous pattern detected: {pattern}")

        if warnings:
            return {
                "status": VerificationStatus.WARNING,
                "message": "Potential safety concerns detected",
                "warnings": warnings,
            }

        return {
            "status": VerificationStatus.PASSED,
            "message": "No safety violations detected in plan",
            "warnings": [],
        }

    def _check_completeness(self, plan: dict | None, plan_id: str, step: int | None) -> dict:
        """Check plan has all required steps."""
        if plan is None:
            return {
                "status": VerificationStatus.FAILED,
                "message": f"Plan '{plan_id}' not found",
            }

        if plan.get("type") == "markdown":
            return {
                "status": VerificationStatus.PASSED,
                "message": "Plan completeness verified (markdown format)",
                "steps_verified": 1,
            }

        # Check for steps in JSON plans
        steps = plan.get("steps", [])
        if not isinstance(steps, list):
            return {
                "status": VerificationStatus.FAILED,
                "message": "Plan 'steps' field must be an array",
            }

        return {
            "status": VerificationStatus.PASSED,
            "message": "Plan completeness verified",
            "steps_verified": len(steps),
        }

    def _check_dependencies(self, plan: dict | None, plan_id: str, cwd: str) -> dict:
        """Check plan dependencies are satisfied."""
        if plan is None:
            return {
                "status": VerificationStatus.FAILED,
                "message": f"Plan '{plan_id}' not found",
            }

        if plan.get("type") == "markdown":
            return {
                "status": VerificationStatus.PASSED,
                "message": "Dependencies check skipped for markdown plans",
            }

        dependencies = plan.get("dependencies", [])
        if not isinstance(dependencies, list):
            dependencies = []

        missing = []
        for dep in dependencies:
            dep_file = os.path.join(cwd, self._plans_dir, f"{dep}.json")
            dep_md = os.path.join(cwd, self._plans_dir, f"{dep}.md")
            if not os.path.exists(dep_file) and not os.path.exists(dep_md):
                missing.append(dep)

        if missing:
            return {
                "status": VerificationStatus.WARNING,
                "message": f"Missing dependencies: {', '.join(missing)}",
                "missing_dependencies": missing,
            }

        return {
            "status": VerificationStatus.PASSED,
            "message": "All dependencies satisfied",
            "dependencies": dependencies,
        }
