from __future__ import annotations

import http.server
import json
import socket
import threading
from urllib.parse import parse_qs, urlparse


class AuthCodeListener:
    """Local HTTP server to listen for OAuth callback with authorization code.

    Opens a temporary HTTP server on a random available port and waits
    for the OAuth provider to redirect with the authorization code.
    """

    def __init__(self) -> None:
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._authorization_code: str | None = None
        self._state: str | None = None
        self._error: str | None = None
        self._ready_event = threading.Event()
        self._port: int | None = None
        self._local_only: bool = True

    def start(self) -> int:
        """Start the HTTP server on a random available port.

        Returns the port number.
        """
        self._server = _AuthHandler.create_server(self._handle_request)
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self._port

    def _handle_request(self, state: str, code: str | None, error: str | None) -> None:
        """Called when the OAuth callback is received."""
        self._state = state
        self._authorization_code = code
        self._error = error
        # Server the success/error page and shutdown
        if self._server:
            threading.Thread(target=self._server.shutdown, daemon=True).start()

    def wait_for_callback(self, state: str) -> str:
        """Wait for the OAuth callback and return the authorization code.

        Raises ValueError if state doesn't match or error occurred.
        """
        # Poll for the authorization code (set by the HTTP handler)
        import time
        for _ in range(300):  # 30 seconds timeout
            if self._authorization_code:
                if self._state != state:
                    raise ValueError("State mismatch in OAuth callback")
                return self._authorization_code
            if self._error:
                raise ValueError(f"OAuth error: {self._error}")
            time.sleep(0.1)

        raise TimeoutError("OAuth callback timeout")

    def close(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None


class _AuthHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""

    _instance: AuthCodeListener | None = None
    _server_state: str | None = None
    _callback_called: bool = False

    @classmethod
    def create_server(cls, callback) -> http.server.HTTPServer:
        """Create an HTTP server bound to localhost on an available port."""

        def handler_factory(callback):
            class _Factory(cls):
                _callback = callback
            return _Factory

        # Find an available port on localhost
        for port in range(19200, 19300):
            try:
                server = http.server.HTTPServer(("127.0.0.1", port), handler_factory(callback))
                # Store reference on the server instance for access from handler
                server._auth_callback = callback  # type: ignore
                server._auth_state = None  # type: ignore
                server._auth_code_received = threading.Event()  # type: ignore
                server._auth_code = None  # type: ignore
                server._auth_error = None  # type: ignore
                return server
            except OSError:
                continue
        raise RuntimeError("Could not find available port for OAuth callback")

    def do_GET(self) -> None:
        """Handle GET request (OAuth callback)."""
        if not hasattr(self.server, "_auth_callback"):
            self.send_error(500)
            return

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        state = params.get("state", [None])[0]
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        # Store on server instance
        self.server._auth_state = state
        self.server._auth_code = code
        self.server._auth_error = error

        # Call the callback
        self.server._auth_callback(state, code, error)

        # Send simple HTML response
        if error:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authentication Failed</h1></body></html>")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Authentication Successful</h1><p>You can close this window.</p></body></html>")

    def log_message(self, format: str, *args) -> None:
        """Suppress log messages."""
        pass


def find_available_port(host: str = "127.0.0.1", start: int = 19200, end: int = 19300) -> int:
    """Find an available port in the given range."""
    for port in range(start, end):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((host, port))
            sock.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"No available port in range {start}-{end}")
