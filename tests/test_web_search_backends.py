"""Tests for the key-free web search backends (Bing / DuckDuckGo / Baidu)."""
from __future__ import annotations

import base64
import json

import pytest

from py_claw.tools import web_search_backends as backends
from py_claw.tools.web_search_backends import (
    HttpResponse,
    SearchEngineError,
    SearchResult,
    execute_search,
    filter_results,
    normalize_engine_name,
    parse_baidu_html,
    parse_bing_html,
    parse_duckduckgo_html,
    sanitize_bing_url,
    search_duckduckgo,
)


def _ck_a_url(target: str) -> str:
    """Build a bing.com /ck/a redirect URL for a target (test fixture helper)."""
    payload = "a1" + base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&&p=abc123&u={payload}&m=2"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


class TestSanitizeBingUrl:
    def test_direct_url_unchanged(self) -> None:
        assert sanitize_bing_url("https://example.com/article") == "https://example.com/article"

    def test_ck_a_decodes_target(self) -> None:
        assert sanitize_bing_url(_ck_a_url("https://example.com/article")) == (
            "https://example.com/article"
        )

    def test_bing_internal_links_dropped(self) -> None:
        assert sanitize_bing_url("https://www.bing.com/search?q=test") == ""
        assert sanitize_bing_url("/ck/a?u=abc") == ""
        assert sanitize_bing_url("javascript:void(0)") == ""

    def test_tracking_params_stripped(self) -> None:
        cleaned = sanitize_bing_url("https://example.com/page?utm_source=bing&keep=1")
        assert cleaned == "https://example.com/page?keep=1"

    def test_protocol_relative(self) -> None:
        assert sanitize_bing_url("//example.com/article") == "https://example.com/article"


class TestDuckDuckGoUrlDecoding:
    def test_uddg_redirect_decoded(self) -> None:
        encoded = backends.parse.urlencode({"uddg": "https://example.com/x", "rut": "abc"})
        assert backends._decode_duckduckgo_url(f"//duckduckgo.com/l/?{encoded}") == (
            "https://example.com/x"
        )

    def test_direct_url_kept(self) -> None:
        assert backends._decode_duckduckgo_url("https://example.com/x") == "https://example.com/x"


class TestNormalizeEngineName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Bing", "bing"),
            ("MICROSOFT", "bing"),
            ("DDG", "duckduckgo"),
            (" DuckDuckGo ", "duckduckgo"),
            ("百度", "baidu"),
            ("auto", "auto"),
        ],
    )
    def test_aliases(self, raw: str, expected: str) -> None:
        assert normalize_engine_name(raw) == expected


# ---------------------------------------------------------------------------
# Bing
# ---------------------------------------------------------------------------

BING_FIXTURE = """
<html><head><title>python - Bing</title></head><body>
<div id="b_results">
  <li class="b_algo"><h2><a href="https://example.com/direct">Example Direct</a></h2>
    <div class="b_caption"><p>Direct snippet text</p></div>
    <cite>example.com</cite></li>
  <li class="b_algo"><h2><a href="{ck_a}">Example Redirect</a></h2>
    <div class="b_caption"><p>Redirect snippet</p></div></li>
  <li class="b_algo"><h2><a href="https://example.com/direct">Dup</a></h2></li>
  <li class="b_ad"><h2><a href="https://ads.example.com/ad">Ad Result</a></h2></li>
</div></body></html>
""".format(ck_a=_ck_a_url("https://real.example.com/deep"))


class TestParseBingHtml:
    def test_extracts_results(self) -> None:
        results = parse_bing_html(BING_FIXTURE, limit=10)
        assert len(results) == 2  # direct + redirect-decoded; the dup URL is deduped
        assert results[0].title == "Example Direct"
        assert results[0].url == "https://example.com/direct"
        assert results[0].description == "Direct snippet text"
        assert results[0].source == "example.com"
        assert results[0].engine == "bing"
        assert results[1].title == "Example Redirect"
        assert results[1].url == "https://real.example.com/deep"
        assert "Ad Result" not in [r.title for r in results]

    def test_limit_respected(self) -> None:
        assert len(parse_bing_html(BING_FIXTURE, limit=1)) == 1

    def test_bot_page_raises(self) -> None:
        blocked = '<html><head><title>验证</title></head><body><p>captcha</p><p>verification</p></body></html>'
        with pytest.raises(SearchEngineError, match="bot-detection"):
            parse_bing_html(blocked, limit=5)


