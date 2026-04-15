"""Deep link utilities - parse and handle claude-cli:// URIs."""

from __future__ import annotations

from .parse_deep_link import (
    DeepLinkAction,
    DeepLinkProtocol,
    parse_deep_link,
    build_deep_link,
    DEEP_LINK_PROTOCOL,
)
from .register_protocol import (
    register_deep_link_protocol,
    unregister_deep_link_protocol,
)

__all__ = [
    "DeepLinkAction",
    "DeepLinkProtocol",
    "parse_deep_link",
    "build_deep_link",
    "DEEP_LINK_PROTOCOL",
    "register_deep_link_protocol",
    "unregister_deep_link_protocol",
]
