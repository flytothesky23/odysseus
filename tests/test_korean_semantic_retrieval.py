from services.search.query import (
    _cache_duration_for_query,
    _detect_question_type,
    _is_news_query,
    enhance_query,
)
from services.search.ranking import rank_search_results
from src.korean_semantics import semantic_tokens
from src.memory import MemoryManager, get_text_similarity
from src.agent_loop import _AGENT_RULES, _API_AGENT_RULES, _DOMAIN_RULES
from src.tool_index import ToolIndex


def test_korean_particles_do_not_destroy_core_terms():
    tokens = semantic_tokens("계약서를 검토해주세요. 민법상의 책임은 무엇인가요?")

    assert "계약서" in tokens
    assert "민법상" in tokens or "민법" in tokens
    assert "책임" in tokens


def test_korean_memory_similarity_handles_inflected_nouns():
    score = get_text_similarity(
        "사용자는 민법 계약서를 자주 검토합니다.",
        "민법상 계약서의 검토 내용을 찾아줘",
    )

    assert score > 0.2


def test_korean_inline_memory_command_is_recognized(tmp_path):
    manager = MemoryManager(str(tmp_path))

    matched, text = manager.process_inline_memory_command(
        "기억해줘: 나는 판례 검색 결과를 한국어로 선호해"
    )

    assert matched is True
    assert text == "나는 판례 검색 결과를 한국어로 선호해"


def test_korean_identity_query_recalls_korean_identity_memory(tmp_path):
    manager = MemoryManager(str(tmp_path))
    memories = [{"text": "내 이름은 홍길동입니다", "id": "m1"}]

    recalled = manager.get_relevant_memories("내 이름이 뭐였지?", memories)

    assert recalled
    assert recalled[0]["id"] == "m1"


def test_korean_question_type_and_query_boost_stay_korean():
    assert _detect_question_type("왜 계약 해제가 문제인가요") == "why"
    enhanced, _ = enhance_query("왜 계약 해제가 문제인가요")

    assert "이유" in enhanced
    assert "reason" not in enhanced


def test_korean_news_query_gets_short_cache_window():
    assert _is_news_query("오늘 최신 AI 뉴스") is True
    assert _cache_duration_for_query("오늘 최신 AI 뉴스").total_seconds() == 1800


def test_korean_ranking_matches_terms_despite_particles():
    results = [
        {
            "title": "여행 준비 체크리스트",
            "snippet": "휴가 일정과 짐 목록",
            "url": "https://example.test/travel",
        },
        {
            "title": "민법상 계약서 책임 검토",
            "snippet": "계약서를 검토할 때 확인할 책임 조항",
            "url": "https://example.test/contract",
        },
    ]

    ranked = rank_search_results("민법 계약서의 책임을 검토해줘", results)

    assert ranked[0]["url"].endswith("/contract")


def test_agent_prompt_preserves_latest_user_language_and_korean_entities():
    combined = "\n".join((_AGENT_RULES, _API_AGENT_RULES, _DOMAIN_RULES["web"]))

    assert "latest user turn" in combined.lower()
    assert "korean" in combined.lower()
    assert "do not translate" in combined.lower()


def test_tool_index_routes_korean_past_chat_lookup_without_embeddings():
    index = ToolIndex.__new__(ToolIndex)
    index.retrieve = lambda _query, k=8: []

    tools = index.get_tools_for_query("예전에 계약서에 대해 나눈 대화를 찾아줘")

    assert "search_chats" in tools
    assert "list_sessions" in tools
    assert "web_search" not in tools


def test_tool_index_routes_korean_native_app_actions_without_translation():
    index = ToolIndex.__new__(ToolIndex)
    index.retrieve = lambda _query, k=8: []

    assert "manage_calendar" in index.get_tools_for_query("내일 일정을 확인해줘")
    assert "manage_notes" in index.get_tools_for_query("할 일 메모를 추가해줘")
    assert "manage_documents" in index.get_tools_for_query("저장된 보고서를 열어줘")
    assert "ui_control" in index.get_tools_for_query("메모 패널을 열어줘")


def test_tool_index_routes_korean_legal_request_to_safe_bridge_only():
    index = ToolIndex.__new__(ToolIndex)
    index.retrieve = lambda _query, k=8: []

    tools = index.get_tools_for_query("대한민국헌법 제10조의 공식 법률 근거를 확인해줘")

    assert "korean_law_lookup" in tools
    assert not any(name.startswith("mcp__") for name in tools)
