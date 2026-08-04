import asyncio

import pytest

from src.agent_tools.web_tools import WebSearchTool


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("오늘 AI 주요 뉴스를 검색해줘", "day"),
        ("현재 Codex 최신 버전은?", "day"),
        ("이번 주 MCP 동향", "week"),
        ("최근 며칠간 한국 AI 정책", "week"),
        ("이번 달 OpenAI 업데이트", "month"),
    ],
)
def test_korean_freshness_terms_select_time_filter(monkeypatch, query, expected):
    captured = {}

    def fake_search(search_query, **kwargs):
        captured.update(query=search_query, **kwargs)
        return (
            "fetched evidence",
            [{
                "url": "https://example.test/source",
                "title": "Source",
                "evidence_status": "fetched",
                "fetched": True,
                "usable": True,
            }],
        )

    monkeypatch.setattr("src.search.comprehensive_web_search", fake_search)

    result = asyncio.run(WebSearchTool().execute(query, {}))

    assert result["exit_code"] == 0
    assert captured["time_filter"] == expected
