from src.action_intents import classify_tool_intent, message_needs_tools


def test_calendar_entry_request_promotes_to_agent():
    assert message_needs_tools("Can you add an entry to my calendar?")
    intent = classify_tool_intent("Can you add an entry to my calendar?")
    assert intent.needs_tools
    assert intent.category == "calendar"


def test_calendar_imperative_variants_promote_to_agent():
    assert message_needs_tools("add lunch with Sam to my calendar tomorrow at noon")
    assert message_needs_tools("schedule a call with Mina next Friday")
    assert message_needs_tools("put dentist appointment on my calendar")
    assert message_needs_tools("Alright. Recreate that same appointment")
    assert message_needs_tools("Okay delete that doctor appointment from the calendar")
    assert message_needs_tools("have another go at adding a test entry to the calendar")
    assert message_needs_tools(
        "Okay so you should be able to create that calendar event for tomorrow at 1:30 p.m. right for me to go to the hardware store"
    )
    assert message_needs_tools(
        "make it an appointment at 12pm for me to visit the doctor it's tomorrow the 2nd of June 2026"
    )


def test_calendar_read_requests_promote_to_agent():
    assert message_needs_tools("What upcoming events do I have?")
    assert message_needs_tools("Can you show my next appointments?")
    assert message_needs_tools("Do I have upcoming Taekwondo classes this week?")
    assert message_needs_tools("What's on my calendar tomorrow?")
    assert message_needs_tools("When is my next meeting?")


def test_note_todo_and_reminder_actions_promote_to_agent():
    assert message_needs_tools("add milk to my todo list")
    assert message_needs_tools("take a note that the server needs checking")
    assert message_needs_tools("set a reminder to call Pat at 4pm")


def test_email_and_ui_actions_promote_to_agent():
    assert message_needs_tools("reply to that email")
    assert message_needs_tools("mark those emails as read")
    assert message_needs_tools("open my calendar")
    assert message_needs_tools("turn off web search")


def test_research_action_promotes_to_agent():
    assert message_needs_tools("research cost effective local models")
    assert message_needs_tools("can you look into GPU hosting options")


def test_explicit_web_search_promotes_to_agent():
    assert message_needs_tools("use web search and find a recipe for chocolate chip cookies")
    assert message_needs_tools("do a web search for the best chocolate chip cookies")
    assert message_needs_tools("search the web for current RTX 3090 prices")
    assert classify_tool_intent("use web search and find a recipe").category == "web"


def test_korean_web_search_promotes_to_agent_but_explanation_does_not():
    for prompt in (
        "웹에서 최신 Codex 릴리스를 검색해 주세요",
        "오늘 서울 날씨를 실제로 찾아봐",
        "현재 원달러 환율을 확인해줘",
    ):
        intent = classify_tool_intent(prompt)
        assert intent.needs_tools
        assert intent.category == "web"

    explanation = classify_tool_intent("웹검색은 어떻게 사용하나요?")
    assert not explanation.needs_tools


def test_korean_native_actions_promote_to_matching_tool_family():
    expected = {
        "내일 오후 일정에 회의를 추가해줘": "calendar",
        "메모에 우유 사기라고 저장해줘": "notes",
        "받은 메일에 답장해줘": "email",
        "이 레포의 테스트를 실행해줘": "workspace",
    }
    for prompt, category in expected.items():
        intent = classify_tool_intent(prompt)
        assert intent.needs_tools, prompt
        assert intent.category == category


def test_korean_pinned_note_analysis_stays_in_chat_instead_of_mutating_notes():
    prompts = (
        "고정된 메모의 파싱 문서만 근거로 지급기한을 요약하세요.",
        "선택한 노트 내용을 바탕으로 핵심 쟁점을 분석해 주세요.",
        "첨부 문서에 적힌 사실만 정리하고 없는 내용은 추측하지 마세요.",
    )

    for prompt in prompts:
        intent = classify_tool_intent(prompt)
        assert not intent.needs_tools, prompt
        assert intent.reason == "Korean local-evidence analysis request"


def test_korean_legal_questions_promote_to_official_law_agent():
    for prompt in (
        "대한민국헌법 제10조 공식 원문을 확인해줘",
        "계약 조항을 관련 법조문과 판례로 법적 분석해 주세요",
        "민법 제390조가 이 사안에 어떻게 적용되나요?",
    ):
        intent = classify_tool_intent(prompt)
        assert intent.needs_tools, prompt
        assert intent.category == "legal"

    feature_help = classify_tool_intent("Korean Law MCP는 어떻게 사용하나요?")
    assert not feature_help.needs_tools


def test_workspace_agent_requests_promote_to_shell_workspace():
    prompts = [
        "fix the bug in this repo",
        "run the tests for this project",
        "debug the server logs",
        "run terminal-bench on this task",
        "inspect the traceback and patch the code",
    ]
    for prompt in prompts:
        intent = classify_tool_intent(prompt)
        assert intent.needs_tools
        assert intent.category == "workspace"


def test_explanatory_calendar_questions_stay_plain_chat():
    assert not message_needs_tools("How do I add an entry to my calendar?")
    assert not message_needs_tools("What about the built-in Odysseus calendar, is that linked to email?")
    assert not message_needs_tools("Can you explain how calendar reminders work?")
    intent = classify_tool_intent("How do I add an entry to my calendar?")
    assert not intent.needs_tools
    assert intent.reason == "explanatory feature question"


def test_router_reports_non_calendar_categories():
    assert classify_tool_intent("reply to that email").category == "email"
    assert classify_tool_intent("open my calendar").category == "ui"
    assert classify_tool_intent("research cost effective local models").category == "research"
