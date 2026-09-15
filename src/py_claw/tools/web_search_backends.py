"""Web search backends: key-free multi-engine search (Bing / DuckDuckGo / Baidu).

Design mirrors the open-webSearch MCP server (Aas-ee/open-webSearch): no API
keys, public search endpoints, engine name normalization, partial-failure
reporting, and structured results carrying title/url/description/source/engine.

Implementation uses only the standard library (urllib + html.parser) to stay
consistent with WebFetchTool and avoid new dependencies. All network access
goes through the module-level ``_http_get`` function so tests can monkeypatch
a single seam; engine executors accept an explicit ``fetch`` override for
finer-grained control.
"""
from __future__ import annotations

import base64
import binascii
import gzip
import json
import re
import zlib
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib import error, parse, request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

DEFAULT_TIMEOUT_SECONDS = 15.0

BING_SEARCH_URL = "https://www.bing.com/search"
DUCKDUCKGO_MAIN_URL = "https://duckduckgo.com/"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
DUCKDUCKGO_PRELOAD_HOST = "links.duckduckgo.com"
BAIDU_SEARCH_URL = "https://www.baidu.com/s"
# Stable hao123 client id — baidu 302s plain requests to a wappass captcha
# page unless this tn parameter is present. It is a fixed client identifier,
# not a session token (see open-webSearch baidu engine).
BAIDU_TN = "88093251_62_hao_pg"


