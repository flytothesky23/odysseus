import asyncio

import pytest

from services.search import core
from services.search.analytics import NetworkError, ParseError, RateLimitError
from services.search import providers
from src.agent_tools.web_tools import WebFetchTool, WebSearchTool


def _result(url, title):
    return {"url": url, "title": title, "snippet": f"snippet for {title}"}


def _setup(monkeypatch):
    results = [
        _result("https://unread.example/a", "Unread"),
        _result("https://read.example/b", "Read"),
    ]
    monkeypatch.setattr(core, "_get_search_settings", lambda: {"search_provider": "searxng"})
    monkeypatch.setattr(core, "_get_result_count", lambda: 2)
    monkeypatch.setattr(core, "_call_provider", lambda *a, **k: [dict(r) for r in results])
    monkeypatch.setattr(core, "rank_search_results", lambda q, r: r)


def test_only_successfully_fetched_pages_are_exposed_as_sources(monkeypatch):
    _setup(monkeypatch)

    def fetch(url, timeout=8, retry_attempt=0):
        if "unread" in url:
            return {"success": False, "url": url, "error": "blocked", "content": ""}
        return {
            "success": True,
            "url": url,
            "title": "Read",
            "content": "usable page content " * 30,
        }

    monkeypatch.setattr(core, "fetch_webpage_content", fetch)
    output, sources = core.comprehensive_web_search(
        "evidence contract", max_pages=2, max_workers=1, return_sources=True
    )

    assert [source["url"] for source in sources] == ["https://read.example/b"]
    assert sources[0]["evidence_status"] == "fetched"
    assert sources[0]["usable"] is True
    assert "[CONTENT 1] From: https://read.example/b" in output
    assert "[CONTENT 2]" not in output


def test_invalid_provider_urls_do_not_consume_fetch_budget(monkeypatch):
    results = [
        _result("/goto?url=opaque-provider-token", "Provider redirect"),
        _result("https://official.example/readme", "Official README"),
    ]
    monkeypatch.setattr(core, "_get_search_settings", lambda: {"search_provider": "tavily"})
    monkeypatch.setattr(core, "_get_result_count", lambda: 2)
    monkeypatch.setattr(core, "_call_provider", lambda *args, **kwargs: [dict(r) for r in results])
    monkeypatch.setattr(core, "rank_search_results", lambda query, rows: rows)
    fetched = []

    def fetch(url, timeout=8, retry_attempt=0):
        fetched.append(url)
        return {
            "success": True,
            "url": url,
            "title": "Official README",
            "content": "verified readme body " * 40,
        }

    monkeypatch.setattr(core, "fetch_webpage_content", fetch)

    _, sources = core.comprehensive_web_search(
        "official README",
        max_pages=1,
        max_workers=1,
        return_sources=True,
    )

    assert fetched == ["https://official.example/readme"]
    assert [source["url"] for source in sources] == [
        "https://official.example/readme"
    ]


def test_zero_readable_pages_is_an_explicit_failure(monkeypatch):
    _setup(monkeypatch)
    monkeypatch.setattr(
        core,
        "fetch_webpage_content",
        lambda url, timeout=8, retry_attempt=0: {
            "success": False,
            "url": url,
            "error": "blocked",
            "content": "",
        },
    )

    output, sources = core.comprehensive_web_search(
        "evidence contract", max_pages=2, max_workers=1, return_sources=True
    )

    assert sources == []
    assert "could not fetch any readable pages" in output.lower()
    assert "WEB SEARCH RESULTS AND FETCHED CONTENT" not in output


def test_web_tool_fails_closed_when_search_has_no_usable_sources(monkeypatch):
    monkeypatch.setattr(
        "src.search.comprehensive_web_search",
        lambda *args, **kwargs: (
            "Web search found candidate results but could not fetch any readable pages.",
            [],
        ),
    )

    result = asyncio.run(WebSearchTool().execute("검색 질의", {}))

    assert result["exit_code"] == 1
    assert result["error_code"] == "no_usable_sources"
    assert "error" in result


