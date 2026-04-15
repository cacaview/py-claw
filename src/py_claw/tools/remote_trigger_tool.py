"""
Remote Trigger Tool.

Manages scheduled remote Claude Code agents (triggers) via the claude.ai CCR API.
Auth is handled in-process — the token never reaches the shell.

Based on TS RemoteTriggerTool implementation.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any

from pydantic import Field, model_validator

from py_claw.schemas.common import PyClawBaseModel
from py_claw.services.oauth.service import get_oauth_service
from py_claw.services.policy_limits import is_policy_allowed
from py_claw.tools.base import ToolDefinition, ToolError


# Feature gate - must be enabled via feature flag
REMOTE_TRIGGER_FEATURE_FLAG = "tengu_surreal_dali"


class RemoteTriggerInput(PyClawBaseModel):
    """Input for RemoteTrigger tool."""

    action: str = Field(description="Action: list, get, create, update, run")
    trigger_id: str | None = Field(default=None, description="Trigger ID for get, update, run")
    body: dict[str, Any] | None = Field(default=None, description="JSON body for create/update")

    @model_validator(mode="after")
    def validate_fields(self) -> RemoteTriggerInput:
        if self.action in ("get", "update", "run") and not self.trigger_id:
            raise ValueError(f"{self.action} requires trigger_id")
        if self.action in ("create", "update") and not self.body:
            raise ValueError(f"{self.action} requires body")
        return self


@dataclass
class RemoteTriggerResult:
    """Result of a remote trigger operation."""
    status: int
    json: str


class RemoteTriggerTool:
    """Tool for managing remote triggers via claude.ai CCR API."""

    definition = ToolDefinition(
        name="RemoteTrigger",
        input_model=RemoteTriggerInput,
    )

    def __init__(self) -> None:
        pass

    def permission_target(self, payload: dict[str, object]) -> Any:
        action = payload.get("action")
        trigger_id = payload.get("trigger_id")
        parts = []
        if isinstance(action, str):
            parts.append(f"action:{action}")
        if isinstance(trigger_id, str):
            parts.append(f"trigger:{trigger_id}")
        return parts

    def execute(self, arguments: RemoteTriggerInput, *, cwd: str) -> dict[str, object]:
        """Execute a remote trigger operation."""
        # Check feature flag
        # In Python we use a simplified check - always allowed for now
        # In TS: getFeatureValue_CACHED_MAY_BE_STALE('tengu_surreal_dali', false)

        # Check policy
        if not is_policy_allowed("allow_remote_sessions"):
            raise ToolError(
                "Remote sessions are not allowed by your organization policy. "
                "Contact your administrator to enable this feature."
            )

        # Get OAuth tokens
        oauth_service = get_oauth_service()
        tokens = oauth_service.get_tokens()

        if not tokens or not tokens.access_token:
            raise ToolError(
                "Not authenticated with a claude.ai account. "
                "Run /login and try again."
            )

        # Get organization UUID from profile
        profile = oauth_service.get_profile()
        if not profile:
            raise ToolError("Unable to get organization information.")

        # Build request
        base_url = "https://api.claude.ai"
        headers = {
            "Authorization": f"Bearer {tokens.access_token}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "ccr-triggers-2026-01-30",
        }

        # Get org UUID
        org_uuid = profile.get("org_uuid") or profile.get("organization_uuid")
        if org_uuid:
            headers["x-organization-uuid"] = org_uuid

        # Build URL and data based on action
        action = arguments.action
        url = f"{base_url}/v1/code/triggers"
        data = None
        method = "GET"

        if action == "list":
            method = "GET"
        elif action == "get":
            method = "GET"
            url = f"{url}/{arguments.trigger_id}"
        elif action == "create":
            method = "POST"
            data = json.dumps(arguments.body).encode("utf-8") if arguments.body else None
        elif action == "update":
            method = "POST"
            url = f"{url}/{arguments.trigger_id}"
            data = json.dumps(arguments.body).encode("utf-8") if arguments.body else None
        elif action == "run":
            method = "POST"
            url = f"{url}/{arguments.trigger_id}/run"
            data = b"{}"
        else:
            raise ToolError(f"Unknown action: {action}")

        # Make request
        try:
            req = urllib.request.Request(
                url,
                method=method,
                data=data,
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                response_data = response.read().decode("utf-8")
                try:
                    json_data = json.dumps(json.loads(response_data), indent=2)
                except json.JSONDecodeError:
                    json_data = json.dumps({"raw": response_data})

                return {
                    "status": response.status,
                    "json": json_data,
                }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise ToolError(
                f"HTTP error {e.code}: {e.reason}\n{error_body}"
            )
        except urllib.error.URLError as e:
            raise ToolError(f"Network error: {e.reason}")
