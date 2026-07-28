from bs4 import BeautifulSoup

from src.visual_report import generate_visual_report


def test_visual_report_toc_links_match_rendered_heading_ids():
    report = """
# Automated Crypto Trading Bot Strategies

### **1.0 Introduction & Research Scope**

Intro body.

### **2.0 Determining the "Best" Configuration**

Configuration body.
"""

    html = generate_visual_report(
        "crypto bot strategies",
        report,
        sources=[],
        stats={},
        session_id="rp-test",
    )
    soup = BeautifulSoup(html, "html.parser")

    links = soup.select(".toc-sidebar nav a")
    assert [link.get_text(strip=True) for link in links] == [
        "1.0 Introduction & Research Scope",
        '2.0 Determining the "Best" Configuration',
    ]

    for link in links:
        target_id = link["href"].removeprefix("#")
        target = soup.find(id=target_id)
        assert target is not None
        assert target.name in {"h2", "h3"}


def test_management_visual_report_uses_wide_scrollable_tables():
    html = generate_visual_report(
        "W24 경영분석",
        (
            "## 경영 요약\n\n"
            "- PSBall 공급가액 82.24백만원\n"
            "- 공급가액 대비 운임비율 9.4%\n\n"
            "## 운송 route 보드\n\n"
            "| 차량군 | 운송품목 | 거리대 | 내부 ROUTE | 기간 물량 | 거리 | 내부 원/T | 내부 원/T·KM | 선정 유사자료 | 관리 메모 |\n"
            "|---|---|---|---|---:|---:|---:|---:|---|---|\n"
            "| 카고25톤 | PSBall | 단거리 | 부산지점 -> 김해 생림면 | 108.51T | 40.9km | 8,110 | 198.28 | 정부관리 양곡트럭 운임 | 미래글로벌 스틸 3건 합산 |\n"
        ),
        category="management",
    )
    soup = BeautifulSoup(html, "html.parser")

    assert soup.select_one(".table-scroll table") is not None
    assert "grid-template-columns: 200px minmax(0, 1fr)" in html
    assert "grid-template-columns: minmax(0, 1fr)" in html
    assert "min-width: 0;" in html
    assert "box-sizing: border-box;" in html
    first_list = soup.select_one(".content > ul")
    assert first_list is not None
    assert len(first_list.select(":scope > li")) == 2
    assert "body.category-management .layout" in html
    assert "width: min(96vw, 1480px)" in html
    assert "word-break: keep-all" in html
    assert "body.category-management .content > ul:first-child" not in html
    assert "grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))" not in html
    assert "body.category-management::before" not in html
    assert "background:var(--accent); color:#fff" not in html
    assert "body.category-management .content h3 {" not in html


def test_designed_management_report_preserves_document_flow_and_print_tables():
    html = generate_visual_report(
        "월간 운영 경영분석",
        (
            "## 경영 요약\n\n"
            "전통적인 문단 흐름을 유지하는 경영 보고서입니다.\n\n"
            "## 넓은 운영 표\n\n"
            "| 기간 | 지표 | 기준 | 결과 | 판단 | 근거 | 후속 조치 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 2026-07 | 물량 | 전월 | 120T | 증가 | 내부 집계 | 재확인 |\n"
        ),
        category="management",
        report_style="designed",
    )
    soup = BeautifulSoup(html, "html.parser")

    assert soup.body["data-report-style"] == "designed"
    assert "designed-profile-briefing" in soup.body.get("class", [])
    assert soup.select_one(".content > h2") is not None
    assert soup.select_one(".table-scroll table") is not None
    assert "display: grid" not in html.split("/* DESIGNED_REPORT_TOKENS */", 1)[-1]
    assert "@media print" in html
    assert "overflow-x: auto" in html
    assert "word-break: keep-all" in html
    assert "overflow-wrap: anywhere" in html
    assert "hyphens: none" in html
    assert "display: block;" in html
    assert "width:100% !important; min-width:0 !important;" in html
    assert "animation: none !important;" in html
    assert "color: #111 !important;" in html
