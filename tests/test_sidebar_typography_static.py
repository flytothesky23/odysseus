"""Static contract for readable desktop sidebar typography."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def _rule(pattern: str) -> str:
    match = re.search(pattern + r"\s*\{(?P<body>[^}]*)\}", CSS, re.DOTALL)
    assert match, f"missing CSS rule: {pattern}"
    return match.group("body")


def test_desktop_sidebar_labels_use_readable_default_type():
    section_title = _rule(
        r"\.section-header-flex h4,\s*\.section-header-flex \.section-title"
    )
    list_label = _rule(r"\.list-item span")
    user_name = _rule(r"\.user-bar-name")

    assert re.search(r"font-size:\s*13px", section_title)
    assert re.search(r"font-size:\s*13px", list_label)
    assert re.search(r"font-size:\s*12px", user_name)


def test_desktop_sidebar_rows_grow_with_the_larger_labels():
    section_row = _rule(r"\.section-header-flex")
    list_row = _rule(r"\.list-item,\s*\.models-row")

    assert re.search(r"min-height:\s*34px", section_row)
    assert re.search(r"min-height:\s*34px", list_row)


def test_mobile_sidebar_keeps_touch_friendly_type_and_rows():
    start = CSS.index("/* Section headers — match list item sizing */")
    end = CSS.index("/* Section separator — more breathing room */", start)
    mobile_sidebar = CSS[start:end]

    assert "height: 48px !important;" in mobile_sidebar
    assert "min-height: 48px;" in mobile_sidebar
    assert mobile_sidebar.count("font-size: 14px !important;") >= 3