class SearchEngineError(Exception):
    """Raised when an engine cannot produce results (blocked, unreachable, ...)."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    final_url: str
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    description: str = ""
    source: str = ""
    engine: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "description": self.description,
            "source": self.source,
            "engine": self.engine,
        }


# HTML void elements: start tags without end tags. Depth-based parsers must
# not count these or malformed self-closing markup (e.g. bare <img>) would
# unbalance the stack.
_VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    }
)


class _RedirectCaptured(Exception):
    def __init__(self, status: int, location: str) -> None:
        super().__init__(f"Redirect {status} -> {location}")
        self.status = status
        self.location = location


class _CapturingRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise _RedirectCaptured(code, newurl)


def _decode_body(body: bytes, content_encoding: str) -> bytes:
    if "gzip" in content_encoding:
        try:
            return gzip.decompress(body)
        except (OSError, EOFError):
            return body
    if "deflate" in content_encoding:
        try:
            return zlib.decompress(body, -zlib.MAX_WBITS)
        except zlib.error:
            return body
    return body


def _http_get(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    data: bytes | None = None,
    follow_redirects: bool = True,
) -> HttpResponse:
    """Fetch a URL and return the response (never raises on HTTP status).

    Network failures (DNS, timeout, TLS) raise ``SearchEngineError`` so
    orchestration can fall back to the next engine.
    """
    merged_headers = dict(DEFAULT_HEADERS)
    if headers:
        merged_headers.update(headers)
    if follow_redirects:
        opener = request.build_opener()
    else:
        opener = request.build_opener(_CapturingRedirectHandler())
    req = request.Request(url, data=data, headers=merged_headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as response:
            body = _decode_body(response.read(), response.headers.get("Content-Encoding", ""))
            return HttpResponse(
                status=response.getcode() or 200,
                final_url=response.geturl(),
                headers={k.lower(): v for k, v in response.headers.items()},
                body=body,
            )
    except _RedirectCaptured as exc:
        return HttpResponse(
            status=exc.status,
            final_url=url,
            headers={"location": exc.location},
            body=b"",
        )
    except (error.URLError, error.HTTPError, TimeoutError, OSError) as exc:
        raise SearchEngineError(f"request failed: {exc}") from exc


def _as_fetch(fetch: object) -> object:
    """Resolve the effective fetch callable; None means the module default."""
    return fetch if fetch is not None else _http_get


def _fetch_with_fn(fetch_fn: object, url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS, **kwargs: object) -> str:
    response = fetch_fn(url, timeout=timeout, **kwargs)  # type: ignore[operator]
    if not isinstance(response, HttpResponse):
        raise SearchEngineError(f"fetch hook returned {type(response).__name__}, expected HttpResponse")
    if response.status >= 400:
        raise SearchEngineError(f"HTTP {response.status} from {url}")
    return response.body.decode("utf-8", errors="replace")


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _hostname(url: str) -> str:
    try:
        return parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Bing
# ---------------------------------------------------------------------------


def _decode_bing_ck_target(url: str) -> str:
    """Decode a bing.com /ck/a redirect link to the real target URL."""
    try:
        parts = parse.urlsplit(url)
    except ValueError:
        return ""
    if not parts.hostname or not parts.hostname.endswith("bing.com"):
        return ""
    if not parts.path.startswith("/ck/a"):
        return ""
    encoded = parse.parse_qs(parts.query).get("u", [""])[0].strip()
    if not encoded:
        return ""
    payload = encoded[2:] if encoded.startswith("a1") else encoded
    # base64url without padding
    padded = payload + "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", "replace").strip()
    except (binascii.Error, ValueError):
        return ""
    return decoded if decoded.startswith(("http://", "https://")) else ""


def sanitize_bing_url(raw_url: str | None) -> str:
    """Resolve Bing internal redirect links and strip tracking parameters."""
    if not raw_url:
        return ""
    url = raw_url.strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    elif url.startswith("/"):
        # Internal paths without a scheme are unusable jump links
        if url.startswith(("/ck/a", "/search", "/newtabredir")):
            return ""
        url = f"https://www.bing.com{url}"
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        parts = parse.urlsplit(url)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    path = parts.path.lower()
    if host.endswith("bing.com") and path.startswith("/ck/a"):
        decoded = _decode_bing_ck_target(url)
        return sanitize_bing_url(decoded) if decoded else ""
    if host.endswith("bing.com") and path.startswith(("/search", "/ck/a", "/newtabredir")):
        return ""
    query = [
        (k, v)
        for k, v in parse.parse_qsl(parts.query, keep_blank_values=True)
        if k not in {"utm_source", "utm_medium", "utm_campaign", "ref", "source"}
    ]
    suffix = parse.urlencode(query)
    rebuilt = f"{parts.scheme}://{parts.netloc}{parts.path}"
    return f"{rebuilt}?{suffix}" if suffix else rebuilt


_BING_BOT_KEYWORDS = (
    "captcha",
    "verification",
    "verify you are human",
    "access denied",
    "too many requests",
    "请验证",
    "验证码",
    "人机验证",
)


def _is_bing_blocked_page(html: str, has_results: bool) -> bool:
    if has_results:
        return False
    normalized = html.lower()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = _normalize_whitespace(title_match.group(1)).lower() if title_match else ""
    keyword_hits = sum(1 for kw in _BING_BOT_KEYWORDS if kw in normalized)
    return title in _BING_BOT_KEYWORDS or keyword_hits >= 2


class _BingResultParser(HTMLParser):
    """Extract (title, url, description, source) tuples from Bing SERP HTML.

    Tracks ``li.b_algo`` / ``li.b_ans`` result blocks: the first anchor inside
    the block heading is the title link, ``.b_caption`` text is the snippet,
    and ``cite`` is the source attribution.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[tuple[str, str, str, str]] = []
        self._li_depth = 0
        self._in_result = False
        self._result_li_depth = 0
        self._in_heading = False
        self._heading_title_parts: list[str] = []
        self._heading_url = ""
        self._in_heading_anchor = False
        self._in_caption = False
        self._caption_parts: list[str] = []
        self._in_cite = False
        self._cite_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        classes = attr_map.get("class", "").split()
        if tag == "li":
            self._li_depth += 1
            if not self._in_result and ("b_algo" in classes or "b_ans" in classes):
                self._in_result = True
                self._result_li_depth = self._li_depth
                self._in_heading = False
                self._heading_title_parts = []
                self._heading_url = ""
                self._in_caption = False
                self._caption_parts = []
                self._cite_parts = []
            return
        if not self._in_result:
            return
        if tag in {"h2", "h3"} and not self._in_heading:
            self._in_heading = True
        elif tag == "a" and self._in_heading and not self._heading_url:
            href = attr_map.get("href", "")
            if href:
                self._heading_url = href
                self._in_heading_anchor = True
        elif tag == "div" and "b_caption" in classes and not self._in_caption:
            self._in_caption = True
        elif tag == "cite" and not self._in_cite:
            self._in_cite = True

    def handle_endtag(self, tag: str) -> None:
        if not self._in_result:
            return
        if tag == "li":
            self._li_depth -= 1
            if self._li_depth < self._result_li_depth:
                self._flush_result()
                self._in_result = False
            return
        if tag in {"h2", "h3"}:
            self._in_heading = False
        elif tag == "a":
            self._in_heading_anchor = False
        elif tag == "div" and self._in_caption:
            self._in_caption = False
        elif tag == "cite":
            self._in_cite = False

    def handle_data(self, data: str) -> None:
        if not self._in_result or not data:
            return
        if self._in_heading and self._in_heading_anchor:
            self._heading_title_parts.append(data)
        elif self._in_caption:
            self._caption_parts.append(data)
        elif self._in_cite:
            self._cite_parts.append(data)

    def _flush_result(self) -> None:
        title = _normalize_whitespace("".join(self._heading_title_parts))
        url = sanitize_bing_url(self._heading_url)
        description = _normalize_whitespace("".join(self._caption_parts))[:400]
        source = _normalize_whitespace("".join(self._cite_parts))
        if not url:
            return
        if not title and not description:
            return
        if not title:
            host = _hostname(url)
            title = f"Result from {host}" if host else "Untitled result"
        self.results.append((title, url, description, source))


