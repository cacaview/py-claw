"""Notifier service - terminal notification system with auto-detect."""
from __future__ import annotations

from .service import (
    NotifierService,
    get_notifier_service,
    notify,
    send_notification,
)
from .terminals import (
    BellBackend,
    GhosttyBackend,
    ITerm2Backend,
    ITerm2WithBellBackend,
    KittyBackend,
    get_backend,
)
from .types import (
    DEFAULT_NOTIFICATION_TITLE,
    NotificationChannel,
    NotificationOptions,
)

__all__ = [
    "NotifierService",
    "NotificationOptions",
    "NotificationChannel",
    "DEFAULT_NOTIFICATION_TITLE",
    "get_notifier_service",
    "send_notification",
    "notify",
    # Terminal backends
    "get_backend",
    "ITerm2Backend",
    "ITerm2WithBellBackend",
    "KittyBackend",
    "GhosttyBackend",
    "BellBackend",
]
