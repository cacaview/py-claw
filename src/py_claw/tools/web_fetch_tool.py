from __future__ import annotations

import time
from html.parser import HTMLParser
from http import HTTPStatus
from typing import Any
from urllib import error, parse, request

from pydantic import BaseModel, field_validator

from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

_MAX_RESULT_CHARS = 100_000


class WebFetchToolInput(BaseModel):
    url: str
    prompt: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be a valid http or https URL")
        return value


class _CrossHostRedirectError(Exception):
    def __init__(self, original_url: str, redirect_url: str, status_code: int) -> None:
        super().__init__(f"Cross-host redirect from {original_url} to {redirect_url}")
        self.original_url = original_url
        self.redirect_url = redirect_url
        self.status_code = status_code


class _CrossHostRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> request.Request | None:
        original_host = parse.urlsplit(req.full_url).hostname
        redirect_host = parse.urlsplit(newurl).hostname
        if original_host and redirect_host and original_host != redirect_host:
            raise _CrossHostRedirectError(req.full_url, newurl, code)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
        if self._skip_depth == 0 and tag in {"p", "div", "section", "article", "main", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._skip_depth == 0 and tag in {"p", "div", "section", "article", "main", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        joined = "".join(self._parts)
        normalized_lines = [" ".join(line.split()) for line in joined.splitlines()]
        return "\n".join(line for line in normalized_lines if line).strip()


class WebFetchTool:
    definition = ToolDefinition(name="WebFetch", input_model=WebFetchToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        raw_url = payload.get("url")
        if not isinstance(raw_url, str):
            return ToolPermissionTarget(tool_name=self.definition.name)
        try:
            hostname = parse.urlsplit(raw_url).hostname
        except Exception:
            hostname = None
        if hostname:
            return ToolPermissionTarget(tool_name=self.definition.name, content=f"domain:{hostname}")
        return ToolPermissionTarget(tool_name=self.definition.name, content=f"input:{raw_url}")

    def execute(self, arguments: WebFetchToolInput, *, cwd: str) -> dict[str, object]:
        start = time.perf_counter()
        opener = request.build_opener(_CrossHostRedirectHandler())
        req = request.Request(
            arguments.url,
            headers={
                "User-Agent": "py-claw/0.1",
                "Accept": "text/html, text/plain, text/markdown, application/xhtml+xml, */*;q=0.1",
            },
        )
        try:
            with opener.open(req, timeout=20) as response:
                body = response.read()
                final_url = response.geturl()
                code = response.getcode() or 200
                content_type = response.headers.get_content_type()
                charset = response.headers.get_content_charset() or "utf-8"
        except _CrossHostRedirectError as exc:
            status = HTTPStatus(exc.status_code)
            duration_ms = int((time.perf_counter() - start) * 1000)
            message = (
                "REDIRECT DETECTED: The URL redirects to a different host.\n\n"
                f"Original URL: {exc.original_url}\n"
                f"Redirect URL: {exc.redirect_url}\n"
                f"Status: {exc.status_code} {status.phrase}\n\n"
                "To complete your request, fetch the redirected URL directly with the same prompt."
            )
            return {
                "bytes": len(message.encode("utf-8")),
                "code": exc.status_code,
                "codeText": status.phrase,
                "result": message,
                "durationMs": duration_ms,
                "url": arguments.url,
            }
        except error.HTTPError as exc:
            code = exc.code
            reason = exc.reason if isinstance(exc.reason, str) else HTTPStatus(exc.code).phrase
            raise ToolError(f"WebFetch failed with HTTP {code} {reason}") from exc
        except error.URLError as exc:
            reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
            raise ToolError(f"WebFetch failed: {reason}") from exc

        text = _decode_body(body, charset=charset)
        content = _render_content(text, content_type=content_type)
        result = _apply_prompt(arguments.prompt, content, fetched_url=final_url)
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "bytes": len(body),
            "code": code,
            "codeText": HTTPStatus(code).phrase,
            "result": result,
            "durationMs": duration_ms,
            "url": arguments.url,
        }


def _decode_body(body: bytes, *, charset: str) -> str:
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _render_content(text: str, *, content_type: str) -> str:
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _HTMLTextExtractor()
        parser.feed(text)
        rendered = parser.text()
        return rendered or text.strip()
    return text.strip()


def _apply_prompt(prompt: str, content: str, *, fetched_url: str) -> str:
    if not content:
        content = "[No textual content extracted]"
    truncated = False
    if len(content) > _MAX_RESULT_CHARS:
        content = content[:_MAX_RESULT_CHARS]
        truncated = True
    result = (
        "WebFetch fetched the requested URL, but prompt-based summarization is not connected to a model yet.\n\n"
        f"Prompt:\n{prompt}\n\n"
        f"Fetched URL: {fetched_url}\n\n"
        f"Content:\n{content}"
    )
    if truncated:
        result += "\n\n[Content truncated]"
    return result
