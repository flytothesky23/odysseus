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


def test_visual_report_embeds_vault_images_as_data_urls(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    image = vault / "notes" / "assets" / "screen.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    monkeypatch.setattr("src.knowledge_base.get_setting", lambda key, default=None: str(vault) if key == "knowledge_vault_root" else default)

    html = generate_visual_report(
        "vault image report",
        "## Overview\n\nBody.",
        sources=[{
            "url": "vault://notes/overview.md#chunk-0",
            "title": "Obsidian: overview.md",
            "source_type": "obsidian",
            "images": [{"url": "vault-image://notes/assets/screen.png"}],
        }],
        stats={},
        session_id="rp-vault-image",
    )
    soup = BeautifulSoup(html, "html.parser")
    hero = soup.select_one(".hero-image")
    img = soup.select_one(".hero-image img")

    assert hero["data-img-url"] == "vault-image://notes/assets/screen.png"
    assert img["src"].startswith("data:image/png;base64,")


def test_visual_report_hides_vault_images_by_identifier(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    image = vault / "notes" / "assets" / "screen.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"small png")
    monkeypatch.setattr("src.knowledge_base.get_setting", lambda key, default=None: str(vault) if key == "knowledge_vault_root" else default)

    html = generate_visual_report(
        "vault image report",
        "## Overview\n\nBody.",
        sources=[{
            "url": "vault://notes/overview.md#chunk-0",
            "title": "Obsidian: overview.md",
            "source_type": "obsidian",
            "images": [{"url": "vault-image://notes/assets/screen.png"}],
        }],
        stats={},
        session_id="rp-vault-image",
        hidden_images=["vault-image://notes/assets/screen.png"],
    )

    assert "data:image/png;base64" not in html
    assert 'class="hero-image"' not in html


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
