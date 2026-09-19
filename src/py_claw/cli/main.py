from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any, Sequence, TextIO

from py_claw import __version__
from py_claw.cli.control import ControlRuntime
from py_claw.cli.runtime import HostPermissionChannel, RuntimeState
from py_claw.cli.structured_io import StructuredIO, StructuredIOError
from py_claw.config import load_config
from py_claw.query import QueryRuntime, SdkUrlQueryBackend
from py_claw.query.backend import ApiQueryBackend
from py_claw.schemas.control import (
    SDKControlPermissionRequest,
    SDKControlRequestEnvelope,
    SDKControlResponseEnvelope,
)
from py_claw.schemas.common import SDKUserMessage
from py_claw.ui.textual_app import run_textual_ui


def _configure_logging() -> None:
    """Configure root logger to emit warnings to stderr."""
    root = logging.getLogger()
    if root.level == logging.NOTSET and not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="py-claw", description="Python port of Claude Code")
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    parser.add_argument("--print", dest="print_mode", action="store_true", help="Run in print mode")
    parser.add_argument("--tui", action="store_true", help="Run the Textual terminal UI")
    parser.add_argument("--input-format", choices=["text", "stream-json"], default="text")
    parser.add_argument("--output-format", choices=["text", "json", "stream-json"], default="text")
    parser.add_argument(
        "--sdk-url",
        help=(
            "URL of a Claude SDK backend to use for queries (enables real model inference instead of "
            "placeholder). If not set, ANTHROPIC_API_KEY environment variable is checked."
        ),
    )
    parser.add_argument("--include-partial-messages", action="store_true")
    parser.add_argument("prompt", nargs="?")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.input_format == "stream-json" and args.output_format != "stream-json":
        raise SystemExit("--input-format=stream-json requires --output-format=stream-json")
    if args.sdk_url and not (args.input_format == "stream-json" and args.output_format == "stream-json"):
        raise SystemExit("--sdk-url requires both --input-format=stream-json and --output-format=stream-json")
    if args.include_partial_messages and not (args.print_mode and args.output_format == "stream-json"):
        raise SystemExit("--include-partial-messages requires --print with --output-format=stream-json")


def _build_state(args: argparse.Namespace) -> RuntimeState:
    state = RuntimeState(include_partial_messages=args.include_partial_messages)
    if args.sdk_url:
        state.query_backend = SdkUrlQueryBackend(args.sdk_url)
    else:
        cfg = load_config()
        if cfg.api.is_configured():
            state.model = cfg.api.model or None
            # Get tool definitions from tool_runtime
            tool_defs: list[tuple[str, type] | None] = []
            if state.tool_runtime and state.tool_runtime.registry:
                for tool in state.tool_runtime.registry.values():
                    tool_defs.append((tool.definition.name, tool.definition.input_model))
            tool_defs = [d for d in tool_defs if d is not None]

            if cfg.api.protocol == "anthropic":
                from py_claw.query.backend import AnthropicQueryBackend, tool_definitions_to_anthropic_tools

                state.query_backend = AnthropicQueryBackend(
                    api_key=cfg.api.api_key,
                    model=cfg.api.model,
                    tools=tool_definitions_to_anthropic_tools(tool_defs) if tool_defs else None,
                    base_url=cfg.api.api_url or None,
                )
            else:
                # Convert to OpenAI tools format
                from py_claw.query.backend import tool_definitions_to_openai_tools
                tools = tool_definitions_to_openai_tools(tool_defs) if tool_defs else None

                state.query_backend = ApiQueryBackend(
                    api_key=cfg.api.api_key,
                    api_url=cfg.api.api_url,
                    model=cfg.api.model,
                    tools=tools,
                    temperature=cfg.api.temperature,
                    top_p=cfg.api.top_p,
                    timeout_seconds=cfg.api.timeout_seconds,
                )
    return state


def _read_print_prompt(args: argparse.Namespace, stdin: TextIO) -> str:
    """Prompt for --print: the positional arg, else piped stdin text."""
    if args.prompt:
        return args.prompt
    try:
        if not stdin.isatty():
            piped = stdin.read()
            if piped.strip():
                return piped
    except Exception:
        pass
    return ""


