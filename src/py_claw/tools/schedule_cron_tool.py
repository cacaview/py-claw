from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


class CronCreateToolInput(PyClawBaseModel):
    cron: str
    prompt: str
    recurring: bool = True
    durable: bool = False


class CronDeleteToolInput(PyClawBaseModel):
    id: str


class CronListToolInput(PyClawBaseModel):
    pass


@dataclass(slots=True)
class _CronJob:
    id: str
    cron: str
    prompt: str
    recurring: bool
    durable: bool
    created_at: float

    def to_output(self) -> dict[str, object]:
        return {
            "id": self.id,
            "cron": self.cron,
            "humanSchedule": self.cron,
            "prompt": self.prompt,
            **({"recurring": True} if self.recurring else {}),
            **({"durable": False} if not self.durable else {}),
        }


def _validate_cron_expression(cron: str) -> None:
    parts = cron.split()
    if len(parts) != 5 or any(not part for part in parts):
        raise ToolError(f"Invalid cron expression '{cron}': expected 5 fields")


class _CronToolBase:
    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def _require_state(self) -> RuntimeState:
        if self._state is None:
            raise ToolError(f"{self.definition.name} requires runtime state")
        return self._state

    def _jobs(self) -> list[_CronJob]:
        state = self._require_state()
        stored = getattr(state, "scheduled_cron_jobs", None)
        if stored is None:
            stored = []
            state.scheduled_cron_jobs = stored
        jobs: list[_CronJob] = []
        for item in stored:
            if isinstance(item, _CronJob):
                jobs.append(item)
                continue
            if not isinstance(item, dict):
                continue
            try:
                jobs.append(
                    _CronJob(
                        id=str(item["id"]),
                        cron=str(item["cron"]),
                        prompt=str(item["prompt"]),
                        recurring=bool(item.get("recurring", True)),
                        durable=bool(item.get("durable", False)),
                        created_at=float(item.get("created_at", time())),
                    )
                )
            except Exception:
                continue
        stored[:] = jobs
        return jobs

    def _replace_jobs(self, jobs: list[_CronJob]) -> None:
        state = self._require_state()
        state.scheduled_cron_jobs = list(jobs)


class CronCreateTool(_CronToolBase):
    definition = ToolDefinition(name="CronCreate", input_model=CronCreateToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("cron")
        return ToolPermissionTarget(tool_name=self.definition.name, content=str(value) if isinstance(value, str) else None)

    def execute(self, arguments: CronCreateToolInput, *, cwd: str) -> dict[str, object]:
        del cwd
        _validate_cron_expression(arguments.cron)
        state = self._require_state()
        jobs = self._jobs()
        job = _CronJob(
            id=uuid4().hex[:8],
            cron=arguments.cron,
            prompt=arguments.prompt,
            recurring=arguments.recurring,
            durable=arguments.durable,
            created_at=time(),
        )
        jobs.append(job)
        self._replace_jobs(jobs)
        return {
            "id": job.id,
            "humanSchedule": job.cron,
            "recurring": job.recurring,
            **({"durable": True} if job.durable else {}),
        }


class CronDeleteTool(_CronToolBase):
    definition = ToolDefinition(name="CronDelete", input_model=CronDeleteToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        value = payload.get("id")
        return ToolPermissionTarget(tool_name=self.definition.name, content=str(value) if isinstance(value, str) else None)

    def execute(self, arguments: CronDeleteToolInput, *, cwd: str) -> dict[str, object]:
        del cwd
        jobs = self._jobs()
        remaining = [job for job in jobs if job.id != arguments.id]
        if len(remaining) == len(jobs):
            raise ToolError(f"No scheduled job with id '{arguments.id}'")
        self._replace_jobs(remaining)
        return {"id": arguments.id}


class CronListTool(_CronToolBase):
    definition = ToolDefinition(name="CronList", input_model=CronListToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        return ToolPermissionTarget(tool_name=self.definition.name)

    def execute(self, arguments: CronListToolInput, *, cwd: str) -> dict[str, object]:
        del arguments, cwd
        jobs = sorted(self._jobs(), key=lambda job: (job.created_at, job.id))
        return {"jobs": [job.to_output() for job in jobs]}
