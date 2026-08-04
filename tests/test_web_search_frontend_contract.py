from pathlib import Path


CHAT_JS = (
    Path(__file__).resolve().parent.parent / "static" / "js" / "chat.js"
).read_text(encoding="utf-8")


def test_agent_step_removes_empty_buffered_continuation_cards():
    assert "roundHolder.classList.contains('msg-continuation')" in CHAT_JS
    assert "&& !roundText.trim()" in CHAT_JS
    assert "roundHolder.remove();" in CHAT_JS


def test_web_completion_failure_never_renders_internal_guard_codes():
    assert "json.type === 'web_completion_failed'" in CHAT_JS
    assert "검색 근거를 최종 답변에 연결하지 못했습니다" in CHAT_JS
    assert "[Agent guard:" not in CHAT_JS
