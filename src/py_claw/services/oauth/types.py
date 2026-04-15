from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OAuthTokens:
    """OAuth tokens received from the token endpoint."""
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: float | None = None
    scope: str | None = None
    token_type: str | None = None
    expires_in: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if the access token is expired."""
        if self.expires_at is None:
            return False
        import time
        return time.time() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            **self.extra,
        }


@dataclass
class OAuthProfile:
    """OAuth user profile information."""
    raw: dict[str, Any] = field(default_factory=dict)
    subscription_type: str | None = None
    rate_limit_tier: str | None = None

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> OAuthProfile:
        return cls(
            raw=data,
            subscription_type=data.get("subscription_type"),
            rate_limit_tier=data.get("rate_limit_tier"),
        )


OAuthTokenExchangeResponse = dict[str, Any]
