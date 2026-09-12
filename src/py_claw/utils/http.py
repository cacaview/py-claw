"""Shared urllib helpers.

py-claw talks to user-configured endpoints and to local test/dev servers;
neither should ever be silently routed through a system proxy.
"""

from __future__ import annotations

import urllib.request
from urllib.request import Request
from urllib.parse import urlparse


def open_url(request: Request, *, timeout: float):
    """Open a URL, never proxying loopback traffic.

    macOS system proxies commonly list ``localhost`` but not ``127.0.0.1`` in
    their exceptions, so urllib silently routes loopback requests into the
    proxy and fails with "connection closed". Loopback never needs a proxy.
    """
    host = (urlparse(request.full_url).hostname or "").lower()
    is_loopback = host in ("localhost", "::1") or host.startswith("127.")
    if is_loopback:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)
