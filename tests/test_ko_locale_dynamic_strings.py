from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dynamic_model_search_placeholder_has_korean_translation_and_cache_bust():
    locale_js = (ROOT / "static/js/ko-locale.js").read_text(encoding="utf-8")
    assert "['Search models…', '모델 검색…']" in locale_js

    for page in ("static/index.html", "static/login.html"):
        html = (ROOT / page).read_text(encoding="utf-8")
        assert "/static/js/ko-locale.js?v=20260802ko5" in html
