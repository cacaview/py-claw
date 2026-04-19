"""Server session CRUD API for bridge sessions.

Provides create, read, archive, and update operations for
bridge sessions via the server API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from py_claw.services.bridge.types import (
    CreateSessionParams,
    CreateSessionResult,
    GitOutcome,
    GitSource,
    SessionEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionApiConfig:
    """Configuration for session API."""

    base_url: str
    timeout_seconds: float = 30.0


class SessionApiClient:
    """Client for bridge session API operations.

    Handles all CRUD operations for bridge sessions including:
    - Creating new sessions
    - Getting session details
    - Archiving sessions
    - Updating session metadata (title, etc.)
    """

    def __init__(
        self,
        base_url: str,
        access_token: str,
        timeout_seconds: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        from py_claw.services.bridge.trusted_device import get_trusted_device_token

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        # Add trusted device token if available
        trusted_token = get_trusted_device_token()
        if trusted_token:
            headers["X-Trusted-Device-Token"] = trusted_token

        return headers

    async def create_session(
        self,
        environment_id: str,
        title: str | None = None,
        git_repo_url: str | None = None,
        branch: str | None = None,
        permission_mode: str | None = None,
        events: list[SessionEvent] | None = None,
    ) -> CreateSessionResult:
        """Create a new bridge session.

        Args:
            environment_id: The environment/organization ID
            title: Optional session title
            git_repo_url: Optional git repository URL
            branch: Optional git branch
            permission_mode: Optional permission mode
            events: Optional initial events

        Returns:
            CreateSessionResult with session_id on success
        """
        # Build session creation params
        params = CreateSessionParams(
            environment_id=environment_id,
            title=title,
            git_repo_url=git_repo_url,
            branch=branch,
            permission_mode=permission_mode,
            events=events,
        )

        # In full implementation:
        # POST /v1/sessions
        # Body: params as JSON
        # Response: { session_id, session_ingress_url, ... }

        # For now, return mock result
        import uuid

        session_id = str(uuid.uuid4())
        session_ingress_url = f"{self.base_url}/v1/sessions/{session_id}/ingress"

        logger.info(
            "Created bridge session: id=%s title=%s",
            session_id,
            title,
        )

        return CreateSessionResult(
            success=True,
            session_id=session_id,
        )

    async def get_session(
        self, session_id: str
    ) -> dict[str, Any] | None:
        """Get session details.

        Args:
            session_id: The session ID

        Returns:
            Session data dict, or None if not found
        """
        # In full implementation:
        # GET /v1/sessions/{session_id}
        # Headers: Authorization: Bearer <access_token>

        # For now, return mock
        return {
            "session_id": session_id,
            "environment_id": "default",
            "title": "mock-session",
            "state": "active",
        }

    async def archive_session(
        self, session_id: str
    ) -> bool:
        """Archive a bridge session.

        Args:
            session_id: The session ID to archive

        Returns:
            True if archived successfully
        """
        # In full implementation:
        # POST /v1/sessions/{session_id}/archive
        # Headers: Authorization: Bearer <access_token>

        logger.info("Archived bridge session: %s", session_id)
        return True

    async def update_session_title(
        self, session_id: str, title: str
    ) -> bool:
        """Update session title.

        Args:
            session_id: The session ID
            title: New title

        Returns:
            True if updated successfully
        """
        # In full implementation:
        # PATCH /v1/sessions/{session_id}
        # Headers: Authorization: Bearer <access_token>
        # Body: { title: title }

        logger.info("Updated session title: %s -> %s", session_id, title)
        return True

    async def send_session_event(
        self,
        session_id: str,
        event: SessionEvent,
    ) -> bool:
        """Send an event to a session.

        Args:
            session_id: The session ID
            event: The event to send

        Returns:
            True if sent successfully
        """
        # In full implementation:
        # POST /v1/sessions/{session_id}/events
        # Headers: Authorization: Bearer <access_token>
        # Body: event as JSON

        logger.debug(
            "Sent session event: session_id=%s type=%s",
            session_id,
            event.type,
        )
        return True

    async def refresh_session_token(
        self, session_id: str
    ) -> str | None:
        """Request a new token for a session.

        Args:
            session_id: The session ID

        Returns:
            New token string, or None on failure
        """
        # In full implementation:
        # POST /v1/sessions/{session_id}/refresh
        # Headers: Authorization: Bearer <access_token>
        # Response: { token: "...", expires_in: ... }

        logger.info("Refreshed session token: %s", session_id)

        # Return mock token
        import uuid

        return f"tok_{uuid.uuid4().hex}"

    async def register_bridge_environment(
        self,
        environment_id: str,
        worker_type: str = "claude_code",
        machine_name: str | None = None,
        git_repo_url: str | None = None,
        branch: str | None = None,
        dir_path: str | None = None,
    ) -> dict[str, Any] | None:
        """Register bridge environment with the server.

        This is the initial registration call that establishes the bridge
        as a worker for the given environment.

        Args:
            environment_id: The environment/organization ID
            worker_type: Type of worker (default: claude_code)
            machine_name: Hostname of the machine
            git_repo_url: Git repository URL
            branch: Git branch name
            dir_path: Working directory path

        Returns:
            Registration result with environment_secret on success, None on failure
        """
        try:
            import uuid

            # In full implementation:
            # POST /v1/code/environments/{environment_id}/bridge
            # Headers: Authorization: Bearer <access_token>
            # Body: { worker_type, machine_name, git_repo_url, branch, dir }
            # Response: { environment_secret, ... }

            # For now, return mock result matching TS response shape
            environment_secret = f"sec_{uuid.uuid4().hex}"

            logger.info(
                "Registered bridge environment: env=%s worker=%s",
                environment_id,
                worker_type,
            )

            return {
                "environment_id": environment_id,
                "environment_secret": environment_secret,
            }
        except Exception as e:
            logger.error("Failed to register bridge environment: %s", e)
            return None

    async def reconnect_session(
        self,
        environment_id: str,
        session_id: str,
    ) -> bool:
        """Reconnect to an existing session.

        Args:
            environment_id: The environment ID
            session_id: The session ID to reconnect

        Returns:
            True if reconnection was successful
        """
        try:
            # In full implementation:
            # POST /v1/code/sessions/{session_id}/reconnect
            # Headers: Authorization: Bearer <access_token>
            # Body: { environment_id }

            logger.info(
                "Reconnected session: env=%s session=%s",
                environment_id,
                session_id,
            )
            return True
        except Exception as e:
            logger.error("Failed to reconnect session: %s", e)
            return False

    async def poll_for_work(
        self,
        environment_id: str,
        environment_secret: str,
        reclaim_older_than_ms: int | None = None,
    ) -> dict[str, Any] | None:
        """Poll for work items from the CCR.

        Args:
            environment_id: The environment ID
            environment_secret: The environment secret from registration
            reclaim_older_than_ms: Optional timeout for reclaiming stale work

        Returns:
            Work item dict if available, None otherwise.

        The response shape:
        {
            "id": "work_id",
            "type": "work",
            "environment_id": "env_id",
            "state": "pending",
            "data": { ... },
            "secret": "base64url_encoded_work_secret",
            "created_at": "2024-01-01T00:00:00Z"
        }
        """
        try:
            import base64
            import json
            import urllib.request

            url = f"{self.base_url}/v1/environments/{environment_id}/work/poll"
            if reclaim_older_than_ms is not None:
                url += f"?reclaim_older_than_ms={reclaim_older_than_ms}"

            headers = {
                "Authorization": f"Bearer {environment_secret}",
                "Accept": "application/json",
            }

            request = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read()
                if not data:
                    return None

                result = json.loads(data.decode("utf-8"))

                # Decode the work secret if present
                if result.get("secret"):
                    try:
                        result["_decoded_secret"] = json.loads(
                            base64.urlsafe_b64decode(
                                result["secret"] + "=="
                            ).decode("utf-8")
                        )
                    except Exception:
                        pass

                logger.debug(
                    "Poll returned work: id=%s type=%s",
                    result.get("id"),
                    result.get("type"),
                )
                return result

        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug("No work available (404)")
                return None
            logger.error("Poll HTTP error: %s %s", e.code, e.reason)
            return None
        except Exception as e:
            logger.error("Poll failed: %s", e)
            return None

    async def acknowledge_work(
        self,
        environment_id: str,
        work_id: str,
        session_token: str,
    ) -> bool:
        """Acknowledge a work item, claiming it for this bridge.

        Args:
            environment_id: The environment ID
            work_id: The work item ID to acknowledge
            session_token: The session ingress token from work secret

        Returns:
            True if acknowledged successfully
        """
        try:
            import json
            import urllib.request

            url = f"{self.base_url}/v1/environments/{environment_id}/work/{work_id}/ack"

            headers = {
                "Authorization": f"Bearer {session_token}",
                "Content-Type": "application/json",
            }

            request = urllib.request.Request(
                url,
                data=b"{}",
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                logger.info(
                    "Acknowledged work: env=%s work=%s status=%s",
                    environment_id,
                    work_id,
                    response.status,
                )
                return response.status == 200

        except Exception as e:
            logger.error("Acknowledge work failed: %s", e)
            return False

    async def stop_work(
        self,
        environment_id: str,
        work_id: str,
        environment_secret: str,
        force: bool = False,
    ) -> bool:
        """Stop/cancel a work item.

        Args:
            environment_id: The environment ID
            work_id: The work item ID to stop
            environment_secret: The environment secret
            force: If True, force stop without graceful shutdown

        Returns:
            True if stopped successfully
        """
        try:
            import urllib.request

            url = f"{self.base_url}/v1/environments/{environment_id}/work/{work_id}/stop"
            if force:
                url += "?force=true"

            headers = {
                "Authorization": f"Bearer {environment_secret}",
                "Content-Type": "application/json",
            }

            request = urllib.request.Request(
                url,
                data=b"",
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                logger.info(
                    "Stopped work: env=%s work=%s status=%s",
                    environment_id,
                    work_id,
                    response.status,
                )
                return response.status == 200

        except Exception as e:
            logger.error("Stop work failed: %s", e)
            return False


def build_session_git_context(
    git_repo_url: str | None,
    branch: str | None,
) -> dict[str, Any] | None:
    """Build git context for session creation.

    Args:
        git_repo_url: Git repository URL
        branch: Git branch name

    Returns:
        Git source/outcome context dict
    """
    if not git_repo_url and not branch:
        return None

    source = GitSource(
        type="git_repository",
        url=git_repo_url,
        revision=branch,
    )

    outcome = GitOutcome(
        type="git_repository",
        git_info={
            "url": git_repo_url,
            "branch": branch,
        },
    )

    return {
        "source": {"type": source.type, "url": source.url, "revision": source.revision},
        "outcome": {"type": outcome.type, "git_info": outcome.git_info},
    }