def test_web_search_success_returns_marker_without_single_fetch_fields(monkeypatch):
    sources = [{
        "url": "https://official.example/source",
        "title": "Official source",
        "evidence_status": "fetched",
        "fetched": True,
        "usable": True,
    }]
    monkeypatch.setattr(
        "src.search.comprehensive_web_search",
        lambda *args, **kwargs: ("[CONTENT 1] official body", sources),
    )

    result = asyncio.run(WebSearchTool().execute("공식 자료 검색", {}))

    assert result["exit_code"] == 0
    assert "<!-- SOURCES:" in result["output"]
    assert "web_source" not in result


@pytest.mark.parametrize("query", ["", "가" * 2001])
def test_web_search_rejects_empty_or_oversized_queries_without_provider_call(monkeypatch, query):
    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not run for an invalid query")

    monkeypatch.setattr("src.search.comprehensive_web_search", should_not_run)

    result = asyncio.run(WebSearchTool().execute(query, {}))

    assert result["exit_code"] == 1
    assert result["error_code"] == "invalid_request"
    assert called is False


@pytest.mark.parametrize(
    ("fetch_error", "expected"),
    [
        ("Rate limit hit (HTTP 429)", "rate_limited"),
        ("NetworkError: connection reset", "network_error"),
        ("HTTP 503: unavailable", "http_error"),
        ("ParseError: malformed HTML", "provider_parse_error"),
        ("TooLarge: body exceeds cap", "too_large"),
    ],
)
def test_web_fetch_returns_typed_safe_failures(monkeypatch, fetch_error, expected):
    monkeypatch.setattr(
        "src.search.content.fetch_webpage_content",
        lambda *args, **kwargs: {"content": "", "title": "", "error": fetch_error},
    )

    result = asyncio.run(WebFetchTool().execute("https://example.com", {}))

    assert result["exit_code"] == 1
    assert result["error_code"] == expected
    assert "connection reset" not in result["error"]
    assert "malformed HTML" not in result["error"]


def test_web_fetch_runtime_failure_does_not_expose_exception_text(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret upstream diagnostic")

    monkeypatch.setattr("src.search.content.fetch_webpage_content", fail)

    result = asyncio.run(WebFetchTool().execute("https://example.com", {}))

    assert result["exit_code"] == 1
    assert result["error_code"] == "runtime_error"
    assert result["diagnostic_type"] == "RuntimeError"
    assert "secret upstream diagnostic" not in result["error"]


def test_web_fetch_success_returns_verified_source_metadata(monkeypatch):
    monkeypatch.setattr(
        "src.search.content.fetch_webpage_content",
        lambda *args, **kwargs: {
            "content": "official body",
            "title": "Official source",
            "error": None,
        },
    )

    result = asyncio.run(WebFetchTool().execute("https://official.example/source", {}))

    assert result["exit_code"] == 0
    assert result["web_source"] == {
        "url": "https://official.example/source",
        "title": "Official source",
        "evidence_status": "fetched",
        "fetched": True,
        "usable": True,
    }


def test_web_tool_distinguishes_no_results_from_runtime_failure(monkeypatch):
    monkeypatch.setattr(
        "src.search.comprehensive_web_search",
        lambda *args, **kwargs: ("No search results found.", []),
    )
    no_results = asyncio.run(WebSearchTool().execute("검색 질의", {}))
    assert no_results["error_code"] == "no_results"

    def fail(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr("src.search.comprehensive_web_search", fail)
    runtime = asyncio.run(WebSearchTool().execute("검색 질의", {}))
    assert runtime["exit_code"] == 1
    assert runtime["error_code"] == "runtime_error"


def test_comprehensive_search_reports_rate_limit_separately(monkeypatch):
    monkeypatch.setattr(core, "_get_search_settings", lambda: {"search_provider": "searxng"})
    monkeypatch.setattr(core, "_get_result_count", lambda: 2)
    monkeypatch.setattr(core, "_build_provider_chain", lambda provider: [provider])

    def rate_limited(*args, **kwargs):
        raise RateLimitError("rate limited")

    monkeypatch.setattr(core, "_call_provider", rate_limited)

    output, sources = core.comprehensive_web_search(
        "rate limited query", return_sources=True
    )

    assert sources == []
    assert "429" in output
    assert "rate limit" in output.lower()


def test_web_tool_maps_rate_limit_to_distinct_error_code(monkeypatch):
    monkeypatch.setattr(
        "src.search.comprehensive_web_search",
        lambda *args, **kwargs: ("Web search rate limited (HTTP 429).", []),
    )

    result = asyncio.run(WebSearchTool().execute("검색 질의", {}))

    assert result["exit_code"] == 1
    assert result["error_code"] == "rate_limited"


class _Response:
    def __init__(self, *, status_code=200, json_error=None):
        self.status_code = status_code
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            request = __import__("httpx").Request("GET", "https://provider.test")
            response = __import__("httpx").Response(self.status_code, request=request)
            raise __import__("httpx").HTTPStatusError("provider failure", request=request, response=response)

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return {}


def test_actual_brave_rate_limit_survives_provider_boundary(monkeypatch):
    monkeypatch.setattr(providers, "_safesearch_for", lambda *_: None)
    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: _Response(status_code=429))
    result = providers._brave_search_impl(
        "비식별 질의", 3, search_config={"brave_api_key": "test-key"}
    )
    assert result == []
    assert isinstance(result.provider_error, RateLimitError)


def test_default_searxng_rate_limit_survives_json_and_html_fallback(monkeypatch):
    monkeypatch.setattr(providers, "_get_search_instance", lambda: "https://searx.test")
    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: _Response(status_code=429))
    result = providers.searxng_search_api("비식별 질의", count=3)
    assert result == []
    assert isinstance(result.provider_error, RateLimitError)


