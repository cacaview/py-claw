from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

if TYPE_CHECKING:
    from py_claw.fork.process import ForkedAgentProcess

TaskStatus = Literal["pending", "in_progress", "completed"]
TaskType = Literal["generic", "local_bash", "local_agent"]


@dataclass(slots=True)
class TaskRecord:
    id: str
    subject: str
    description: str
    status: TaskStatus = "pending"
    active_form: str | None = None
    owner: str | None = None
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    task_type: TaskType = "generic"
    command: str | None = None
    output_file: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error: str | None = None


@dataclass(slots=True)
class TeamRecord:
    team_name: str
    description: str | None = None
    leader_agent_id: str | None = None
    member_agent_ids: set[str] = field(default_factory=set)
    member_names: set[str] = field(default_factory=set)


@dataclass(slots=True)
class LocalAgentExchange:
    summary: str | None
    user_message: str
    assistant_text: str


@dataclass(slots=True)
class LocalAgentSession:
    agent_id: str
    task_id: str
    agent_name: str
    description: str
    cwd: str
    system_prompt: str
    output_file: str
    model: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    backend_type: str = "placeholder"
    exchanges: list[LocalAgentExchange] = field(default_factory=list)
    name: str | None = None
    team_name: str | None = None


@dataclass(slots=True)
class TaskRuntime:
    _agent_sessions: dict[str, LocalAgentSession] = field(default_factory=dict)
    _agent_task_ids: dict[str, str] = field(default_factory=dict)
    _agent_names: dict[str, str] = field(default_factory=dict)
    _teams: dict[str, TeamRecord] = field(default_factory=dict)
    _tasks: dict[str, TaskRecord] = field(default_factory=dict)
    _next_id: int = 1
    _processes: dict[str, subprocess.Popen[str]] = field(default_factory=dict)
    _forked_processes: dict[str, "ForkedAgentProcess"] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _updated: threading.Condition = field(init=False)

    def __post_init__(self) -> None:
        self._updated = threading.Condition(self._lock)

    def create(self, *, subject: str, description: str, active_form: str | None = None) -> TaskRecord:
        with self._lock:
            task_id = str(self._next_id)
            self._next_id += 1
            record = TaskRecord(
                id=task_id,
                subject=subject,
                description=description,
                active_form=active_form,
            )
            self._tasks[task_id] = record
            return record

    def create_background_shell_task(
        self,
        *,
        command: str,
        cwd: str,
        description: str | None = None,
    ) -> TaskRecord:
        with self._lock:
            task_id = str(self._next_id)
            self._next_id += 1
            output_file = self._task_output_path(cwd, task_id)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("", encoding="utf-8")
            record = TaskRecord(
                id=task_id,
                subject=description or command,
                description=description or command,
                status="in_progress",
                active_form="Running background command",
                task_type="local_bash",
                command=command,
                output_file=str(output_file),
            )
            self._tasks[task_id] = record
            self._updated.notify_all()
            return record

    def attach_process(self, task_id: str, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._require_task(task_id)
            self._processes[task_id] = process
            self._updated.notify_all()

    def get_forked_process(self, agent_id: str) -> "ForkedAgentProcess | None":
        """Get the forked subprocess for an agent session, if one exists."""
        with self._lock:
            return self._forked_processes.get(agent_id)

    def stop_forked_process(self, agent_id: str) -> None:
        """Stop a forked agent subprocess and update session status."""
        with self._lock:
            process = self._forked_processes.pop(agent_id, None)
            if process:
                try:
                    process.terminate(timeout=5.0)
                except Exception:
                    pass
            session = self._agent_sessions.get(agent_id)
            if session:
                record = self._tasks.get(session.task_id)
                if record and record.status == "in_progress":
                    record.status = "completed"

    def create_agent_session(
        self,
        *,
        agent_name: str,
        description: str,
        cwd: str,
        system_prompt: str,
        initial_prompt: str,
        assistant_text: str,
        model: str | None = None,
        allowed_tools: list[str] | None = None,
        backend_type: str = "placeholder",
        name: str | None = None,
        team_name: str | None = None,
        spawn_subagent: bool = False,
        mcp_servers: list[dict[str, Any]] | None = None,
        isolation: dict[str, Any] | None = None,
    ) -> LocalAgentSession:
        with self._lock:
            task_id = str(self._next_id)
            self._next_id += 1
            output_file = self._task_output_path(cwd, task_id)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            agent_id = f"agent-{uuid4().hex[:12]}"
            exchange = LocalAgentExchange(
                summary="Initial prompt",
                user_message=initial_prompt,
                assistant_text=assistant_text,
            )
            session = LocalAgentSession(
                agent_id=agent_id,
                task_id=task_id,
                agent_name=agent_name,
                description=description,
                cwd=cwd,
                system_prompt=system_prompt,
                output_file=str(output_file),
                model=model,
                allowed_tools=list(allowed_tools or []),
                backend_type=backend_type,
                exchanges=[exchange],
                name=name,
                team_name=team_name,
            )

            if spawn_subagent:
                # Spawn persistent forked subprocess for teammate
                from py_claw.fork.process import ForkedAgentProcess
                from py_claw.fork.protocol import build_fork_boilerplate

                effective_system_prompt = system_prompt
                if effective_system_prompt:
                    effective_system_prompt = (
                        effective_system_prompt
                        + "\n\n"
                        + build_fork_boilerplate(
                              parent_session_id="main",
                              child_session_id=agent_id,
                              transcript=[],
                          )
                    ).strip()

                process = ForkedAgentProcess(
                    session_id=agent_id,
                    system_prompt=effective_system_prompt,
                    model=model,
                    allowed_tools=allowed_tools,
                    cwd=cwd,
                    mcp_servers=mcp_servers,
                    isolation=isolation,
                )
                process.spawn()
                process.send_init()
                process.send_turn(initial_prompt, turn_count=0)

                # Wait for initial turn result
                try:
                    result = process.send_turn_sync(initial_prompt, turn_count=0, timeout=120.0)
                    exchange.assistant_text = result.get("assistant_text", assistant_text)
                except Exception:
                    pass  # Use provided assistant_text on error

                self._forked_processes[agent_id] = process
                status: TaskStatus = "in_progress"
            else:
                status = "completed"

            output = self._render_agent_output(session)
            output_file.write_text(output, encoding="utf-8")
            record = TaskRecord(
                id=task_id,
                subject=description,
                description=description,
                status=status,
                active_form="Running background agent",
                task_type="local_agent",
                output_file=str(output_file),
                stdout=output,
            )
            self._tasks[task_id] = record
            self._agent_sessions[agent_id] = session
            self._agent_task_ids[task_id] = agent_id
            self._agent_names[agent_name] = agent_id
            if name:
                self._agent_names[name] = agent_id
            self._updated.notify_all()
            return session

    def resolve_agent_session(self, recipient: str) -> LocalAgentSession:
        with self._lock:
            if recipient in self._agent_sessions:
                return self._agent_sessions[recipient]
            task_id = recipient.strip()
            agent_id = self._agent_task_ids.get(task_id)
            if agent_id is not None:
                return self._agent_sessions[agent_id]
            named_agent_id = self._agent_names.get(recipient)
            if named_agent_id is not None:
                return self._agent_sessions[named_agent_id]
            for session in self._agent_sessions.values():
                if session.name == recipient:
                    return session
            raise KeyError(f"Unknown agent session: {recipient}")

    def append_agent_exchange(
        self,
        agent_id: str,
        *,
        summary: str | None,
        user_message: str,
        assistant_text: str,
    ) -> LocalAgentSession:
        with self._lock:
            session = self._agent_sessions[agent_id]
            session.exchanges.append(
                LocalAgentExchange(
                    summary=summary,
                    user_message=user_message,
                    assistant_text=assistant_text,
                )
            )
            record = self._require_task(session.task_id)
            output = self._render_agent_output(session)
            record.stdout = output
            if record.output_file is not None:
                Path(record.output_file).write_text(output, encoding="utf-8")
            self._updated.notify_all()
            return session

    def create_team(
        self,
        team_name: str,
        *,
        description: str | None = None,
        leader_agent_id: str | None = None,
        leader_name: str | None = None,
    ) -> TeamRecord:
        with self._lock:
            record = TeamRecord(
                team_name=team_name,
                description=description,
                leader_agent_id=leader_agent_id,
            )
            if leader_agent_id is not None:
                record.member_agent_ids.add(leader_agent_id)
            if leader_name is not None:
                record.member_names.add(leader_name)
            self._teams[team_name] = record
            return record

    def delete_team(self, team_name: str) -> TeamRecord:
        with self._lock:
            try:
                record = self._teams.pop(team_name)
            except KeyError as exc:
                raise KeyError(f"Unknown team: {team_name}") from exc
            for session in self._agent_sessions.values():
                if session.team_name == team_name:
                    session.team_name = None
            return record

    def get_team(self, team_name: str) -> TeamRecord:
        with self._lock:
            try:
                return self._teams[team_name]
            except KeyError as exc:
                raise KeyError(f"Unknown team: {team_name}") from exc

    def has_team(self, team_name: str) -> bool:
        with self._lock:
            return team_name in self._teams

    def list_teams(self) -> list[TeamRecord]:
        with self._lock:
            return [self._teams[name] for name in sorted(self._teams)]

    def register_team_member(self, team_name: str, agent_id: str, *, member_name: str | None = None) -> TeamRecord:
        with self._lock:
            team = self._teams.get(team_name)
            if team is None:
                team = self.create_team(team_name)
            team.member_agent_ids.add(agent_id)
            if member_name is not None:
                team.member_names.add(member_name)
            return team

    def unregister_team_member(self, team_name: str, agent_id: str | None = None, *, member_name: str | None = None) -> None:
        with self._lock:
            team = self._teams.get(team_name)
            if team is None:
                return
            if agent_id is not None:
                team.member_agent_ids.discard(agent_id)
                if team.leader_agent_id == agent_id:
                    team.leader_agent_id = None
            if member_name is not None:
                team.member_names.discard(member_name)
            if not team.member_agent_ids and not team.member_names and team.leader_agent_id is None:
                self._teams.pop(team_name, None)

    def append_output(self, task_id: str, content: str, *, stream: str) -> None:
        if not content:
            return
        with self._lock:
            record = self._require_task(task_id)
            if stream == "stdout":
                record.stdout += content
            else:
                record.stderr += content
            if record.output_file is not None:
                with Path(record.output_file).open("a", encoding="utf-8") as handle:
                    handle.write(content)
            self._updated.notify_all()

    def mark_process_finished(self, task_id: str, exit_code: int | None) -> None:
        with self._lock:
            record = self._require_task(task_id)
            record.exit_code = exit_code
            if exit_code not in (None, 0) and record.error is None:
                record.error = f"Command exited with code {exit_code}"
            record.status = "completed"
            self._processes.pop(task_id, None)
            self._updated.notify_all()

    def mark_process_failed(self, task_id: str, message: str) -> None:
        with self._lock:
            record = self._require_task(task_id)
            record.error = message
            record.status = "completed"
            self._processes.pop(task_id, None)
            self._updated.notify_all()

    def stop(self, task_id: str) -> TaskRecord:
        with self._lock:
            record = self._require_task(task_id)
            process = self._processes.get(task_id)
            if record.status != "in_progress" or process is None:
                raise ValueError(f"Task {task_id} is not running")
        try:
            process.terminate()
            exit_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait(timeout=5)
        with self._lock:
            record = self._require_task(task_id)
            record.error = "Task stopped"
            record.exit_code = exit_code
            record.status = "completed"
            self._processes.pop(task_id, None)
            self._updated.notify_all()
            return record

    def wait_for_task(self, task_id: str, timeout_ms: int) -> TaskRecord:
        deadline = time.monotonic() + (timeout_ms / 1000)
        with self._updated:
            record = self._require_task(task_id)
            while record.status in {"pending", "in_progress"}:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._updated.wait(timeout=remaining)
                record = self._require_task(task_id)
            return record

    def get(self, task_id: str) -> TaskRecord:
        with self._lock:
            return self._require_task(task_id)

    def list(self) -> list[TaskRecord]:
        with self._lock:
            return [self._tasks[task_id] for task_id in sorted(self._tasks, key=_task_sort_key)]

    def update(
        self,
        task_id: str,
        *,
        subject: str | None = None,
        description: str | None = None,
        active_form: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        add_blocks: list[str] | None = None,
        add_blocked_by: list[str] | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            record = self._require_task(task_id)
            if status == "deleted":
                del self._tasks[task_id]
                self._processes.pop(task_id, None)
                for task in self._tasks.values():
                    task.blocks = [value for value in task.blocks if value != task_id]
                    task.blocked_by = [value for value in task.blocked_by if value != task_id]
                self._updated.notify_all()
                return None
            if status is not None and status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"Invalid task status: {status}")
            if add_blocks:
                self._ensure_known_tasks(add_blocks)
                for value in add_blocks:
                    if value != task_id and value not in record.blocks:
                        record.blocks.append(value)
            if add_blocked_by:
                self._ensure_known_tasks(add_blocked_by)
                for value in add_blocked_by:
                    if value != task_id and value not in record.blocked_by:
                        record.blocked_by.append(value)
            if subject is not None:
                record.subject = subject
            if description is not None:
                record.description = description
            if active_form is not None:
                record.active_form = active_form
            if status is not None:
                record.status = status
            if owner is not None:
                record.owner = owner
            self._updated.notify_all()
            return record

    def summary(self, task: TaskRecord) -> dict[str, object]:
        with self._lock:
            data: dict[str, object] = {
                "id": task.id,
                "subject": task.subject,
                "status": task.status,
                "owner": task.owner,
                "blockedBy": self._open_dependencies(task.blocked_by),
            }
            if task.task_type != "generic":
                data["taskType"] = task.task_type
            return data

    def detail(self, task: TaskRecord) -> dict[str, object]:
        with self._lock:
            data: dict[str, object] = {
                "id": task.id,
                "subject": task.subject,
                "description": task.description,
                "status": task.status,
                "activeForm": task.active_form,
                "owner": task.owner,
                "blocks": self._open_dependencies(task.blocks),
                "blockedBy": self._open_dependencies(task.blocked_by),
            }
            if task.task_type != "generic":
                data["taskType"] = task.task_type
            if task.command is not None:
                data["command"] = task.command
            if task.output_file is not None:
                data["outputFile"] = task.output_file
            if task.exit_code is not None:
                data["exitCode"] = task.exit_code
            if task.error is not None:
                data["error"] = task.error
            session = self._session_for_task(task.id)
            if session is not None:
                data["agentId"] = session.agent_id
                data["agentType"] = session.agent_name
                data["model"] = session.model
                if session.team_name is not None:
                    data["teamName"] = session.team_name
            return data

    def output(self, task: TaskRecord) -> dict[str, object]:
        with self._lock:
            data: dict[str, object] = {
                "task_id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "description": task.description,
                "output": self._combined_output(task),
            }
            if task.command is not None:
                data["command"] = task.command
            if task.output_file is not None:
                data["output_file"] = task.output_file
            if task.exit_code is not None:
                data["exitCode"] = task.exit_code
            if task.error is not None:
                data["error"] = task.error
            session = self._session_for_task(task.id)
            if session is not None:
                data["agent_id"] = session.agent_id
                data["agentType"] = session.agent_name
                if session.team_name is not None:
                    data["teamName"] = session.team_name
            return data

    def agent_session(self, recipient: str) -> dict[str, object]:
        session = self.resolve_agent_session(recipient)
        return {
            "agent_id": session.agent_id,
            "task_id": session.task_id,
            "agentType": session.agent_name,
            "description": session.description,
            "model": session.model,
            "allowedTools": list(session.allowed_tools),
            "backendType": session.backend_type,
            "exchangeCount": len(session.exchanges),
            "teamName": session.team_name,
        }

    def agent_exchanges(self, recipient: str) -> list[dict[str, object]]:
        session = self.resolve_agent_session(recipient)
        return [
            {
                "summary": exchange.summary,
                "userMessage": exchange.user_message,
                "assistantText": exchange.assistant_text,
            }
            for exchange in session.exchanges
        ]

    def has_agent_session(self, recipient: str) -> bool:
        try:
            self.resolve_agent_session(recipient)
        except KeyError:
            return False
        return True

    def list_agent_sessions(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "agent_id": session.agent_id,
                    "task_id": session.task_id,
                    "agentType": session.agent_name,
                    "description": session.description,
                    "exchangeCount": len(session.exchanges),
                    "teamName": session.team_name,
                }
                for session in self._agent_sessions.values()
            ]

    def _require_task(self, task_id: str) -> TaskRecord:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"Unknown task: {task_id}") from exc

    def _require_agent_session(self, agent_id: str) -> LocalAgentSession:
        try:
            return self._agent_sessions[agent_id]
        except KeyError as exc:
            raise KeyError(f"Unknown agent session: {agent_id}") from exc

    def _ensure_known_tasks(self, task_ids: list[str]) -> None:
        missing = [task_id for task_id in task_ids if task_id not in self._tasks]
        if missing:
            joined = ", ".join(missing)
            raise KeyError(f"Unknown task ids: {joined}")

    def _open_dependencies(self, task_ids: list[str]) -> list[str]:
        values: list[str] = []
        for task_id in task_ids:
            task = self._tasks.get(task_id)
            if task is not None and task.status != "completed":
                values.append(task_id)
        return values

    def _combined_output(self, task: TaskRecord) -> str:
        return "\n".join(part.rstrip("\n") for part in (task.stdout, task.stderr) if part).rstrip()

    def _render_agent_output(self, session: LocalAgentSession) -> str:
        parts = [
            f"agent_id: {session.agent_id}",
            f"agent_name: {session.agent_name}",
            f"backend_type: {session.backend_type}",
        ]
        if session.team_name is not None:
            parts.append(f"team_name: {session.team_name}")
        if session.model is not None:
            parts.append(f"model: {session.model}")
        if session.allowed_tools:
            parts.append(f"allowed_tools: {', '.join(session.allowed_tools)}")
        parts.append("")
        for index, exchange in enumerate(session.exchanges, start=1):
            parts.append(f"[{index}] user")
            if exchange.summary:
                parts.append(f"summary: {exchange.summary}")
            parts.append(exchange.user_message)
            parts.append("")
            parts.append(f"[{index}] assistant")
            parts.append(exchange.assistant_text)
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    def _task_output_path(self, cwd: str, task_id: str) -> Path:
        return Path(cwd) / ".py_claw" / "tasks" / f"{task_id}.log"

    def _session_for_task(self, task_id: str) -> LocalAgentSession | None:
        agent_id = self._agent_task_ids.get(task_id)
        if agent_id is None:
            return None
        return self._agent_sessions.get(agent_id)



def _task_sort_key(task_id: str) -> tuple[int, str]:
    return (0, str(int(task_id))) if task_id.isdigit() else (1, task_id)
