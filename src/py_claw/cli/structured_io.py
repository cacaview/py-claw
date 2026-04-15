from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from py_claw.schemas.control import (
    SDKControlCancelRequest,
    SDKControlRequest,
    SDKControlRequestEnvelope,
    SDKControlResponseEnvelope,
    SDKKeepAliveMessage,
    SDKUpdateEnvironmentVariablesMessage,
    StdinMessage,
    StdoutMessage,
)


class StructuredIOError(Exception):
    pass


class StructuredIOParseError(StructuredIOError):
    pass


class StructuredIORequestError(StructuredIOError):
    pass


class StructuredIORequestAborted(StructuredIORequestError):
    pass


@dataclass(slots=True)
class _PendingRequest:
    request: SDKControlRequestEnvelope
    response_adapter: TypeAdapter[Any] | None = None


class StructuredIO:
    def __init__(self, replay_user_messages: bool = False) -> None:
        self.replay_user_messages = replay_user_messages
        self._pending_requests: dict[str, _PendingRequest] = {}
        self._completed_responses: dict[str, Any] = {}
        self._failed_requests: dict[str, Exception] = {}
        self._prepended_lines: list[str] = []
        self._buffer = ""
        self._input_closed = False
        self._stdout_messages: list[StdoutMessage] = []
        self._stdin_adapter = TypeAdapter(StdinMessage)

    @property
    def pending_requests(self) -> dict[str, _PendingRequest]:
        return self._pending_requests

    @property
    def completed_responses(self) -> dict[str, Any]:
        return self._completed_responses

    @property
    def failed_requests(self) -> dict[str, Exception]:
        return self._failed_requests

    @property
    def stdout_messages(self) -> list[StdoutMessage]:
        return self._stdout_messages

    def prepend_user_message(self, content: str) -> None:
        self._prepended_lines.append(
            json.dumps(
                {
                    "type": "user",
                    "session_id": "",
                    "message": {"role": "user", "content": content},
                    "parent_tool_use_id": None,
                }
            )
            + "\n"
        )

    def feed_text(self, text: str) -> list[StdinMessage]:
        if self._input_closed:
            raise StructuredIORequestError("Stream closed")
        self._buffer += text
        return self._drain_buffer(final=False)

    def close_input(self) -> list[StdinMessage]:
        if self._input_closed:
            return []
        messages = self._drain_buffer(final=True)
        self._input_closed = True
        pending_request_ids = list(self._pending_requests.keys())
        for request_id in pending_request_ids:
            self._failed_requests[request_id] = StructuredIORequestError(
                "Tool permission stream closed before response received"
            )
            del self._pending_requests[request_id]
        return messages

    def iter_messages(self, chunks: Iterable[str]) -> Iterable[StdinMessage]:
        for chunk in chunks:
            for message in self.feed_text(chunk):
                yield message
        for message in self.close_input():
            yield message

    def _drain_buffer(self, *, final: bool) -> list[StdinMessage]:
        messages: list[StdinMessage] = []
        while True:
            if self._prepended_lines:
                self._buffer = "".join(self._prepended_lines) + self._buffer
                self._prepended_lines = []
            newline = self._buffer.find("\n")
            if newline == -1:
                break
            line = self._buffer[:newline]
            self._buffer = self._buffer[newline + 1 :]
            message = self.process_line(line)
            if message is not None:
                messages.append(message)
        if final and self._buffer:
            line = self._buffer
            self._buffer = ""
            message = self.process_line(line)
            if message is not None:
                messages.append(message)
        return messages

    def process_line(self, line: str) -> StdinMessage | None:
        if not line:
            return None
        try:
            parsed = json.loads(line)
            message = self._stdin_adapter.validate_python(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise StructuredIOParseError(f"Error parsing streaming input line: {line}") from exc

        if isinstance(message, SDKKeepAliveMessage):
            return None

        if isinstance(message, SDKUpdateEnvironmentVariablesMessage):
            os.environ.update(message.variables)
            return None

        if isinstance(message, SDKControlResponseEnvelope):
            request_id = message.response.request_id
            pending = self._pending_requests.get(request_id)
            if pending is None:
                return message if self.replay_user_messages else None
            del self._pending_requests[request_id]
            if message.response.subtype == "error":
                self._failed_requests[request_id] = StructuredIORequestError(message.response.error)
            else:
                result: Any = message.response.response if message.response.response is not None else {}
                if pending.response_adapter is not None:
                    try:
                        result = pending.response_adapter.validate_python(result)
                    except ValidationError as exc:
                        self._failed_requests[request_id] = exc
                    else:
                        self._completed_responses[request_id] = result
                else:
                    self._completed_responses[request_id] = result
            return message if self.replay_user_messages else None

        if isinstance(message, SDKControlRequestEnvelope):
            return message

        if getattr(message, "type", None) == "user":
            role = getattr(message.message, "get", None)
            if callable(role):
                role_value = message.message.get("role")
            elif isinstance(message.message, dict):
                role_value = message.message.get("role")
            else:
                role_value = None
            if role_value != "user":
                raise StructuredIOParseError(f"Error parsing streaming input line: {line}")
            return message

        return message

    def write(self, message: StdoutMessage) -> str:
        self._stdout_messages.append(message)
        if hasattr(message, "model_dump"):
            payload = message.model_dump(by_alias=True, exclude_none=True)
        else:
            payload = message
        return json.dumps(payload, separators=(",", ":")) + "\n"

    def send_request(
        self,
        request: SDKControlRequest,
        response_type: Any | None = None,
        request_id: str | None = None,
    ) -> SDKControlRequestEnvelope:
        if self._input_closed:
            raise StructuredIORequestError("Stream closed")
        actual_request_id = request_id or str(uuid4())
        envelope = SDKControlRequestEnvelope(
            type="control_request",
            request_id=actual_request_id,
            request=request,
        )
        adapter = TypeAdapter(response_type) if response_type is not None else None
        self._pending_requests[actual_request_id] = _PendingRequest(
            request=envelope,
            response_adapter=adapter,
        )
        self._stdout_messages.append(envelope)
        return envelope

    def cancel_request(self, request_id: str) -> SDKControlCancelRequest:
        if request_id not in self._pending_requests:
            raise StructuredIORequestError(f"Unknown request: {request_id}")
        del self._pending_requests[request_id]
        message = SDKControlCancelRequest(type="control_cancel_request", request_id=request_id)
        self._stdout_messages.append(message)
        return message

    def take_completed_response(self, request_id: str) -> Any:
        if request_id in self._failed_requests:
            raise self._failed_requests.pop(request_id)
        if request_id not in self._completed_responses:
            raise StructuredIORequestError(f"Unknown or incomplete request: {request_id}")
        return self._completed_responses.pop(request_id)


class WebSocketStructuredIO:
    """Structured I/O over WebSocket transport.

    This class provides the same interface as StructuredIO but communicates
    over a WebSocket connection instead of stdin/stdout. Used for remote
    CLI sessions where the client connects via WebSocket.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        replay_user_messages: bool = False,
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self.replay_user_messages = replay_user_messages
        self._pending_requests: dict[str, _PendingRequest] = {}
        self._completed_responses: dict[str, Any] = {}
        self._failed_requests: dict[str, Exception] = {}
        self._prepended_lines: list[str] = []
        self._input_closed = False
        self._stdout_messages: list[StdoutMessage] = []
        self._ws: Any = None
        self._receive_thread: Any = None
        self._stop_event: Any = None
        self._lock: Any = None

    @property
    def pending_requests(self) -> dict[str, _PendingRequest]:
        return self._pending_requests

    @property
    def completed_responses(self) -> dict[str, Any]:
        return self._completed_responses

    @property
    def failed_requests(self) -> dict[str, Exception]:
        return self._failed_requests

    @property
    def stdout_messages(self) -> list[StdoutMessage]:
        return self._stdout_messages

    def connect(self) -> None:
        """Establish WebSocket connection and start receive thread."""
        import threading
        import wsproto
        import wsproto.frame_protocol as fp
        from urllib.parse import urlparse

        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        parsed = urlparse(self.url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        use_tls = parsed.scheme in ("wss", "https")

        import socket
        import ssl

        # Create socket connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if use_tls:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
        sock.settimeout(30.0)
        sock.connect((host, port))

        # HTTP upgrade request
        request_lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Version: 13",
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
        ]
        for k, v in self.headers.items():
            if k.lower() not in ("host", "upgrade", "connection", "sec-websocket-version", "sec-websocket-key"):
                request_lines.append(f"{k}: {v}")
        request_lines.append("")
        request_lines.append("")

        http_request = "\r\n".join(request_lines).encode("utf-8")
        sock.sendall(http_request)

        # Read upgrade response
        response = b""
        while b"\r\n\r\n" not in response:
            response += sock.recv(4096)
        response_text = response.decode("utf-8", errors="replace")
        if "101" not in response_text:
            sock.close()
            raise StructuredIOError(f"WebSocket upgrade failed: {response_text[:200]}")

        # Store socket for later use
        self._sock = sock
        self._ws_conn = wsproto.WSConnection(wsproto.ConnectionType.CLIENT)

        # Start receive thread
        self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._receive_thread.start()

    def _receive_loop(self) -> None:
        """Background thread to receive WebSocket messages."""
        import wsproto.events as ws_events

        sock = self._sock
        ws_conn = self._ws_conn
        buffer = b""

        while not self._stop_event.is_set():
            try:
                sock.settimeout(0.5)
                chunk = sock.recv(8192)
                if not chunk:
                    break
                buffer += chunk

                ws_conn.receive_data(buffer)
                for event in ws_conn.events():
                    if isinstance(event, ws_events.Message):
                        text = event.data.decode("utf-8")
                        self._handle_message_text(text)
                    elif isinstance(event, ws_events.Close):
                        self._stop_event.set()
                        break
                buffer = b""
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_message_text(self, text: str) -> None:
        """Handle incoming WebSocket message text."""
        import json
        from py_claw.schemas.control import SDKControlResponseEnvelope, SDKControlCancelRequest

        if not text.strip():
            return

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return

        # Handle SDKControlResponseEnvelope
        if "type" in parsed and parsed["type"] == "control_response":
            request_id = parsed.get("response", {}).get("request_id")
            if request_id and request_id in self._pending_requests:
                del self._pending_requests[request_id]
                subtype = parsed.get("response", {}).get("subtype")
                if subtype == "error":
                    self._failed_requests[request_id] = StructuredIORequestError(
                        parsed.get("response", {}).get("error", "Unknown error")
                    )
                else:
                    self._completed_responses[request_id] = parsed.get("response", {}).get("response", {})
        # Handle SDKControlCancelRequest
        elif "type" in parsed and parsed["type"] == "control_cancel_request":
            request_id = parsed.get("request_id")
            if request_id and request_id in self._pending_requests:
                del self._pending_requests[request_id]
                self._failed_requests[request_id] = StructuredIORequestAborted(
                    "Request cancelled by server"
                )

    def close(self) -> None:
        """Close WebSocket connection."""
        if self._stop_event:
            self._stop_event.set()
        if self._receive_thread:
            self._receive_thread.join(timeout=2)
        if hasattr(self, "_sock") and self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def send_request(
        self,
        request: SDKControlRequest,
        response_type: Any | None = None,
        request_id: str | None = None,
    ) -> SDKControlRequestEnvelope:
        """Send a request over WebSocket."""
        if self._input_closed:
            raise StructuredIORequestError("Stream closed")

        import json
        actual_request_id = request_id or str(uuid4())
        envelope = SDKControlRequestEnvelope(
            type="control_request",
            request_id=actual_request_id,
            request=request,
        )

        adapter = TypeAdapter(response_type) if response_type is not None else None
        self._pending_requests[actual_request_id] = _PendingRequest(
            request=envelope,
            response_adapter=adapter,
        )

        # Serialize and send via WebSocket
        payload = json.dumps(envelope.model_dump(by_alias=True, exclude_none=True), separators=(",", ":"))
        self._send_text(payload)

        return envelope

    def _send_text(self, text: str) -> None:
        """Send text over WebSocket."""
        import wsproto
        ws_conn = self._ws_conn
        ws_conn.send_data(text.encode("utf-8"))
        if hasattr(self, "_sock") and self._sock:
            try:
                self._sock.sendall(ws_conn.bytes_to_send())
            except Exception:
                pass

    def cancel_request(self, request_id: str) -> SDKControlCancelRequest:
        """Cancel a pending request."""
        if request_id not in self._pending_requests:
            raise StructuredIORequestError(f"Unknown request: {request_id}")
        del self._pending_requests[request_id]
        message = SDKControlCancelRequest(type="control_cancel_request", request_id=request_id)
        self._send_text(json.dumps(message.model_dump(by_alias=True, exclude_none=True), separators=(",", ":")))
        return message

    def take_completed_response(self, request_id: str) -> Any:
        """Get completed response for a request."""
        if request_id in self._failed_requests:
            raise self._failed_requests.pop(request_id)
        if request_id not in self._completed_responses:
            raise StructuredIORequestError(f"Unknown or incomplete request: {request_id}")
        return self._completed_responses.pop(request_id)


# ---------------------------------------------------------------------------
# SSE Frame Parser
# ---------------------------------------------------------------------------


class SSEFrame:
    """Represents a parsed SSE frame."""

    __slots__ = ("event", "id", "data")

    def __init__(
        self,
        event: str | None = None,
        id: str | None = None,
        data: str | None = None,
    ) -> None:
        self.event = event
        self.id = id
        self.data = data


def parse_sse_frames(buffer: str) -> tuple[list[SSEFrame], str]:
    """Incrementally parse SSE frames from a text buffer.

    Returns parsed frames and the remaining (incomplete) buffer.
    """
    frames: list[SSEFrame] = []
    pos = 0

    while True:
        idx = buffer.find("\n\n", pos)
        if idx == -1:
            break
        raw_frame = buffer[pos:idx]
        pos = idx + 2

        if not raw_frame.strip():
            continue

        frame = SSEFrame()
        is_comment = False

        for line in raw_frame.split("\n"):
            if line.startswith(":"):
                is_comment = True
                continue

            colon_idx = line.index(":")
            if colon_idx == -1:
                continue

            field = line[:colon_idx]
            value = line[colon_idx + 2:] if line[colon_idx + 1] == " " else line[colon_idx + 1:]

            if field == "event":
                frame.event = value
            elif field == "id":
                frame.id = value
            elif field == "data":
                frame.data = (frame.data + "\n" + value) if frame.data else value

        if frame.data or is_comment:
            frames.append(frame)

    return frames, buffer[pos:]


# ---------------------------------------------------------------------------
# SSE Transport
# ---------------------------------------------------------------------------

_RECONNECT_BASE_DELAY_MS = 1000
_RECONNECT_MAX_DELAY_MS = 30_000
_RECONNECT_GIVE_UP_MS = 600_000
_LIVENESS_TIMEOUT_MS = 45_000
_PERMANENT_HTTP_CODES = {401, 403, 404}
_POST_MAX_RETRIES = 10
_POST_BASE_DELAY_MS = 500
_POST_MAX_DELAY_MS = 8000


class SSETransport:
    """Transport that uses SSE for reading and HTTP POST for writing.

    Reads events via Server-Sent Events from the CCR v2 event stream endpoint.
    Writes events via HTTP POST with retry logic.

    Supports automatic reconnection with exponential backoff and Last-Event-ID
    for resumption after disconnection.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        session_id: str | None = None,
        refresh_headers: callable | None = None,
        initial_sequence_num: int | None = None,
        get_auth_headers: callable | None = None,
    ) -> None:
        self._url = url
        self._headers = dict(headers) if headers else {}
        self._session_id = session_id
        self._refresh_headers = refresh_headers
        self._get_auth_headers = get_auth_headers or self._default_auth_headers
        self._state = "idle"
        self._last_sequence_num = initial_sequence_num or 0
        self._seen_sequence_nums: set[int] = set()
        self._reconnect_attempts = 0
        self._reconnect_start_time: float | None = None
        self._reconnect_timer: threading.Timer | None = None
        self._liveness_timer: threading.Timer | None = None
        self._stop_event = threading.Event()
        self._receive_thread: threading.Thread | None = None
        self._abort_controller: threading.Event | None = None
        self._lock = threading.Lock()

        self._pending_requests: dict[str, _PendingRequest] = {}
        self._completed_responses: dict[str, Any] = {}
        self._failed_requests: dict[str, Exception] = {}
        self._stdout_messages: list[StdoutMessage] = []

        self._on_data: callable | None = None
        self._on_close: callable | None = None
        self._on_event: callable | None = None
        self._response: Any = None

        self._post_url = self._convert_sse_url_to_post_url(url)

    @staticmethod
    def _default_auth_headers() -> dict[str, str]:
        return {}

    @staticmethod
    def _convert_sse_url_to_post_url(sse_url: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(sse_url)
        path = parsed.path
        if path.endswith("/stream"):
            path = path[: -len("/stream")]
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    @property
    def pending_requests(self) -> dict[str, _PendingRequest]:
        return self._pending_requests

    @property
    def completed_responses(self) -> dict[str, Any]:
        return self._completed_responses

    @property
    def failed_requests(self) -> dict[str, Exception]:
        return self._failed_requests

    @property
    def stdout_messages(self) -> list[StdoutMessage]:
        return self._stdout_messages

    def get_last_sequence_num(self) -> int:
        return self._last_sequence_num

    def connect(self) -> None:
        import urllib.request
        from urllib.parse import urlparse, ParseResult

        with self._lock:
            if self._state not in ("idle", "reconnecting"):
                return
            self._state = "reconnecting"

        self._stop_event.clear()
        self._abort_controller = threading.Event()

        parsed_url = urlparse(self._url)
        query_parts = []
        if parsed_url.query:
            query_parts.append(parsed_url.query)
        if self._last_sequence_num > 0:
            query_parts.append(f"from_sequence_num={self._last_sequence_num}")
        new_query = "&".join(query_parts) if query_parts else None
        sse_url = ParseResult(
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment,
        ).geturl()

        auth_headers = self._get_auth_headers()
        headers = {**self._headers, **auth_headers}
        headers["Accept"] = "text/event-stream"
        headers["anthropic-version"] = "2023-06-01"
        if self._last_sequence_num > 0:
            headers["Last-Event-ID"] = str(self._last_sequence_num)

        try:
            req = urllib.request.Request(sse_url, headers=headers)
            self._response = urllib.request.urlopen(req, timeout=30.0)
            self._state = "connected"
            self._reconnect_attempts = 0
            self._reconnect_start_time = None
            self._reset_liveness_timer()
            self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receive_thread.start()
        except urllib.error.HTTPError as e:
            if e.code in _PERMANENT_HTTP_CODES:
                self._state = "closed"
                self._on_close_callback()
                return
            self._handle_connection_error()
        except Exception:
            self._handle_connection_error()

    def _receive_loop(self) -> None:
        import json
        buffer = ""

        while not self._stop_event.is_set():
            if self._abort_controller and self._abort_controller.is_set():
                break
            try:
                chunk = self._response.read(8192)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                frames, buffer = parse_sse_frames(buffer)
                for frame in frames:
                    self._reset_liveness_timer()
                    if frame.id:
                        try:
                            seq_num = int(frame.id)
                            if seq_num not in self._seen_sequence_nums:
                                self._seen_sequence_nums.add(seq_num)
                                if len(self._seen_sequence_nums) > 1000:
                                    threshold = self._last_sequence_num - 200
                                    self._seen_sequence_nums = {
                                        s for s in self._seen_sequence_nums if s >= threshold
                                    }
                            if seq_num > self._last_sequence_num:
                                self._last_sequence_num = seq_num
                        except ValueError:
                            pass
                    if frame.event and frame.data:
                        self._handle_sse_frame(frame.event, frame.data)
                    elif frame.data:
                        pass
            except Exception:
                if self._stop_event.is_set() or (self._abort_controller and self._abort_controller.is_set()):
                    break
                break

        if self._state not in ("closing", "closed"):
            self._handle_connection_error()

    def _handle_sse_frame(self, event_type: str, data: str) -> None:
        import json
        if event_type != "client_event":
            return
        try:
            ev = json.loads(data)
        except json.JSONDecodeError:
            return
        payload = ev.get("payload")
        if payload and isinstance(payload, dict) and "type" in payload:
            self._on_data(json.dumps(payload) + "\n")
        self._on_event_callback(ev)

    def _handle_connection_error(self) -> None:
        import time
        self._clear_liveness_timer()
        if self._state in ("closing", "closed"):
            return
        if self._abort_controller:
            self._abort_controller.set()
            self._abort_controller = None
        now = time.monotonic()
        if self._reconnect_start_time is None:
            self._reconnect_start_time = now
        elapsed_ms = (now - self._reconnect_start_time) * 1000
        if elapsed_ms < _RECONNECT_GIVE_UP_MS:
            if self._reconnect_timer:
                self._reconnect_timer.cancel()
            if self._refresh_headers:
                fresh = self._refresh_headers()
                self._headers.update(fresh)
            self._state = "reconnecting"
            self._reconnect_attempts += 1
            base_delay = min(
                _RECONNECT_BASE_DELAY_MS * (2 ** (self._reconnect_attempts - 1)),
                _RECONNECT_MAX_DELAY_MS,
            )
            delay = base_delay + base_delay * 0.25 * (2 * __import__("random").random() - 1)
            delay = max(0, delay)
            self._reconnect_timer = threading.Timer(delay / 1000, self._do_reconnect)
            self._reconnect_timer.start()
        else:
            self._state = "closed"
            self._on_close_callback()

    def _do_reconnect(self) -> None:
        self.connect()

    def _on_close_callback(self) -> None:
        if self._on_close:
            self._on_close()

    def _on_data(self, data: str) -> None:
        import json
        if not data.strip():
            return
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return
        if "type" in parsed and parsed["type"] == "control_response":
            request_id = parsed.get("response", {}).get("request_id")
            if request_id and request_id in self._pending_requests:
                del self._pending_requests[request_id]
                subtype = parsed.get("response", {}).get("subtype")
                if subtype == "error":
                    self._failed_requests[request_id] = StructuredIORequestError(
                        parsed.get("response", {}).get("error", "Unknown error")
                    )
                else:
                    self._completed_responses[request_id] = parsed.get("response", {}).get("response", {})
        elif "type" in parsed and parsed["type"] == "control_cancel_request":
            request_id = parsed.get("request_id")
            if request_id and request_id in self._pending_requests:
                del self._pending_requests[request_id]
                self._failed_requests[request_id] = StructuredIORequestAborted(
                    "Request cancelled by server"
                )

    def _on_event_callback(self, ev: Any) -> None:
        if self._on_event:
            self._on_event(ev)

    def _reset_liveness_timer(self) -> None:
        self._clear_liveness_timer()
        self._liveness_timer = threading.Timer(_LIVENESS_TIMEOUT_MS / 1000, self._on_liveness_timeout)
        self._liveness_timer.start()

    def _clear_liveness_timer(self) -> None:
        if self._liveness_timer:
            self._liveness_timer.cancel()
            self._liveness_timer = None

    def _on_liveness_timeout(self) -> None:
        self._liveness_timer = None
        if self._abort_controller:
            self._abort_controller.set()
        self._handle_connection_error()

    def send_request(
        self,
        request: SDKControlRequest,
        response_type: Any | None = None,
        request_id: str | None = None,
    ) -> SDKControlRequestEnvelope:
        if self._state == "closed":
            raise StructuredIORequestError("Stream closed")
        actual_request_id = request_id or str(uuid4())
        envelope = SDKControlRequestEnvelope(
            type="control_request",
            request_id=actual_request_id,
            request=request,
        )
        adapter = TypeAdapter(response_type) if response_type is not None else None
        self._pending_requests[actual_request_id] = _PendingRequest(
            request=envelope,
            response_adapter=adapter,
        )
        payload = json.dumps(envelope.model_dump(by_alias=True, exclude_none=True), separators=(",", ":"))
        self._post(payload)
        return envelope

    def _post(self, body: str) -> None:
        import time
        import urllib.error
        import urllib.request
        auth_headers = self._get_auth_headers()
        headers = {
            **auth_headers,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        for attempt in range(1, _POST_MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    self._post_url,
                    data=body.encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                response = urllib.request.urlopen(req, timeout=30.0)
                if response.status in (200, 201):
                    return
                if 400 <= response.status < 500 and response.status != 429:
                    return
            except urllib.error.HTTPError:
                pass
            except Exception:
                pass
            if attempt == _POST_MAX_RETRIES:
                return
            delay_ms = min(_POST_BASE_DELAY_MS * (2 ** (attempt - 1)), _POST_MAX_DELAY_MS)
            time.sleep(delay_ms / 1000)

    def cancel_request(self, request_id: str) -> SDKControlCancelRequest:
        if request_id not in self._pending_requests:
            raise StructuredIORequestError(f"Unknown request: {request_id}")
        del self._pending_requests[request_id]
        message = SDKControlCancelRequest(type="control_cancel_request", request_id=request_id)
        self._post(json.dumps(message.model_dump(by_alias=True, exclude_none=True), separators=(",", ":")))
        return message

    def take_completed_response(self, request_id: str) -> Any:
        if request_id in self._failed_requests:
            raise self._failed_requests.pop(request_id)
        if request_id not in self._completed_responses:
            raise StructuredIORequestError(f"Unknown or incomplete request: {request_id}")
        return self._completed_responses.pop(request_id)

    def close(self) -> None:
        self._state = "closing"
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
        self._clear_liveness_timer()
        self._stop_event.set()
        if self._abort_controller:
            self._abort_controller.set()
        if self._receive_thread:
            self._receive_thread.join(timeout=2)
        self._state = "closed"

    def set_on_data(self, callback: callable) -> None:
        self._on_data = callback

    def set_on_close(self, callback: callable) -> None:
        self._on_close = callback

    def set_on_event(self, callback: callable) -> None:
        self._on_event = callback