class TestSearchBing:
    def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_fetch(url: str, **kwargs: object) -> HttpResponse:
            assert url.startswith(backends.BING_SEARCH_URL)
            return HttpResponse(status=200, final_url=url, headers={}, body=BING_FIXTURE.encode())

        results = backends.search_bing("python web", 3, fetch=fake_fetch)
        assert len(results) == 2
        assert all(r.engine == "bing" for r in results)

    def test_network_failure_raises(self) -> None:
        def fake_fetch(url: str, **kwargs: object) -> HttpResponse:
            raise SearchEngineError("request failed: DNS")

        with pytest.raises(SearchEngineError, match="DNS"):
            backends.search_bing("python web", 3, fetch=fake_fetch)

    def test_no_results_raises(self) -> None:
        def fake_fetch(url: str, **kwargs: object) -> HttpResponse:
            return HttpResponse(status=200, final_url=url, headers={}, body=b"<html><body>nothing</body></html>")

        with pytest.raises(SearchEngineError, match="no parseable results"):
            backends.search_bing("python web", 3, fetch=fake_fetch)


# ---------------------------------------------------------------------------
# DuckDuckGo
# ---------------------------------------------------------------------------

DDG_HTML_FIXTURE = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffirst&rut=x">First Result</a>
  <a class="result__snippet" href="#">First snippet text.</a>
</div>
<div class="result">
  <a class="result__a" href="https://direct.example.com/second">Second Result</a>
  <a class="result__snippet" href="#">Second snippet.</a>
</div>
</body></html>
"""

DDG_MAIN_PAGE = (
    "<html><head>"
    '<link rel="preload" href="https://links.duckduckgo.com/d.js?q=test&l=wt-wt&s=0&vqd=4-123">'
    "</head><body></body></html>"
)

DDG_JSONP_BODY = (
    "window.execDeep = function() { "
    "DDG.pageLayout.load('d', "
    + json.dumps(
        [
            {"t": "DDG Result One", "u": "https://example.com/one", "a": "One abstract", "i": "example.com"},
            {"n": 1, "t": "Navigation", "u": "https://duckduckgo.com/nav"},
            {"t": "DDG Result Two", "u": "https://example.com/two", "a": "Two abstract", "sn": "example.com"},
        ]
    )
    + "); }"
)


class TestParseDuckDuckGoHtml:
    def test_extracts_results(self) -> None:
        results = parse_duckduckgo_html(DDG_HTML_FIXTURE, limit=10)
        assert len(results) == 2
        assert results[0].title == "First Result"
        assert results[0].url == "https://example.com/first"
        assert results[0].description == "First snippet text."
        assert results[1].url == "https://direct.example.com/second"
        assert all(r.engine == "duckduckgo" for r in results)


class TestSearchDuckDuckGo:
    def test_preload_path(self) -> None:
        def fake_fetch(url: str, **kwargs: object) -> HttpResponse:
            if url.startswith("https://duckduckgo.com/"):
                return HttpResponse(status=200, final_url=url, headers={}, body=DDG_MAIN_PAGE.encode())
            if "links.duckduckgo.com/d.js" in url:
                return HttpResponse(status=200, final_url=url, headers={}, body=DDG_JSONP_BODY.encode())
            raise AssertionError(f"unexpected url {url}")

        results = search_duckduckgo("test", 10, fetch=fake_fetch)
        assert [r.url for r in results] == ["https://example.com/one", "https://example.com/two"]
        assert results[0].title == "DDG Result One"
        assert results[1].source == "example.com"  # sn fallback

    def test_untrusted_preload_ignored(self) -> None:
        main_page = (
            '<html><head><link rel="preload" href="https://evil.example.com/d.js?q=x">'
            "</head><body></body></html>"
        )
        calls: list[str] = []

        def fake_fetch(url: str, **kwargs: object) -> HttpResponse:
            calls.append(url)
            if url.startswith("https://duckduckgo.com/"):
                return HttpResponse(status=200, final_url=url, headers={}, body=main_page.encode())
            if "html.duckduckgo.com" in url:
                return HttpResponse(status=200, final_url=url, headers={}, body=DDG_HTML_FIXTURE.encode())
            raise AssertionError(f"unexpected url {url}")

        results = search_duckduckgo("test", 10, fetch=fake_fetch)
        assert all("evil.example.com" not in c for c in calls)
        assert len(results) == 2  # fell through to the html endpoint

    def test_preload_failure_falls_back_to_html(self) -> None:
        def fake_fetch(url: str, **kwargs: object) -> HttpResponse:
            if url.startswith("https://duckduckgo.com/"):
                return HttpResponse(status=202, final_url=url, headers={}, body=b"challenge")
            if "html.duckduckgo.com" in url:
                return HttpResponse(status=200, final_url=url, headers={}, body=DDG_HTML_FIXTURE.encode())
            raise AssertionError(f"unexpected url {url}")

        results = search_duckduckgo("test", 10, fetch=fake_fetch)
        assert [r.url for r in results] == ["https://example.com/first", "https://direct.example.com/second"]


# ---------------------------------------------------------------------------
# Baidu
# ---------------------------------------------------------------------------

BAIDU_FIXTURE = """
<html><body><div id="container">
  <div class="result c-container">
    <h3 class="c-header"><a href="http://www.baidu.com/link?url=ENC1"><span class="tts-b-hl">Card One</span></a></h3>
    <div data-module="abstract"><span class="c-color-gray">One abstract text</span></div>
  </div>
  <div class="result c-container">
    <h3 class="c-header"><a href="https://direct.example.com/two">Card Two</a><img src="icon.png"></h3>
  </div>
  <div class="result c-container">
    <h3 class="c-header"><a href="http://www.baidu.com/link?url=ENC2">Card Three</a></h3>
    <div data-module="abstract"><span>Three abstract</span></div>
  </div>
