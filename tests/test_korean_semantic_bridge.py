import json
from pathlib import Path

import pytest

from src.korean_semantics import (
    detect_korean_domains,
    is_korean_casual_low_signal,
    is_korean_contextual_followup,
    is_korean_explicit_continuation,
    is_korean_explanatory_question,
    is_korean_repair_followup,
    is_korean_web_intent,
    looks_like_korean_action_promise,
)


_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "korean_semantic_turns.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("text", _CASES["direct_web"])
def test_direct_korean_web_requests_are_detected(text):
    assert is_korean_web_intent(text)
    assert "web" in detect_korean_domains(text)


@pytest.mark.parametrize("text", _CASES["web_continuations"])
def test_korean_followups_inherit_only_when_recent_context_is_web(text):
    recent = "사용자가 최신 AI 뉴스를 웹에서 검색했고 출처를 비교했습니다."
    assert is_korean_contextual_followup(text, recent)
    assert not is_korean_contextual_followup(text, "어제 저녁 메뉴를 이야기했습니다.")


@pytest.mark.parametrize("text", _CASES["explanatory"])
def test_korean_feature_questions_do_not_become_tool_actions(text):
    assert is_korean_explanatory_question(text)
    assert not is_korean_web_intent(text)


@pytest.mark.parametrize("text", _CASES["casual"])
def test_korean_casual_turns_are_low_signal(text):
    assert is_korean_casual_low_signal(text)


@pytest.mark.parametrize("text", _CASES["topic_switch"])
def test_complete_new_korean_topic_does_not_inherit_old_web_task(text):
    recent = "최신 뉴스를 검색하고 출처를 확인했습니다."
    assert not is_korean_contextual_followup(text, recent)


@pytest.mark.parametrize(
    "text",
    [
        "제가 지금 웹에서 검색해 보겠습니다.",
        "관련 자료를 실제로 확인해볼게요.",
        "잠시만요, 최신 결과를 찾아보겠습니다.",
    ],
)
def test_korean_future_tense_tool_promises_are_detected(text):
    assert looks_like_korean_action_promise(text)


def test_korean_domain_detection_covers_native_odysseus_actions():
    assert detect_korean_domains("받은 메일을 확인하고 답장해줘") == {"email"}
    assert detect_korean_domains("내일 오후 일정에 회의를 추가해줘") == {
        "notes_calendar_tasks"
    }
    assert detect_korean_domains("이 보고서를 Documents 문서로 저장해줘") == {
        "documents"
    }
    assert detect_korean_domains("이 레포의 테스트를 실행해줘") == {"files"}
    assert detect_korean_domains("대한민국헌법 제10조의 공식 법률 근거를 확인해줘") == {
        "legal"
    }
    assert detect_korean_domains("지급 지연에 관한 대법원 판례를 찾아줘") == {
        "legal"
    }


@pytest.mark.parametrize(
    "text",
    [
        "예전에 계약서에 대해 나눈 대화를 찾아줘",
        "과거 채팅에서 민법 이야기를 검색해줘",
        "이전에 지급 조건을 논의했던 대화 기록을 보여줘",
    ],
)
def test_korean_past_conversation_search_routes_to_sessions_not_web(text):
    domains = detect_korean_domains(text)

    assert "sessions" in domains
    assert "web" not in domains


def test_generic_korean_continuation_is_available_to_non_web_agent_domains():
    assert is_korean_explicit_continuation("네, 그렇게 해주세요.")
    assert is_korean_explicit_continuation("방금 내용 그대로 진행해줘.")
    assert not is_korean_explicit_continuation(
        "그런데 파이썬의 GIL이 무엇인지 설명해 주세요."
    )


@pytest.mark.parametrize(
    "text",
    [
        "제대로 피드백을 못하신듯 마지막 질문에 대한",
        "위의 맥락이 이상한데 질문에 답이 아닌듯",
        "직전 답변이 제 질문을 놓쳤습니다.",
        "방금 요청을 웹검색을 사용해 실제로 다시 시도해 주세요.",
    ],
)
def test_korean_repair_turns_are_explicit_continuations(text):
    assert is_korean_repair_followup(text)
    assert is_korean_explicit_continuation(text)


@pytest.mark.parametrize(
    "text",
    [
        "그렇다면 중복 문서는 어떻게 처리하나요?",
        "그중 검토 큐는 왜 필요한가요?",
        "이 경우 기존 근거는 유지되나요?",
    ],
)
def test_korean_contextual_questions_continue_the_current_topic(text):
    assert is_korean_explicit_continuation(text)
