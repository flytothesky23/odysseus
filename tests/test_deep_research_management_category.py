import asyncio
import json
import sys
import types

from src.deep_research import CATEGORY_PROMPTS, DeepResearcher
from src.visual_report import generate_visual_report


def _researcher(**kwargs):
    return DeepResearcher(
        llm_endpoint="http://local.test/v1/chat/completions",
        llm_model="local-model",
        **kwargs,
    )


def test_management_category_is_registered_for_manual_and_auto_use():
    prompt = CATEGORY_PROMPTS["management"]

    assert "MANAGEMENT ANALYSIS" in prompt
    assert "경영 요약" in prompt
    assert "PSBall" in prompt
    assert "관리 Check Point" in prompt


def test_auto_management_classification_runs_before_planning():
    researcher = _researcher(max_rounds=0)
    seen = []

    async def fake_llm(messages, **kwargs):
        prompt = messages[0]["content"]
        seen.append(prompt)
        if "Classify this research question" in prompt:
            return "management"
        return json.dumps({
            "sub_questions": ["손익과 운영 KPI는 무엇인가?"],
            "key_topics": ["PSBall", "현금흐름"],
            "success_criteria": "경영 판단과 Check Point가 포함된 보고서",
        })

    researcher._llm = fake_llm

    asyncio.run(researcher.research("사업보고서와 주간 경영분석보고서를 작성해줘"))

    assert researcher.category == "management"
    assert any("Category meanings" in prompt and "management" in prompt for prompt in seen)
    plan_prompt = next(prompt for prompt in seen if "research strategist" in prompt)
    assert "Management Analysis Report mode" in plan_prompt
    assert "financial-statement" in plan_prompt
    assert "PSBall" in plan_prompt


def test_management_query_generation_gets_metric_source_pack_guidance():
    researcher = _researcher(category="management")
    researcher.research_plan = "plan"
    researcher.queries_used = set()
    seen = {}

    async def fake_llm(messages, **kwargs):
        seen["prompt"] = messages[0]["content"]
        return json.dumps(["PSBall 주간 공급가액 운임비율", "함안 청남 부산물 판매실적"])

    researcher._llm = fake_llm

    queries = asyncio.run(researcher._generate_queries("W24 경영분석", "", 1))

    assert queries
    assert "source packs" in seen["prompt"]
    assert "PSBall" in seen["prompt"]
    assert "슬래그반출" in seen["prompt"]
    assert "운임" in seen["prompt"]
    assert "장비시간" in seen["prompt"]


def test_management_extraction_goal_requests_period_value_and_baseline(monkeypatch):
    search_mod = types.ModuleType("src.search")

    def fake_fetch_webpage_content(url, timeout):
        return {
            "success": True,
            "content": "W24 PSBall 공급가액 82.24백만원, 운임비율 9.4%",
            "title": "W24",
            "og_image": "",
        }

    search_mod.fetch_webpage_content = fake_fetch_webpage_content
    monkeypatch.setitem(sys.modules, "src.search", search_mod)

    async def immediate_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", immediate_to_thread)

    researcher = _researcher(category="management")
    seen = {}

    async def fake_llm(messages, **kwargs):
        seen["goal"] = messages[0]["content"]
        return json.dumps({
            "rational": "management metric evidence",
            "evidence": "W24 PSBall 공급가액 82.24백만원, 운임비율 9.4%",
            "summary": "W24 metric",
        })

    researcher._llm = fake_llm

    result = asyncio.run(researcher._fetch_and_extract("https://example.test/w24", "W24 경영분석", "W24"))

    assert result["summary"] == "W24 metric"
    assert "period, value, unit, baseline" in seen["goal"]
    assert "공급가액 대비 운임비율" in seen["goal"]
    assert "Haman/Cheongnam" in seen["goal"]


def test_management_synthesis_stop_and_final_prompts_include_contract():
    researcher = _researcher(category="management")
    seen = []

    async def fake_llm(messages, **kwargs):
        prompt = messages[0]["content"]
        seen.append(prompt)
        if "deciding whether" in prompt:
            return "NO — missing management checkpoints."
        return "## 경영 요약\n\n본문"

    researcher._llm = fake_llm

    asyncio.run(researcher._synthesize(
        "W24 경영분석",
        [{"title": "note", "url": "vault://note", "summary": "PSBall"}],
        "",
    ))
    asyncio.run(researcher._should_stop("W24 경영분석", "보고서", 2))
    asyncio.run(researcher._final_report("W24 경영분석", "보고서"))

    joined = "\n\n".join(seen)
    assert "evolving management ledger" in joined
    assert "relevant axes" in joined
    assert "Executive Brief" in joined
    assert "종합의견 및 관리 Check Point" in joined


def test_visual_report_has_management_category_skin():
    html = generate_visual_report(
        "W24 경영분석",
        "## 경영 요약\n\n| 지표 | 값 |\n|---|---:|\n| PSBall 공급가액 | 82.24백만원 |",
        category="management",
    )

    assert 'class="category-management"' in html
    assert "Management analysis category" in html
    assert "font-variant-numeric: tabular-nums" in html
