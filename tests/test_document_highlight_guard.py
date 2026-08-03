from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_document_editor_skips_highlight_js_for_non_code_document_formats():
    source = (ROOT / "static" / "js" / "document.js").read_text(encoding="utf-8")

    assert "window.hljs.getLanguage(_hlLang)" in source
    assert "const _canHighlight" in source
    assert "if (_canHighlight)" in source
