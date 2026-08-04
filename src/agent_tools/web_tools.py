import asyncio
import inspect
import json
import time
from typing import Dict, Any

from src.constants import MAX_OUTPUT_CHARS


_MAX_WEB_QUERY_CHARS = 2000
_MAX_WEB_URL_CHARS = 2048


def _failure(message: str, code: str, **diagnostics: Any) -> dict:
    return {
        "error": message,
        "error_code": code,
        "exit_code": 1,
        **diagnostics,
    }


def _classify_fetch_error(error: str) -> tuple[str, str]:
    """Map untrusted fetch diagnostics to a stable, user-safe failure."""
    low = str(error or "").casefold()
    if "429" in low or "rate limit" in low:
        return "rate_limited", "웹 원문 서버가 요청을 제한했습니다(HTTP 429)."
    if "networkerror" in low or "network error" in low:
        return "network_error", "웹 원문을 가져오는 중 네트워크 오류가 발생했습니다."
    if low.startswith("http ") or "httpstatus" in low:
        return "http_error", "웹 원문 서버가 HTTP 오류를 반환했습니다."
    if "parseerror" in low or "parse error" in low:
        return "provider_parse_error", "웹 원문 응답을 안전하게 해석하지 못했습니다."
    if "toolarge" in low or "too large" in low:
        return "too_large", "웹 원문이 안전한 다운로드 한도를 초과했습니다."
    return "no_readable_content", "웹 페이지에서 읽을 수 있는 본문을 확보하지 못했습니다."


class WebSearchTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.search import comprehensive_web_search
        progress_cb = ctx.get("progress_cb") if isinstance(ctx, dict) else None
        raw = content.strip()
        query = raw
        time_filter = None
        max_pages = 5
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and "query" in parsed:
                    query = str(parsed.get("query", "")).strip()
                    tf = parsed.get("time_filter") or parsed.get("freshness")
                    if isinstance(tf, str) and tf.lower() in ("day", "week", "month", "year"):
                        time_filter = tf.lower()
                    mp = parsed.get("max_pages")
                    if isinstance(mp, int) and 1 <= mp <= 10:
                        max_pages = mp
            except json.JSONDecodeError:
                return _failure("웹 검색 인자는 올바른 JSON 객체여야 합니다.", "invalid_request")
        if not query:
            query = raw.split("\n")[0].strip()
        if not query or query.startswith("{"):
            return _failure("웹 검색 질의가 필요합니다.", "invalid_request")
        if len(query) > _MAX_WEB_QUERY_CHARS:
            return _failure("웹 검색 질의가 허용 길이를 초과했습니다.", "invalid_request")
        if time_filter is None:
            q_lc = query.lower()
            if any(kw in q_lc for kw in (
                "today", "latest", "breaking", "this morning", "right now", "currently",
                "오늘", "현재", "최신", "방금", "속보", "지금",
            )):
                time_filter = "day"
            elif any(kw in q_lc for kw in (
                "this week", "past week", "recent news", "last few days",
                "이번 주", "이번주", "최근 며칠", "주간",
            )):
                time_filter = "week"
            elif any(kw in q_lc for kw in ("this month", "past month", "이번 달", "이번달")):
                time_filter = "month"
            elif " news" in q_lc or q_lc.startswith("news ") or q_lc.endswith(" news"):
                time_filter = "week"
        loop = asyncio.get_running_loop()
        if progress_cb:
            await progress_cb({
                "elapsed_s": 0,
                "tail": f"Searching web for: {query[:160]}",
            })
        started_at = time.monotonic()
        try:
            text, sources = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: comprehensive_web_search(
                        query,
                        max_pages=max_pages,
                        time_filter=time_filter,
                        return_sources=True,
                    ),
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            return _failure("웹 검색이 30초 제한 시간을 초과했습니다.", "timeout")
        except Exception as e:
            return _failure(
                "웹 검색 중 내부 런타임 오류가 발생했습니다.",
                "runtime_error",
                diagnostic_type=type(e).__name__,
            )
        if progress_cb:
            await progress_cb({
                "elapsed_s": round(time.monotonic() - started_at, 1),
                "tail": f"Search completed; preparing {len(sources)} fetched source(s).",
            })
        if not sources:
            low = str(text or "").lower()
            if "429" in low or "rate limit" in low or "rate-limiting" in low:
                error_code = "rate_limited"
            elif "network error" in low:
                error_code = "network_error"
            elif "could not be parsed" in low or "parse_error" in low:
                error_code = "provider_parse_error"
            elif "disabled" in low:
                error_code = "disabled"
            elif "no search results" in low or "returned empty" in low:
                error_code = "no_results"
            elif "could not fetch any readable pages" in low or "no suitable results" in low:
                error_code = "no_usable_sources"
            elif "failed" in low or "errored" in low:
                error_code = "provider_error"
            else:
                error_code = "no_usable_sources"
            return _failure(
                str(text or "Web search returned no usable evidence."),
                error_code,
            )

        output = text[:MAX_OUTPUT_CHARS] if len(text) > MAX_OUTPUT_CHARS else text
        if sources:
            output += "\n\n<!-- SOURCES:" + json.dumps(sources) + " -->"
        return {"output": output, "exit_code": 0}

class WebFetchTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.search.content import fetch_webpage_content
        from src.constants import WEB_FETCH_HARD_MAX_BYTES
        raw = content.strip()
        url = ""
        max_bytes = None
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    url = str(parsed.get("url") or "").strip()
                    # Download-budget override (#3812): "full": true raises the
                    # budget to the hard cap; an explicit max_bytes is clamped
                    # to the hard cap downstream. Default stays the soft cap.
                    if parsed.get("full") is True:
                        max_bytes = WEB_FETCH_HARD_MAX_BYTES
                    mb = parsed.get("max_bytes")
                    if isinstance(mb, int) and mb > 0:
                        max_bytes = mb
            except json.JSONDecodeError:
                url = ""
        if not url:
            url = raw.split("\n")[0].strip()
        if not url or url.startswith("{") or any(c in url for c in (" ", "\t", "\n")):
            return _failure("web_fetch에는 하나의 URL 또는 도메인이 필요합니다.", "invalid_request")
        if len(url) > _MAX_WEB_URL_CHARS:
            return _failure("web_fetch URL이 허용 길이를 초과했습니다.", "invalid_request")
        low = url.lower()
        if "://" in low and not low.startswith(("http://", "https://")):
            return _failure("web_fetch는 http/https URL만 허용합니다.", "invalid_request")
        if not low.startswith(("http://", "https://")):
            url = "https://" + url
        loop = asyncio.get_running_loop()
        try:
            def _fetch():
                kwargs = {"timeout": 10}
                try:
                    sig = inspect.signature(fetch_webpage_content)
                    if "max_bytes" in sig.parameters:
                        kwargs["max_bytes"] = max_bytes
                except (TypeError, ValueError):
                    # Some deployed/test shims may not expose a signature.
                    # Prefer compatibility over failing the whole fetch.
                    pass
                return fetch_webpage_content(url, **kwargs)

            result = await asyncio.wait_for(
                loop.run_in_executor(None, _fetch),
                timeout=30,
            )
        except asyncio.TimeoutError:
            return _failure("웹 원문 조회가 제한 시간을 초과했습니다.", "timeout")
        except Exception as e:
            return _failure(
                "웹 원문 조회 중 내부 런타임 오류가 발생했습니다.",
                "runtime_error",
                diagnostic_type=type(e).__name__,
            )
        err = result.get("error")
        text = (result.get("content") or "").strip()
        title = result.get("title") or ""

        if not text:
            if err:
                error_code, message = _classify_fetch_error(str(err))
                return _failure(message, error_code)
            return _failure(
                "웹 페이지에서 읽을 수 있는 본문을 확보하지 못했습니다(JS 또는 로그인이 필요할 수 있습니다).",
                "no_readable_content",
            )

        # Tell the model when the download budget cut the body short and how
        # to get the rest, instead of silently presenting a partial page as
        # the whole thing.
        size_note = ""
        if result.get("truncated"):
            fetched = result.get("fetched_bytes") or 0
            total = result.get("total_bytes")
            total_txt = f" of {total:,} bytes" if total else ""
            size_note = (
                f"[partial content: download stopped at {fetched:,} bytes{total_txt}. "
                f'Re-call with {{"url": "{url}", "full": true}} to fetch up to '
                f"{WEB_FETCH_HARD_MAX_BYTES:,} bytes.]\n\n"
            )

        # The notice must lead the output so the MAX_OUTPUT_CHARS trim below can
        # never drop it. The title is untrusted, uncapped page content, so a
        # giant title ahead of the notice could push it out of range; keep the
        # notice first and cap the title as a second guard.
        if len(title) > 300:
            title = title[:300] + "..."
        header = (f"# {title}\n" if title else "") + f"Source: {url}\n\n"
        output = size_note + header + text
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n\n[...truncated]"
        return {
            "output": output,
            "exit_code": 0,
            "web_source": {
                "url": url,
                "title": title,
                "evidence_status": "fetched",
                "fetched": True,
                "usable": True,
            },
        }
