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
