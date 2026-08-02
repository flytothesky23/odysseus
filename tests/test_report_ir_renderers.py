from bs4 import BeautifulSoup

from src.report_ir import ReportIR, build_report_ir
from src.report_renderers import (
    RENDERER_REGISTRY,
    normalize_html_renderers,
    render_report,
)


REPORT = """# 프로젝트 알파 근거 보고서

## 집행 요약

확인된 사실: 프로젝트 알파는 2026-04-01 시작했다. [착수 기록](vault://safe/01-fact.md)

- 승인 예산은 1,200,000원이다.
- 일정이 공격적이라는 평가는 개인 의견이다.

## 상충과 변경 이력

> 초기 목표는 월 120건이었다.

후속 결정에서는 목표가 135건으로 변경됐다. [변경 기록](vault://safe/02-change.md)

## 한계와 답할 수 없는 질문

현재 근거만으로 영업이익은 확정할 수 없다.
"""


def _render_all(report_ir: ReportIR):
    return {
        renderer: render_report(
            renderer,
            report_ir=report_ir,
            question="프로젝트 알파를 근거만으로 분석해줘",
            sources=[],
            stats={"Rounds": 2},
            category="comparison",
            session_id="rp-ir",
            research_mode="editorial",
        )
        for renderer in ("document", "editorial", "scroll_story")
    }


def test_report_ir_is_deterministic_typed_and_evidence_locked():
    first = build_report_ir(
        question="프로젝트 알파를 근거만으로 분석해줘",
        report_markdown=REPORT,
        sources=[
            {"title": "착수 기록", "url": "vault://safe/01-fact.md"},
            {"title": "변경 기록", "url": "vault://safe/02-change.md"},
        ],
        category="comparison",
    )
    second = build_report_ir(
        question="프로젝트 알파를 근거만으로 분석해줘",
        report_markdown=REPORT,
        sources=[
            {"title": "착수 기록", "url": "vault://safe/01-fact.md"},
            {"title": "변경 기록", "url": "vault://safe/02-change.md"},
        ],
        category="comparison",
    )

    assert first == second
    assert first.version == "report-ir-v1"
    assert first.mapping_hash == second.mapping_hash
    assert [section.section_id for section in first.sections] == [
        "section-executive-summary",
        "section-conflict-history",
        "section-limitations",
    ]
    block_types = {
        block.block_type
        for section in first.sections
        for block in section.blocks
    }
    assert {"prose", "list", "quote", "limitation", "conflict"} <= block_types
    assert first.claims
    assert first.citations
    assert all(claim.claim_id.startswith("claim-") for claim in first.claims)
    assert all(citation.citation_id.startswith("citation-") for citation in first.citations)
    assert all(not source.safe_label.startswith("/") for source in first.sources)
    assert first.to_dict()["mapping_hash"] == first.mapping_hash


def test_report_ir_reduces_absolute_source_titles_to_safe_labels():
    report_ir = build_report_ir(
        question="private source labels",
        report_markdown="## 근거\n\n확인된 사실이다.",
        sources=[
            {"title": "/Users/alice/PrivateVault/secret.md"},
            {"title": "/home/alice/private/notes.yaml"},
            {"title": "file:///Users/alice/PrivateVault/local.csv"},
            {"title": r"C:\\Users\\alice\\PrivateVault\\memo.md"},
        ],
    )

    assert [source.safe_label for source in report_ir.sources] == [
        "secret.md",
        "notes.yaml",
        "local.csv",
        "memo.md",
    ]
    assert all("alice" not in source.safe_label.lower() for source in report_ir.sources)


def test_all_renderers_consume_one_ir_without_claim_or_citation_loss():
    report_ir = build_report_ir(
        question="프로젝트 알파를 근거만으로 분석해줘",
        report_markdown=REPORT,
        sources=[],
        category="comparison",
    )
    before = report_ir.to_json()
    rendered = _render_all(report_ir)

    assert set(RENDERER_REGISTRY) >= {"document", "editorial", "scroll_story"}
    assert report_ir.to_json() == before
    for renderer, artifact in rendered.items():
        soup = BeautifulSoup(artifact.html, "html.parser")
        assert artifact.renderer_id == renderer
        assert artifact.report_ir_hash == report_ir.mapping_hash
        assert soup.body["data-report-ir-hash"] == report_ir.mapping_hash
        assert {
            element["data-claim-id"]
            for element in soup.select("[data-claim-id]")
        } == {claim.claim_id for claim in report_ir.claims}
        assert {
            element["data-citation-id"]
            for element in soup.select("[data-citation-id]")
        } == {citation.citation_id for citation in report_ir.citations}


def test_renderer_topologies_are_structurally_distinct_not_palette_aliases():
    report_ir = build_report_ir(
        question="프로젝트 알파 분석",
        report_markdown=REPORT,
        sources=[],
        category="comparison",
    )
    rendered = _render_all(report_ir)
    soups = {
        key: BeautifulSoup(artifact.html, "html.parser")
        for key, artifact in rendered.items()
    }

    assert soups["document"].select_one("main.content") is not None
    assert soups["document"].select_one(".scroll-story-stage") is None
    assert soups["editorial"].select_one(".hero[data-design-composition]") is not None
    assert soups["editorial"].select_one(".scroll-story-stage") is None
    assert soups["scroll_story"].select_one("main.scroll-story-stage") is not None
    assert soups["scroll_story"].select_one("nav.scroll-story-route") is not None
    assert len(soups["scroll_story"].select("article.scroll-story-scene")) == len(
        report_ir.sections
    )


def test_scroll_story_is_semantic_offline_and_has_accessible_fallbacks():
    report_ir = build_report_ir(
        question="프로젝트 알파 분석",
        report_markdown=REPORT,
        sources=[],
        category="comparison",
    )
    artifact = render_report(
        "scroll_story",
        report_ir=report_ir,
        question="프로젝트 알파 분석",
        sources=[],
        stats={},
        category="comparison",
        session_id="rp-scroll",
        research_mode="editorial",
    )
    soup = BeautifulSoup(artifact.html, "html.parser")

    assert soup.html["lang"] == "ko"
    assert soup.select_one('a[href="#scroll-story-content"]') is not None
    assert soup.select_one('main#scroll-story-content[tabindex="-1"]') is not None
    assert all(scene.find(["h2", "h3"]) for scene in soup.select(".scroll-story-scene"))
    assert soup.select_one("noscript") is not None
    assert "prefers-reduced-motion: reduce" in artifact.html
    assert "@media print" in artifact.html
    assert "position: sticky" in artifact.html
    assert "IntersectionObserver" in artifact.html
    assert "scrollTo" not in artifact.html
    assert "<video" not in artifact.html
    assert "<canvas" not in artifact.html
    assert "http://fonts" not in artifact.html
    assert "https://fonts" not in artifact.html
    assert "<script src=" not in artifact.html


def test_html_renderer_selection_is_separate_and_backward_compatible():
    assert normalize_html_renderers(None, artifact_formats=["html"]) == ["document"]
    assert normalize_html_renderers(
        ["auto", "editorial", "scroll-story", "editorial"],
        artifact_formats=["html"],
    ) == ["document", "editorial", "scroll_story"]
    assert normalize_html_renderers(
        None,
        artifact_formats=["html_designed"],
    ) == ["editorial"]
    assert normalize_html_renderers(
        ["arbitrary-js"],
        artifact_formats=["html"],
    ) == ["document"]
