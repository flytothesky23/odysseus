from bs4 import BeautifulSoup

from src.report_ir import build_report_ir
from src.report_renderers import render_report
from src.research_handler import _renderer_recommendation


REPORT = """# 변화의 근거 지도

## 핵심 주장

첫 기록은 2026-01-10에 작성되었다.

## 상충과 변경

후속 기록은 초기 목표를 수정했다.

## 한계

두 기록 사이의 의사결정 과정은 현재 자료만으로 확정할 수 없다.
"""


def test_five_contexts_change_structure_beyond_palette_with_stable_claim_mapping():
    contexts = {
        "academic": "academic",
        "management": "management",
        "personal": "personal",
        "product": "product",
        "timeline": "timeline",
    }
    signatures = {}
    hashes = set()

    for context_id, category in contexts.items():
        report_ir = build_report_ir(
            question="변화 과정을 근거로 설명해줘",
            report_markdown=REPORT,
            sources=[],
            category=category,
        )
        recommendation = _renderer_recommendation(
            category=category,
            research_mode="editorial" if category == "personal" else "research",
            selected=[],
        )
        artifact = render_report(
            recommendation["renderer"],
            report_ir=report_ir,
            question="변화 과정을 근거로 설명해줘",
            sources=[],
            category=category,
            research_mode="editorial" if category == "personal" else "research",
        )
        soup = BeautifulSoup(artifact.html, "html.parser")
        body = soup.body
        signatures[context_id] = (
            artifact.renderer_id,
            artifact.design_spec.preset,
            artifact.design_spec.context_profile.narrative_shape,
            body.get("data-scene-treatment", "document-flow"),
            tuple(body.get("class", [])),
            bool(soup.select_one(".timeline-sequence")),
            bool(soup.select_one(".product-journey-sequence")),
        )
        hashes.add(report_ir.mapping_hash)

    assert len(hashes) == 1
    assert len(set(signatures.values())) == 5
    assert {signature[0] for signature in signatures.values()} == {
        "document",
        "editorial",
        "scroll_story",
    }
    assert signatures["timeline"][5] is True
    assert signatures["product"][6] is True
    assert signatures["timeline"][3] != signatures["product"][3]
    assert signatures["academic"][1] != signatures["management"][1]