def _run_print_mode(args: argparse.Namespace, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    """One-shot print mode: run a single turn and emit the result."""
    state = _build_state(args)
    if state.query_backend is None:
        stderr.write(
            "py-claw: no API backend configured.\n"
            "Set ~/.config/py-claw/config.json with api.api_key / api.api_url / api.model.\n"
        )
        return 2

    prompt = _read_print_prompt(args, stdin)
    if not prompt.strip():
        stderr.write("py-claw: --print requires a prompt (argument or piped stdin).\n")
        return 2

    query_runtime = QueryRuntime(state)
    message = SDKUserMessage(type="user", message={"role": "user", "content": prompt}, parent_tool_use_id=None)

    exit_code = 0
    for outbound in query_runtime.handle_user_message(message):
        outbound_type = getattr(outbound, "type", None)
        if outbound_type == "assistant":
            content = getattr(getattr(outbound, "message", None), "get", lambda _k: None)("content")
            if args.output_format == "text" and isinstance(content, str) and content.strip():
                stdout.write(content if content.endswith("\n") else content + "\n")
                stdout.flush()
        elif outbound_type == "result":
            payload = outbound.model_dump(by_alias=True, exclude_none=True)
            if args.output_format == "json":
                stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
                stdout.flush()
            elif payload.get("is_error"):
                errors = payload.get("errors") or []
                stderr.write("; ".join(str(e) for e in errors) + "\n")
            if payload.get("is_error"):
                exit_code = 1
    return exit_code


def _write_control_response(
    structured_io: StructuredIO,
    stdout: TextIO,
    request_id: str,
    response: dict | None = None,
    error: str | None = None,
) -> None:
    payload = {
        "type": "control_response",
        "response": (
            {"subtype": "error", "request_id": request_id, "error": error or "Unknown error"}
            if error is not None
            else {"subtype": "success", "request_id": request_id, "response": response}
        ),
    }
    stdout.write(structured_io.write(SDKControlResponseEnvelope.model_validate(payload)))
    stdout.flush()


def _run_stream_json(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    structured_io = StructuredIO()
    state = _build_state(args)
    control_runtime = ControlRuntime(state)
    query_runtime = QueryRuntime(state)

    # A stream-json host is the only non-TUI surface that can answer
    # ``can_use_tool`` control requests, so the query engine's ask path is
    # gated on installing this channel. Print mode and the TUI leave it None.
    state.host_permission_channel = _StreamJsonPermissionChannel(structured_io, stdin, stdout)
    if args.prompt:
        structured_io.prepend_user_message(args.prompt)

    try:
        for message in structured_io.iter_messages(stdin):
            if isinstance(message, SDKControlRequestEnvelope):
                try:
                    response = control_runtime.handle_request(message.request)
                except StructuredIOError as exc:
                    _write_control_response(
                        structured_io,
                        stdout,
                        request_id=message.request_id,
                        error=str(exc),
                    )
                else:
                    _write_control_response(
                        structured_io,
                        stdout,
                        request_id=message.request_id,
                        response=response,
                    )
                continue

            if getattr(message, "type", None) != "user":
                continue

            for outbound in query_runtime.handle_user_message(message):
                stdout.write(structured_io.write(outbound))
                stdout.flush()
    finally:
        # iter_messages drains stdin to EOF; mark the stream closed so a
        # can_use_tool request still in flight while the host disconnects
        # fails fast instead of a blocked read() against a closed stdin.
        structured_io.close_input()
        state.host_permission_channel = None
        state.query_runtime = None
    return 0


class _HostPermissionResponse:
    """Host permission response carrying the fields the engine inspects."""

    def __init__(
        self,
        behavior: str | None = None,
        updated_input: dict[str, Any] | None = None,
        deny_message: str | None = None,
    ) -> None:
        self.behavior = behavior
        self.updatedInput = updated_input
        self.message = deny_message


class _StreamJsonPermissionChannel:
    """Host-side ``can_use_tool`` request/response channel over stdin/stdout.

    ``send`` writes the control request through ``StructuredIO.send_request``
    — the same request_id round-trip used by every other stream-json request —
    and flushes it to ``stdout``. ``wait`` blocks reading the host's
    ``control_response`` line directly from the stream; because the engine runs
    synchronously inside the main message loop, this is safe and the pending
    request is still open while we block.
    """

    _RECV_CHUNK = 65536

    def __init__(self, structured_io: StructuredIO, stdin: TextIO, stdout: TextIO) -> None:
        self._structured_io = structured_io
        self._stdin = stdin
        self._stdout = stdout
        self._pending_request_id: str | None = None
        self._stdin_buffer = ""

    def send(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        *,
        request_id: str | None = None,
    ) -> None:
        request = SDKControlPermissionRequest(
            subtype="can_use_tool",
            tool_name=tool_name,
            input=tool_input,
            tool_use_id=tool_use_id,
        )
        envelope = self._structured_io.send_request(request, request_id=request_id)
        self._pending_request_id = envelope.request_id
        self._flush_stdout()

    def wait(self, timeout: float) -> _HostPermissionResponse | None:
        request_id = self._pending_request_id
        if request_id is None:
            return None
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() >= deadline:
                # Timeout: the host never answered, fail closed.
                return None
            line = self._read_line()
            if line is None:
                # Host closed the stream before answering: fail closed.
                return None
            if not line:
                continue
            line = self._substitute_request_id(line)
            try:
                message = self._structured_io.process_line(line)
            except StructuredIOError:
                # Malformed line: the host will send a well-formed response
                # (or not); keep waiting.
                continue
            # A control response addressed to our request is consumed by
            # process_line (it pops the pending entry, returns None) — the
            # absence of our pending entry is the signal that the answer
            # arrived. A response for a DIFFERENT request passes through
            # untouched (still pending) and is left for the main loop.
            if message is None and request_id not in self._structured_io._pending_requests:
                return self._decode_response(request_id)

    def _decode_response(self, request_id: str) -> _HostPermissionResponse | None:
        try:
            result = self._structured_io.take_completed_response(request_id)
        except StructuredIOError as exc:
            # Error subtype: treat as a deny that carries the host's message.
            return _HostPermissionResponse(deny_message=str(exc))
        if not isinstance(result, dict):
            return None
        return _HostPermissionResponse(
            behavior=result.get("behavior"),
            updated_input=result.get("updatedInput"),
            deny_message=result.get("message"),
        )

    def _read_line(self) -> str | None:
        """Read one line from the host stream; None on EOF/close."""
        while True:
            if "\n" in self._stdin_buffer:
                line, self._stdin_buffer = self._stdin_buffer.split("\n", 1)
                return line
            try:
                chunk = self._stdin.read(self._RECV_CHUNK)
            except Exception:
                return None
            if not chunk:
                return None
            self._stdin_buffer += chunk

    def _substitute_request_id(self, line: str) -> str:
        """Replace a ``__PENDING__`` request_id placeholder in a host
        control-response line with the id of the request we actually sent.

        Hosts that cannot read our emitted request id (e.g. tests feeding a
        canned response) signal the round-trip with ``"request_id":
        "__PENDING__"``; the single in-flight request makes the substitution
        unambiguous.
        """
        if self._pending_request_id and '"__PENDING__"' in line:
            return line.replace('"__PENDING__"', f'"{self._pending_request_id}"')
        return line

    def _flush_stdout(self) -> None:
        # ``send_request`` already queued the envelope; ``write`` would queue it
        # again, so iterate a snapshot and use the raw serialization to avoid
        # the list growing while it is being traversed.
        messages = list(self._structured_io.stdout_messages)
        for envelope in messages:
            import json as _json

            if hasattr(envelope, "model_dump"):
                payload = envelope.model_dump(by_alias=True, exclude_none=True)
            else:
                payload = envelope
            self._stdout.write(_json.dumps(payload, separators=(",", ":")) + "\n")
        self._stdout.flush()


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    out_stream = stdout or sys.stdout
    in_stream = stdin or sys.stdin
    if args.version:
        print(__version__, file=out_stream)
        return 0
    validate_args(args)
    _configure_logging()
    if args.tui:
        state = _build_state(args)
        return run_textual_ui(state, QueryRuntime(state), prompt=args.prompt)
    if args.input_format == "stream-json" and args.output_format == "stream-json":
        return _run_stream_json(args, in_stream, out_stream)
    if args.print_mode or (args.output_format in ("text", "json") and args.prompt):
        return _run_print_mode(args, in_stream, out_stream, sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