def parse_bing_html(html: str, limit: int) -> list[SearchResult]:
    parser = _BingResultParser()
    parser.feed(html)
    seen: set[str] = set()
    results: list[SearchResult] = []
    for title, url, description, source in parser.results:
        if url in seen:
            continue
        seen.add(url)
        results.append(
            SearchResult(title=title, url=url, description=description, source=source, engine="bing")
        )
        if len(results) >= limit:
            break
    if not results and _is_bing_blocked_page(html, has_results=False):
        raise SearchEngineError("bing returned a bot-detection or verification page")
    return results


def search_bing(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
    """Search Bing; the first SERP page returns up to ~10 organic results."""
    fetch_fn = _as_fetch(fetch)
    params = parse.urlencode({"q": query, "ensearch": "0"})
    html = _fetch_with_fn(fetch_fn, f"{BING_SEARCH_URL}?{params}")
    results = parse_bing_html(html, limit)
    if not results:
        raise SearchEngineError("bing returned no parseable results")
    return results


# ---------------------------------------------------------------------------
# DuckDuckGo
# ---------------------------------------------------------------------------


def _decode_duckduckgo_url(href: str) -> str:
    """Decode a //duckduckgo.com/l/?uddg=... redirect to the real URL."""
    url = href.strip()
    if url.startswith("//"):
        url = f"https:{url}"
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        parts = parse.urlsplit(url)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if host.endswith("duckduckgo.com") and parts.path == "/l/":
        target = parse.parse_qs(parts.query).get("uddg", [""])[0]
        return target if target.startswith(("http://", "https://")) else ""
    return url


def _is_trusted_ddg_preload(url: str) -> bool:
    try:
        parts = parse.urlsplit(url)
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and (parts.hostname or "").lower() == DUCKDUCKGO_PRELOAD_HOST
        and not parts.port
        and parts.path == "/d.js"
    )


_DDG_PRELOAD_RE = re.compile(r"https://links\.duckduckgo\.com/d\.js\?[^\"'\s]+", re.I)
_DDG_JSONP_RE = re.compile(r"DDG\.pageLayout\.load\('d',\s*(\[.*?\])\s*\);", re.S)


def _ddg_jsonp_items(body: str) -> list[dict[str, object]]:
    match = _DDG_JSONP_RE.search(body)
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    items = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("n"):  # navigation entries are not web results
            continue
        items.append(item)
    return items


