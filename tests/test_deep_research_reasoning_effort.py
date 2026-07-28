import pytest

from src.deep_research import DeepResearcher
from src.research_handler import ResearchHandler


@pytest.mark.asyncio
async def test_deep_research_forwards_reasoning_effort(monkeypatch):
    captured = {}

    async def fake_llm_call_async(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("src.llm_core.llm_call_async", fake_llm_call_async)

    researcher = DeepResearcher(
        llm_endpoint="http://local.test/v1/chat/completions",
        llm_model="local-model",
        reasoning_effort="high",
    )

    response = await researcher._llm([{"role": "user", "content": "hi"}])

    assert response == "ok"
    assert researcher.reasoning_effort == "high"
    assert captured["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_deep_research_drops_invalid_reasoning_effort(monkeypatch):
    captured = {}

    async def fake_llm_call_async(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr("src.llm_core.llm_call_async", fake_llm_call_async)

    researcher = DeepResearcher(
        llm_endpoint="http://local.test/v1/chat/completions",
        llm_model="local-model",
        reasoning_effort="expensive",
    )

    await researcher._llm([{"role": "user", "content": "hi"}])

    assert researcher.reasoning_effort is None
    assert captured["reasoning_effort"] is None


@pytest.mark.asyncio
async def test_research_handler_passes_normalized_reasoning_effort(monkeypatch):
    captured = {}

    class FakeDeepResearcher:
        findings = []
        evolving_report = ""

        def __init__(self, reasoning_effort=None, **kwargs):
            captured.update(kwargs)
            captured["reasoning_effort"] = reasoning_effort

        async def research(self, query, prior_report="", prior_findings=None, prior_urls=None):
            return "final report"

        def get_stats(self):
            return {"Rounds": 1, "Queries": 1, "URLs": 0}

    async def fake_probe(endpoint, model, headers=None):
        return None

    monkeypatch.setattr("src.deep_research.DeepResearcher", FakeDeepResearcher)
    monkeypatch.setattr(ResearchHandler, "_probe_endpoint", staticmethod(fake_probe))

    handler = ResearchHandler.__new__(ResearchHandler)
    handler._legacy_engine = None
    handler._active_tasks = {}

    result = await handler.call_research_service(
        "query",
        "http://local.test/v1/chat/completions",
        "local-model",
        reasoning_effort="HIGH",
    )

    assert "final report" in result
    assert captured["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_research_handler_drops_invalid_reasoning_effort(monkeypatch):
    captured = {}

    class FakeDeepResearcher:
        findings = []
        evolving_report = ""

        def __init__(self, reasoning_effort=None, **kwargs):
            captured.update(kwargs)
            captured["reasoning_effort"] = reasoning_effort

        async def research(self, query, prior_report="", prior_findings=None, prior_urls=None):
            return "final report"

        def get_stats(self):
            return {"Rounds": 1, "Queries": 1, "URLs": 0}

    async def fake_probe(endpoint, model, headers=None):
        return None

    monkeypatch.setattr("src.deep_research.DeepResearcher", FakeDeepResearcher)
    monkeypatch.setattr(ResearchHandler, "_probe_endpoint", staticmethod(fake_probe))

    handler = ResearchHandler.__new__(ResearchHandler)
    handler._legacy_engine = None
    handler._active_tasks = {}

    await handler.call_research_service(
        "query",
        "http://local.test/v1/chat/completions",
        "local-model",
        reasoning_effort="expensive",
    )

    assert captured["reasoning_effort"] is None


@pytest.mark.parametrize("effort", ["none", "minimal", "low", "medium", "high", "xhigh"])
def test_research_reasoning_effort_accepts_supported_values(effort):
    from src.deep_research import _normalize_reasoning_effort
    from src.research_handler import normalize_reasoning_effort

    assert _normalize_reasoning_effort(effort.upper()) == effort
    assert normalize_reasoning_effort(effort.upper()) == effort


@pytest.mark.asyncio
async def test_generate_plan_supplies_default_source_instruction(monkeypatch):
    captured = {}

    async def fake_llm_call_async(**kwargs):
        captured.update(kwargs)
        return '{"sub_questions":[],"key_topics":[],"success_criteria":"ok"}'

    monkeypatch.setattr("src.llm_core.llm_call_async", fake_llm_call_async)
    handler = ResearchHandler.__new__(ResearchHandler)

    result = await handler.generate_plan(
        "current operations",
        "http://local.test/v1/chat/completions",
        "local-model",
    )

    assert result["success_criteria"] == "ok"
    assert "Use external web sources only" in captured["messages"][0]["content"]
