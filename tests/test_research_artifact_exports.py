import json

from src import research_handler
from src.research_handler import (
    ResearchHandler,
    normalize_artifact_formats,
    normalize_reasoning_effort,
)


def _handler(tmp_path, monkeypatch):
    data_dir = tmp_path / "deep_research"
    data_dir.mkdir()
    monkeypatch.setattr(research_handler, "RESEARCH_DATA_DIR", data_dir)
    handler = ResearchHandler.__new__(ResearchHandler)
    handler._active_tasks = {}
    return handler, data_dir


def _write_result(data_dir, session_id="rp-export"):
    data = {
        "query": "대한민국헌법 제10조 분석",
        "status": "done",
        "result": "## Research Summary\n\n본문 보고서",
        "raw_report": "# 원문 보고서",
        "sources": [
            {
                "title": "헌법 전문",
                "url": "vault://21_업무노트/헌법.md#chunk-0",
                "source_type": "obsidian",
                "source_path": "21_업무노트/헌법.md",
            },
            {"title": "Court", "url": "https://example.com/court"},
        ],
        "raw_findings": [
            {
                "title": "내부 노트",
                "url": "vault://21_업무노트/헌법.md#chunk-0",
                "summary": "인간의 존엄과 행복추구권을 설명한 노트",
                "source_type": "obsidian",
                "source_path": "21_업무노트/헌법.md",
            }
        ],
        "stats": {"Duration": "12.3s", "Rounds": 2, "Queries": 4, "URLs": 3},
        "category": "factcheck",
        "source_mode": "knowledge",
        "knowledge_folders": ["obsidian:21_업무노트"],
        "artifact_formats": ["md_json", "html"],
        "reasoning_effort": "high",
        "started_at": 100,
        "completed_at": 200,
        "owner": "alice",
    }
    (data_dir / f"{session_id}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def test_normalize_artifact_formats_aliases_and_defaults():
    assert normalize_artifact_formats(None) == ["html"]
    assert normalize_artifact_formats(["markdown", "json", "visual"]) == ["md_json", "html"]
    assert normalize_artifact_formats(["unknown"]) == ["html"]


def test_normalize_reasoning_effort_drops_invalid_values():
    assert normalize_reasoning_effort("HIGH") == "high"
    assert normalize_reasoning_effort(" medium ") == "medium"
    assert normalize_reasoning_effort("expensive") is None


def test_markdown_export_is_obsidian_friendly(tmp_path, monkeypatch):
    handler, data_dir = _handler(tmp_path, monkeypatch)
    _write_result(data_dir)

    markdown = handler.get_report_markdown("rp-export")

    assert "codexian_provider: odysseus-local" in markdown
    assert 'odysseus_session_id: "rp-export"' in markdown
    assert "# 대한민국헌법 제10조 분석" in markdown
    assert "- Markdown 리포트: `/api/research/report/rp-export/markdown`" in markdown
    assert "- 세션 JSON: `/api/research/report/rp-export/session.json`" in markdown
    assert "- 추론 정도: `high`" in markdown
    assert 'reasoning_effort: "high"' in markdown
    assert "## Research Summary" in markdown
    assert "1. [헌법 전문](vault://21_업무노트/헌법.md#chunk-0) `obsidian` `21_업무노트/헌법.md`" in markdown
    assert "## Raw Findings" in markdown
    assert "인간의 존엄과 행복추구권" in markdown


def test_session_json_export_omits_owner_and_includes_artifact_urls(tmp_path, monkeypatch):
    handler, data_dir = _handler(tmp_path, monkeypatch)
    _write_result(data_dir)

    exported = handler.get_report_session_export("rp-export")

    assert exported["session_id"] == "rp-export"
    assert exported["query"] == "대한민국헌법 제10조 분석"
    assert exported["artifact_formats"] == ["md_json", "html"]
    assert exported["reasoning_effort"] == "high"
    assert exported["artifact_urls"]["markdown"] == "/api/research/report/rp-export/markdown"
    assert exported["artifact_urls"]["json"] == "/api/research/report/rp-export/session.json"
    assert "owner" not in exported