def search_duckduckgo_preload(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
    """Fetch the DDG main page and query its preloaded d.js result feed."""
    fetch_fn = _as_fetch(fetch)
    main_url = f"{DUCKDUCKGO_MAIN_URL}?{parse.urlencode({'q': query, 'ia': 'web'})}"
    html = _fetch_with_fn(fetch_fn, main_url)
    preload_url = next(
        (c for c in _DDG_PRELOAD_RE.findall(html) if _is_trusted_ddg_preload(c)),
        "",
    )
    if not preload_url:
        return []
    base_parts = parse.urlsplit(preload_url)
    base_query = parse.parse_qsl(base_parts.query, keep_blank_values=True)
    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    offset = 0
    while len(results) < limit:
        page_query = [(k, str(offset) if k == "s" else v) for k, v in base_query]
        page_url = (
            f"{base_parts.scheme}://{base_parts.netloc}{base_parts.path}"
            f"?{parse.urlencode(page_query)}"
        )
        body = _fetch_with_fn(
            fetch_fn,
            page_url,
            headers={
                "Accept": "*/*",
                "Referer": "https://duckduckgo.com/",
                "Sec-Fetch-Site": "same-site",
                "Sec-Fetch-Mode": "no-cors",
            },
        )
        items = _ddg_jsonp_items(body)
        if not items:
            break
        added = 0
        for item in items:
            if len(results) >= limit:
                break
            url = str(item.get("u") or "")
            if not url.startswith(("http://", "https://")) or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(
                SearchResult(
                    title=str(item.get("t") or ""),
                    url=url,
                    description=str(item.get("a") or "")[:400],
                    source=str(item.get("i") or item.get("sn") or "")[:200],
                    engine="duckduckgo",
                )
            )
            added += 1
        offset += added
        if added == 0:
            break
    return results


class _DuckDuckGoResultParser(HTMLParser):
    """Extract results from html.duckduckgo.com: a.result__a + a.result__snippet."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[tuple[str, str, str, str]] = []
        self._pending_url = ""
        self._pending_title_parts: list[str] = []
        self._in_title_link = False
        self._in_snippet = False
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = {k: (v or "") for k, v in attrs}
        classes = attr_map.get("class", "").split()
        href = attr_map.get("href", "")
        if "result__a" in classes and href:
            self._pending_url = _decode_duckduckgo_url(href)
            self._pending_title_parts = []
            self._in_title_link = True
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "a":
            return
        if self._in_title_link:
            self._in_title_link = False
            title = _normalize_whitespace("".join(self._pending_title_parts))
            if self._pending_url and title:
                self.results.append((title, self._pending_url, "", ""))
            self._pending_url = ""
        elif self._in_snippet:
            self._in_snippet = False
            snippet = _normalize_whitespace("".join(self._snippet_parts))[:400]
            if snippet and self.results:
                title, url, _desc, _src = self.results[-1]
                self.results[-1] = (title, url, snippet, _src)

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._in_title_link:
            self._pending_title_parts.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)


def parse_duckduckgo_html(html: str, limit: int) -> list[SearchResult]:
    parser = _DuckDuckGoResultParser()
    parser.feed(html)
    return [
        SearchResult(title=title, url=url, description=desc, source=src, engine="duckduckgo")
        for title, url, desc, src in parser.results[:limit]
    ]


def search_duckduckgo_html(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
    fetch_fn = _as_fetch(fetch)
    url = f"{DUCKDUCKGO_HTML_URL}?{parse.urlencode({'q': query})}"
    html = _fetch_with_fn(fetch_fn, url)
    return parse_duckduckgo_html(html, limit)


def search_duckduckgo(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
    """DuckDuckGo search: preloaded d.js feed first, HTML endpoint as fallback."""
    fetch_fn = _as_fetch(fetch)
    try:
        results = search_duckduckgo_preload(query, limit, fetch=fetch_fn)
        if results:
            return results
    except SearchEngineError:
        pass
    return search_duckduckgo_html(query, limit, fetch=fetch_fn)


# ---------------------------------------------------------------------------
# Baidu
# ---------------------------------------------------------------------------

_BAIDU_CHALLENGE_MARKERS = ("wappass", "百度安全验证", "请输入验证码", "antispider")


def _is_baidu_challenge_page(html: str, has_results: bool) -> bool:
    if has_results:
        return False
    normalized = html.lower()
    return any(marker.lower() in normalized for marker in _BAIDU_CHALLENGE_MARKERS)


class _BaiduResultParser(HTMLParser):
    """Extract results from baidu SERP: ``h3 > a`` (title/url) plus the
    ``data-module="abstract"`` snippet that follows each result card.

    A snippet only attaches to a result while no later ``h3`` has opened —
    this prevents a card without an abstract from stealing the next card's
    snippet.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[tuple[str, str, str, str]] = []
        self._in_h3 = False
        self._h3_depth = 0
        self._in_h3_anchor = False
        self._h3_url = ""
        self._h3_title_parts: list[str] = []
        self._in_abstract = False
        self._abstract_depth = 0
        self._abstract_parts: list[str] = []
        self._h3_opened_since_last_result = False

    def _count_depth(self, tag: str) -> bool:
        return tag not in _VOID_ELEMENTS

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        if tag == "h3" and not self._in_h3:
            self._in_h3 = True
            self._h3_depth = 1 if self._count_depth(tag) else 0
            self._h3_url = ""
            self._h3_title_parts = []
            self._h3_opened_since_last_result = True
            return
        if self._in_h3 and self._count_depth(tag):
            self._h3_depth += 1
        if tag == "a" and self._in_h3 and not self._h3_url:
            href = attr_map.get("href", "")
            if href:
                self._h3_url = href
                self._in_h3_anchor = True
        if attr_map.get("data-module") == "abstract" and not self._in_abstract:
            self._in_abstract = True
            self._abstract_depth = 1 if self._count_depth(tag) else 0
            self._abstract_parts = []
            return
        if self._in_abstract and self._count_depth(tag):
            self._abstract_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_h3_anchor = False
        if self._in_abstract and self._count_depth(tag):
            self._abstract_depth -= 1
            if self._abstract_depth <= 0:
                self._in_abstract = False
                self._attach_abstract()
        if self._in_h3 and self._count_depth(tag):
            self._h3_depth -= 1
            if self._h3_depth <= 0:
                self._close_h3()

    def _close_h3(self) -> None:
        self._in_h3 = False
        self._in_h3_anchor = False
        title = _normalize_whitespace("".join(self._h3_title_parts))
        url = self._h3_url
        if title and url:
            self.results.append((title, url, "", ""))
            # The snippet for this card may now arrive; a later card's h3
            # will re-arm the guard before its own abstract.
            self._h3_opened_since_last_result = False

    def _attach_abstract(self) -> None:
        if self._h3_opened_since_last_result or not self.results:
            return
        snippet = _normalize_whitespace("".join(self._abstract_parts))[:400]
        if not snippet:
            return
        title, url, _desc, _src = self.results[-1]
        self.results[-1] = (title, url, snippet, _src)

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._in_h3 and self._in_h3_anchor:
            self._h3_title_parts.append(data)
        elif self._in_abstract:
            self._abstract_parts.append(data)


def parse_baidu_html(html: str, limit: int) -> list[SearchResult]:
    parser = _BaiduResultParser()
    parser.feed(html)
    results = [
        SearchResult(title=title, url=url, description=desc, source="", engine="baidu")
        for title, url, desc, _src in parser.results[:limit]
    ]
    if not results and _is_baidu_challenge_page(html, has_results=False):
        raise SearchEngineError("baidu returned a security verification page")
    return results


def _is_baidu_wrapper_url(url: str) -> bool:
    """True for baidu.com jump links whose target could not be resolved.

    /baidu.php wrappers 302 back to the baidu homepage without a session, and
    unresolved /link jumps are equally unusable — both are dead ends for a
    downstream fetch, so they are dropped instead of returned.
    """
    try:
        parts = parse.urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return host.endswith("baidu.com") and parts.path.startswith(("/link", "/baidu.php"))


def _resolve_baidu_redirect(href: str, fetch_fn: object) -> str:
    """Best-effort resolution of baidu.com/link redirect URLs to the real target."""
    try:
        parts = parse.urlsplit(href)
    except ValueError:
        return href
    host = (parts.hostname or "").lower()
    if not host.endswith("baidu.com") or not parts.path.startswith("/link"):
        return href
    try:
        response = fetch_fn(href, timeout=6.0, follow_redirects=False)  # type: ignore[operator]
    except Exception:
        return href
    if not isinstance(response, HttpResponse):
        return href
    location = response.headers.get("location", "")
    if response.status in (301, 302, 303, 307, 308) and location.startswith(("http://", "https://")):
        target_host = _hostname(location)
        if target_host and not target_host.endswith("baidu.com"):
            return location
    return href


def search_baidu(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
    fetch_fn = _as_fetch(fetch)
    params = parse.urlencode({"wd": query, "tn": BAIDU_TN, "ie": "utf-8", "pn": "0"})
    html = _fetch_with_fn(fetch_fn, f"{BAIDU_SEARCH_URL}?{params}")
    results = parse_baidu_html(html, limit)
    if not results:
        raise SearchEngineError("baidu returned no parseable results")
    resolved: list[SearchResult] = []
    seen: set[str] = set()
    for result in results:
        url = _resolve_baidu_redirect(result.url, fetch_fn)
        if _is_baidu_wrapper_url(url) or url in seen:
            continue
        seen.add(url)
        resolved.append(
            SearchResult(
                title=result.title,
                url=url,
                description=result.description,
                source=result.source or _hostname(url),
                engine=result.engine,
            )
        )
    if not resolved:
        raise SearchEngineError("baidu returned only unresolvable wrapper links")
    return resolved[:limit]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

SUPPORTED_ENGINES = ("bing", "duckduckgo", "baidu")
AUTO_ENGINE_ORDER = ("bing", "duckduckgo", "baidu")

_ENGINE_FUNCTIONS = {
    "bing": search_bing,
    "duckduckgo": search_duckduckgo,
    "baidu": search_baidu,
}

_ENGINE_ALIASES = {
    "bing": "bing",
    "microsoft": "bing",
    "msn": "bing",
    "duckduckgo": "duckduckgo",
    "ddg": "duckduckgo",
    "duck": "duckduckgo",
    "baidu": "baidu",
    "百度": "baidu",
}


def normalize_engine_name(engine: str) -> str:
    cleaned = engine.strip().lower().replace(" ", "")
    return _ENGINE_ALIASES.get(cleaned, cleaned)


def filter_results(
    results: list[SearchResult],
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
) -> list[SearchResult]:
    """Filter results by allowed/blocked domains (exact or subdomain match)."""

    def _matches(hostname: str, domains: list[str]) -> bool:
        return any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains)

    filtered = results
    if allowed_domains:
        allowed = [d.strip().lower() for d in allowed_domains if d.strip()]
        filtered = [r for r in filtered if _matches(_hostname(r.url).lower(), allowed)]
    if blocked_domains:
        blocked = [d.strip().lower() for d in blocked_domains if d.strip()]
        filtered = [r for r in filtered if not _matches(_hostname(r.url).lower(), blocked)]
    return filtered


def execute_search(
    query: str,
    *,
    engine: str = "auto",
    max_results: int = 8,
    fetch: object = None,
) -> dict[str, object]:
    """Run a web search, falling back through engines in AUTO_ENGINE_ORDER.

    Returns a dict with ``query``, ``engine``, ``engines``, ``results``
    (list of result dicts), ``totalResults`` and ``failures`` (per-engine
    error list). Never raises on engine failures — the caller decides how to
    present an all-failed search.
    """
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty")
    max_results = max(1, min(int(max_results), 20))

    requested = normalize_engine_name(engine)
    engines = [requested] if requested != "auto" else list(AUTO_ENGINE_ORDER)

    results: list[SearchResult] = []
    failures: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    engine_used: str | None = None

    for name in engines:
        if len(results) >= max_results:
            break
        fn = _ENGINE_FUNCTIONS.get(name)
        if fn is None:
            failures.append({"engine": name, "error": f"unsupported engine: {name}"})
            if requested != "auto":
                break
            continue
        try:
            got = fn(clean_query, max(1, max_results - len(results)), fetch=fetch)
        except SearchEngineError as exc:
            failures.append({"engine": name, "error": str(exc)})
        except Exception as exc:  # defensive: a parser bug must not kill the turn
            failures.append({"engine": name, "error": f"unexpected error: {exc}"})
        else:
            for result in got:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                results.append(result)
                if engine_used is None:
                    engine_used = name
                if len(results) >= max_results:
                    break
        if requested != "auto":
            break
        if len(results) >= max_results:
            break

    return {
        "query": clean_query,
        "engine": engine_used or (requested if requested != "auto" else ""),
        "engines": engines,
        "totalResults": len(results),
        "results": [r.to_dict() for r in results],
        "failures": failures,
    }
