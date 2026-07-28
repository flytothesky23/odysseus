"""Static contract for chat model reasoning controls."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_composer_exposes_reasoning_control_and_sends_selected_effort():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    picker_js = (ROOT / "static" / "js" / "modelPicker.js").read_text(encoding="utf-8")
    chat_js = (ROOT / "static" / "js" / "chat.js").read_text(encoding="utf-8")
    sessions_js = (ROOT / "static" / "js" / "sessions.js").read_text(encoding="utf-8")

    assert 'id="model-picker-reasoning"' in html
    assert "model_reasoning_efforts" in picker_js
    assert "model_default_reasoning_efforts" in picker_js
    assert "getSelectedReasoningEffort" in chat_js
    assert "fd.append('reasoning_effort', selectedReasoningEffort)" in chat_js
    assert (
        "./modelPicker.js?v=20260728codexreasoning1" in chat_js
        and "./modelPicker.js?v=20260728codexreasoning1" in sessions_js
    )
    assert "ultra" not in picker_js.lower()
