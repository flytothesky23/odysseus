import pytest

from src.deep_research import DeepResearcher


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
