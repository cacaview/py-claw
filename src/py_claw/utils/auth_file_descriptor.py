"""
Auth file descriptor helpers.

File descriptor based authentication for platform-specific
file handle operations.

Mirrors TS authFileDescriptor.ts behavior.
"""
from __future__ import annotations

import os
import sys


def is_file_descriptor_auth_supported() -> bool:
    """
    Check if file descriptor-based auth is supported on this platform.

    Returns:
        True if file descriptors can be used for auth
    """
    # Supported on Unix-like systems
    return sys.platform not in ("win32",)


def get_auth_file_descriptor(fd: int) -> int | None:
    """
    Get a file descriptor for authentication.

    Args:
        fd: File descriptor number

    Returns:
        File descriptor or None if not supported/invalid
    """
    if not is_file_descriptor_auth_supported():
        return None

    try:
        # Validate the fd is a valid file descriptor
        os.fstat(fd)
        return fd
    except (OSError, ValueError):
        return None
