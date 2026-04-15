from __future__ import annotations

import base64
import hashlib
import os


def _base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string (no padding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_code_verifier() -> str:
    """Generate a random PKCE code verifier (43-128 chars, unreserved URI chars)."""
    # Use 32 random bytes encoded as base64url (43 chars without padding)
    return _base64url_encode(os.urandom(32))


def generate_code_challenge(verifier: str) -> str:
    """Generate PKCE code challenge from verifier using S256 method."""
    # SHA256 hash of the verifier, then base64url encode
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _base64url_encode(digest)


def generate_state() -> str:
    """Generate a random state parameter for OAuth CSRF protection."""
    return _base64url_encode(os.urandom(32))
