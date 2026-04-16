from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field, model_validator

from py_claw.schemas.common import PyClawBaseModel
from py_claw.settings.loader import get_settings_with_sources
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    from py_claw.cli.runtime import RuntimeState


_ASK_USER_QUESTION_SERVER = "ask-user-question"


class AskUserQuestionOption(PyClawBaseModel):
    label: str
    description: str
    preview: str | None = None


class AskUserQuestionAnnotation(PyClawBaseModel):
    preview: str | None = None
    notes: str | None = None


class AskUserQuestionMetadata(PyClawBaseModel):
    source: str | None = None


class AskUserQuestionQuestion(PyClawBaseModel):
    question: str
    header: str
    options: list[AskUserQuestionOption] = Field(min_length=2, max_length=4)
    multiSelect: bool = False

    @model_validator(mode="after")
    def validate_unique_option_labels(self) -> AskUserQuestionQuestion:
        labels = [option.label for option in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("Option labels must be unique within each question")
        return self


class AskUserQuestionToolInput(PyClawBaseModel):
    questions: list[AskUserQuestionQuestion] = Field(min_length=1, max_length=4)
    answers: dict[str, str] | None = None
    annotations: dict[str, AskUserQuestionAnnotation] | None = None
    metadata: AskUserQuestionMetadata | None = None

    @model_validator(mode="after")
    def validate_unique_question_texts(self) -> AskUserQuestionToolInput:
        questions = [question.question for question in self.questions]
        if len(questions) != len(set(questions)):
            raise ValueError("Question texts must be unique")
        return self


class AskUserQuestionTool:
    definition = ToolDefinition(name="AskUserQuestion", input_model=AskUserQuestionToolInput)

    def __init__(self, state: RuntimeState | None = None) -> None:
        self._state = state

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        questions = payload.get("questions")
        if not isinstance(questions, list):
            return ToolPermissionTarget(tool_name=self.definition.name)
        question_texts: list[str] = []
        for item in questions:
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            if isinstance(question, str) and question:
                question_texts.append(question)
        content = " | ".join(question_texts) if question_texts else None
        return ToolPermissionTarget(tool_name=self.definition.name, content=content)

    def execute(self, arguments: AskUserQuestionToolInput, *, cwd: str) -> dict[str, object]:
        if arguments.answers is not None:
            return self._build_result(
                questions=arguments.questions,
                answers=arguments.answers,
                annotations=arguments.annotations,
            )

        state = self._require_state()
        settings = get_settings_with_sources(
            flag_settings=state.flag_settings,
            policy_settings=state.policy_settings,
            cwd=state.cwd,
            home_dir=state.home_dir,
        )
        hook_result = state.hook_runtime.run_elicitation(
            settings=settings,
            cwd=state.cwd,
            mcp_server_name=_ASK_USER_QUESTION_SERVER,
            message=self._build_message(arguments.questions),
            mode="form",
            url=None,
            elicitation_id=arguments.metadata.source if arguments.metadata is not None else None,
            requested_schema=self._build_requested_schema(arguments.questions),
            permission_mode=state.permission_mode,
        )
        if hook_result.action is not None:
            action = hook_result.action
            content = hook_result.content
        else:
            callback = getattr(state, "ask_user_callback", None)
            if callback is not None:
                action, content = callback(arguments)
            else:
                action = "cancel"
                content = None

        result_hook = state.hook_runtime.run_elicitation_result(
            settings=settings,
            cwd=state.cwd,
            mcp_server_name=_ASK_USER_QUESTION_SERVER,
            elicitation_id=arguments.metadata.source if arguments.metadata is not None else None,
            mode="form",
            action=action,
            content=content,
            permission_mode=state.permission_mode,
        )
        if result_hook.action is not None:
            action = result_hook.action
        if result_hook.content is not None:
            content = result_hook.content

        if action == "decline":
            raise ToolError("User declined to answer questions")
        if action != "accept":
            raise ToolError("User did not answer questions")

        answers, annotations = self._normalize_content(content, arguments.questions)
        return self._build_result(
            questions=arguments.questions,
            answers=answers,
            annotations=annotations,
        )

    def _require_state(self) -> RuntimeState:
        if self._state is None:
            raise ToolError("AskUserQuestion requires runtime state when answers are not provided")
        return self._state

    def _build_message(self, questions: list[AskUserQuestionQuestion]) -> str:
        lines = ["Answer the following multiple-choice questions."]
        for question in questions:
            option_summary = "; ".join(f"{option.label}: {option.description}" for option in question.options)
            qualifier = " (multi-select)" if question.multiSelect else ""
            lines.append(f"- [{question.header}] {question.question}{qualifier} Options: {option_summary}")
        return "\n".join(lines)

    def _build_requested_schema(self, questions: list[AskUserQuestionQuestion]) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for question in questions:
            labels = [option.label for option in question.options]
            if question.multiSelect:
                schema: dict[str, Any] = {
                    "type": "array",
                    "items": {"type": "string", "enum": labels},
                    "uniqueItems": True,
                    "title": question.header,
                    "description": question.question,
                }
            else:
                schema = {
                    "type": "string",
                    "enum": labels,
                    "title": question.header,
                    "description": question.question,
                }
            properties[question.question] = schema
            required.append(question.question)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def _normalize_content(
        self,
        content: dict[str, Any] | None,
        questions: list[AskUserQuestionQuestion],
    ) -> tuple[dict[str, str], dict[str, AskUserQuestionAnnotation] | None]:
        if content is None:
            raise ToolError("AskUserQuestion completed without answers")
        if not isinstance(content, dict):
            raise ToolError("AskUserQuestion received invalid elicitation content")

        raw_answers = content.get("answers") if isinstance(content.get("answers"), dict) else content
        if not isinstance(raw_answers, dict):
            raise ToolError("AskUserQuestion received invalid answers")

        answers: dict[str, str] = {}
        for question in questions:
            if question.question not in raw_answers:
                continue
            normalized = self._normalize_answer_value(raw_answers[question.question])
            if normalized is not None:
                answers[question.question] = normalized
        if not answers:
            raise ToolError("AskUserQuestion completed without answers")

        annotations = self._normalize_annotations(content.get("annotations"))
        return answers, annotations

    def _normalize_answer_value(self, value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = [str(item) for item in value if isinstance(item, (str, int, float, bool))]
            return ", ".join(parts) if parts else None
        if isinstance(value, (int, float, bool)):
            return str(value)
        return None

    def _normalize_annotations(self, value: Any) -> dict[str, AskUserQuestionAnnotation] | None:
        if not isinstance(value, dict):
            return None
        annotations: dict[str, AskUserQuestionAnnotation] = {}
        for question, payload in value.items():
            if not isinstance(question, str) or not isinstance(payload, dict):
                continue
            try:
                annotations[question] = AskUserQuestionAnnotation.model_validate(payload)
            except Exception:
                continue
        return annotations or None

    def _build_result(
        self,
        *,
        questions: list[AskUserQuestionQuestion],
        answers: dict[str, str],
        annotations: dict[str, AskUserQuestionAnnotation] | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "questions": [question.model_dump(exclude_none=True) for question in questions],
            "answers": answers,
        }
        if annotations:
            payload["annotations"] = {
                question: annotation.model_dump(exclude_none=True) for question, annotation in annotations.items()
            }
        return payload