</div></body></html>
"""


class TestParseBaiduHtml:
    def test_extracts_results(self) -> None:
        results = parse_baidu_html(BAIDU_FIXTURE, limit=10)
        assert len(results) == 3
        assert results[0].title == "Card One"
        assert results[0].description == "One abstract text"
        assert results[1].url == "https://direct.example.com/two"
        # Card two has no abstract — it must not steal card three's snippet
        assert results[1].description == ""
        assert results[2].description == "Three abstract"
        assert all(r.engine == "baidu" for r in results)

    def test_challenge_page_raises(self) -> None:
        challenge = '<html><head><title>百度安全验证</title></head><body>wappass captcha</body></html>'
        with pytest.raises(SearchEngineError, match="security verification"):
            parse_baidu_html(challenge, limit=5)


class TestSearchBaidu:
    def test_resolves_link_redirects_and_drops_wrappers(self) -> None:
        def fake_fetch(url: str, **kwargs: object) -> HttpResponse:
            if "www.baidu.com/s?" in url:
                return HttpResponse(status=200, final_url=url, headers={}, body=BAIDU_FIXTURE.encode())
            if "url=ENC1" in url:
                return HttpResponse(
                    status=302,
                    final_url=url,
                    headers={"location": "https://real.example.com/one"},
                    body=b"",
                )
            if "url=ENC2" in url:
                # Unresolvable: stays a baidu wrapper
                return HttpResponse(
                    status=302,
                    final_url=url,
                    headers={"location": "http://www.baidu.com"},
                    body=b"",
                )
            raise AssertionError(f"unexpected url {url}")

        results = backends.search_baidu("test", 5, fetch=fake_fetch)
        assert [r.url for r in results] == [
            "https://real.example.com/one",
            "https://direct.example.com/two",
        ]
        assert results[0].source == "real.example.com"

    def test_all_wrappers_raises(self) -> None:
        def fake_fetch(url: str, **kwargs: object) -> HttpResponse:
            if "www.baidu.com/s?" in url:
                page = '<html><body><div><h3><a href="http://www.baidu.com/baidu.php?url=Ks1">X</a></h3></div></body></html>'
                return HttpResponse(status=200, final_url=url, headers={}, body=page.encode())
            return HttpResponse(status=302, final_url=url, headers={"location": "http://www.baidu.com"}, body=b"")

        with pytest.raises(SearchEngineError, match="unresolvable wrapper"):
            backends.search_baidu("test", 5, fetch=fake_fetch)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _ok_engine(name: str):
    def engine(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
        return [
            SearchResult(title=f"{name} one", url=f"https://{name}.example.com/1", engine=name),
            SearchResult(title=f"{name} two", url=f"https://{name}.example.com/2", engine=name),
        ]

    return engine


class TestExecuteSearch:
    def test_auto_uses_first_working_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in list(backends.SUPPORTED_ENGINES):
            monkeypatch.setitem(backends._ENGINE_FUNCTIONS, name, _ok_engine(name))
        result = execute_search("query", engine="auto", max_results=3)
        assert result["engine"] == "bing"
        assert result["totalResults"] == 3  # bing 2 + ddg 1 (limit reached)
        assert result["failures"] == []

    def test_auto_falls_back_when_engine_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken_bing(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
            raise SearchEngineError("bing blocked")

        monkeypatch.setitem(backends._ENGINE_FUNCTIONS, "bing", broken_bing)
        for name in ("duckduckgo", "baidu"):
            monkeypatch.setitem(backends._ENGINE_FUNCTIONS, name, _ok_engine(name))
        result = execute_search("query", engine="auto", max_results=4)
        assert result["engine"] == "duckduckgo"
        assert result["totalResults"] == 4  # ddg 2 + baidu 2
        assert [f["engine"] for f in result["failures"]] == ["bing"]
        assert result["failures"][0]["error"] == "bing blocked"

    def test_all_engines_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in list(backends.SUPPORTED_ENGINES):
            def broken(query: str, limit: int, *, fetch: object = None, _n=name) -> list[SearchResult]:
                raise SearchEngineError(f"{_n} down")

            monkeypatch.setitem(backends._ENGINE_FUNCTIONS, name, broken)
        result = execute_search("query", engine="auto", max_results=5)
        assert result["results"] == []
        assert result["engine"] == ""
        assert [f["engine"] for f in result["failures"]] == ["bing", "duckduckgo", "baidu"]

    def test_explicit_engine_no_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
            raise SearchEngineError("baidu down")

        monkeypatch.setitem(backends._ENGINE_FUNCTIONS, "baidu", broken)
        result = execute_search("query", engine="baidu", max_results=5)
        assert result["results"] == []
        assert result["engines"] == ["baidu"]
        assert len(result["failures"]) == 1

    def test_explicit_engine_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, object] = {}

        def spy_bing(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
            seen["limit"] = limit
            return _ok_engine("bing")(query, limit)

        monkeypatch.setitem(backends._ENGINE_FUNCTIONS, "bing", spy_bing)
        result = execute_search("query", engine="Microsoft", max_results=2)
        assert seen["limit"] == 2
        assert result["engine"] == "bing"

    def test_unsupported_engine_reports_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
            raise SearchEngineError("offline")

        for name in list(backends.SUPPORTED_ENGINES):
            monkeypatch.setitem(backends._ENGINE_FUNCTIONS, name, broken)
        # Explicit unsupported engine: reported as a failure, no engine runs.
        result = execute_search("query", engine="yandex", max_results=2)
        assert result["engines"] == ["yandex"]
        assert result["failures"][0]["error"] == "unsupported engine: yandex"
        assert result["results"] == []

    def test_max_results_clamped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def huge(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
            assert limit == 20
            return [SearchResult(title=f"r{i}", url=f"https://example.com/{i}", engine="bing") for i in range(30)]

        for name in list(backends.SUPPORTED_ENGINES):
            monkeypatch.setitem(backends._ENGINE_FUNCTIONS, name, huge)
        result = execute_search("query", engine="bing", max_results=999)
        assert result["totalResults"] == 20

    def test_dedup_across_engines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def bing(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
            return [SearchResult(title="dup", url="https://example.com/same", engine="bing")]

        def ddg(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
            return [
                SearchResult(title="dup again", url="https://example.com/same", engine="duckduckgo"),
                SearchResult(title="unique", url="https://example.com/other", engine="duckduckgo"),
            ]

        monkeypatch.setitem(backends._ENGINE_FUNCTIONS, "bing", bing)
        monkeypatch.setitem(backends._ENGINE_FUNCTIONS, "duckduckgo", ddg)

        def offline_baidu(query: str, limit: int, *, fetch: object = None) -> list[SearchResult]:
            raise SearchEngineError("offline in test")

        monkeypatch.setitem(backends._ENGINE_FUNCTIONS, "baidu", offline_baidu)
        result = execute_search("query", engine="auto", max_results=10)
        assert [r["url"] for r in result["results"]] == [
            "https://example.com/same",
            "https://example.com/other",
        ]

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValueError):
            execute_search("   ", engine="auto")


class TestFilterResults:
    def _results(self) -> list[SearchResult]:
        return [
            SearchResult(title="a", url="https://docs.python.org/guide", engine="bing"),
            SearchResult(title="b", url="https://python.org/blog", engine="bing"),
            SearchResult(title="c", url="https://example.com/page", engine="bing"),
        ]

    def test_allowed_domains(self) -> None:
        filtered = filter_results(self._results(), allowed_domains=["python.org"])
        assert [r.url for r in filtered] == [
            "https://docs.python.org/guide",
            "https://python.org/blog",
        ]

    def test_blocked_domains(self) -> None:
        filtered = filter_results(self._results(), blocked_domains=["example.com"])
        assert [r.url for r in filtered] == [
            "https://docs.python.org/guide",
            "https://python.org/blog",
        ]

    def test_no_filters_keeps_all(self) -> None:
        assert len(filter_results(self._results())) == 3