def test_actual_provider_timeout_survives_provider_boundary(monkeypatch):
    import httpx

    monkeypatch.setattr(providers, "_safesearch_for", lambda *_: None)

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(providers.httpx, "get", timeout)
    result = providers._brave_search_impl(
        "비식별 질의", 3, search_config={"brave_api_key": "test-key"}
    )
    assert result == []
    assert isinstance(result.provider_error, NetworkError)


def test_actual_provider_invalid_json_survives_provider_boundary(monkeypatch):
    import json

    monkeypatch.setattr(providers, "_safesearch_for", lambda *_: None)
    monkeypatch.setattr(
        providers.httpx,
        "get",
        lambda *a, **k: _Response(
            json_error=json.JSONDecodeError("bad", "<html>", 0)
        ),
    )
    result = providers._brave_search_impl(
        "비식별 질의", 3, search_config={"brave_api_key": "test-key"}
    )
    assert result == []
    assert isinstance(result.provider_error, ParseError)


def test_tavily_drops_internal_relative_redirects(monkeypatch):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": "Provider redirect",
                        "url": "/goto?url=opaque-provider-token",
                        "content": "not a public candidate",
                    },
                    {
                        "title": "Official README",
                        "url": "https://github.com/openai/codex",
                        "content": "public candidate",
                    },
                ]
            }

    monkeypatch.setattr(providers, "_get_provider_key", lambda *_: "test-key")
    monkeypatch.setattr(providers.httpx, "post", lambda *args, **kwargs: Response())

    results = providers.tavily_search("official README", count=5)

    assert [result["url"] for result in results] == [
        "https://github.com/openai/codex"
    ]


def test_core_re_raises_typed_provider_failure(monkeypatch):
    failure = providers.ProviderFailureResults(RateLimitError("limited"))
    monkeypatch.setattr(core, "brave_search", lambda *a, **k: failure)
    with pytest.raises(RateLimitError):
        core._call_provider("brave", "비식별 질의", 3)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Web search network error. Tried: brave:network_error", "network_error"),
        ("Web search provider response could not be parsed. Tried: brave:parse_error", "provider_parse_error"),
        ("Web search failed — provider/runtime error. Tried: brave:provider_error", "provider_error"),
    ],
)
def test_web_tool_preserves_provider_failure_class(monkeypatch, message, expected):
    monkeypatch.setattr(
        "src.search.comprehensive_web_search",
        lambda *args, **kwargs: (message, []),
    )
    result = asyncio.run(WebSearchTool().execute("검색 질의", {}))
    assert result["error_code"] == expected
