from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OAuthConfig:
    """OAuth configuration for Anthropic services."""
    client_id: str
    authorize_url: str
    token_url: str
    manual_redirect_url: str
    claude_ai_origin: str

    @classmethod
    def production(cls) -> OAuthConfig:
        return cls(
            client_id="9d1c250a-e61b-44d9-88ed-5944d1962f5e",
            authorize_url="https://platform.claude.com/oauth/authorize",
            token_url="https://platform.claude.com/v1/oauth/token",
            manual_redirect_url="https://platform.claude.com/oauth/code/callback",
            claude_ai_origin="https://claude.ai",
        )

    @classmethod
    def staging(cls) -> OAuthConfig:
        return cls(
            client_id="22422756-60c9-4084-8eb7-27705fd5cf9a",
            authorize_url="https://platform.staging.ant.dev/oauth/authorize",
            token_url="https://platform.staging.ant.dev/v1/oauth/token",
            manual_redirect_url="https://platform.staging.ant.dev/oauth/code/callback",
            claude_ai_origin="https://claude-ai.staging.ant.dev",
        )

    @classmethod
    def from_env(cls) -> OAuthConfig:
        """Detect config from environment variables."""
        if os.environ.get("CLAUDE_CODE_OAUTH_CLIENT_ID"):
            # Custom client ID means use production
            return cls.production()
        if os.environ.get("ANTHROPIC_USE_STAGING"):
            return cls.staging()
        return cls.production()


def get_oauth_config() -> OAuthConfig:
    """Get the current OAuth configuration."""
    return OAuthConfig.from_env()
