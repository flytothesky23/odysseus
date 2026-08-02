#!/usr/bin/env python3
"""Build a deterministic five-context renderer gallery for user inspection.

The fixture is synthetic and contains no private user material. Every renderer
for a context consumes the same immutable ReportIR; this script records the
mapping hashes and structural signatures so palette-only diversity cannot pass.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.design_recipes import design_recipe_manifest
from src.report_ir import build_report_ir
from src.report_renderers import render_report
from src.research_handler import _renderer_recommendation


CONTEXTS = {
    "academic-evidence": {
        "category": "academic",
        "mode": "research",
        "question": "도시 열섬 완화 방안에 관한 합성 근거를 비교하고 한계를 밝혀 주세요.",
        "report": """# 도시 열섬 완화 근거 보고서

## 연구 질문과 근거 범위

합성 관측 기록에서 수목 그늘 구역의 주간 표면온도는 대조 구역보다 2.1°C 낮았다. [관측 기록](vault://fixture/academic-observation.md)

## 핵심 근거

> 관측은 동일한 14일 동안 같은 시간대에 수행되었다.

- 차열 포장 구역의 평균 차이는 1.2°C였다.
- 야간 기온 차이는 측정되지 않아 종일 효과로 일반화할 수 없다.

## 상충과 변경

초기 메모는 수목 효과를 2.8°C로 적었지만 교정된 센서 기록은 2.1°C로 변경했다. [교정 기록](vault://fixture/academic-revision.md)

## 한계와 답할 수 없는 질문

합성 자료만으로 다른 계절과 도시 규모에 같은 효과가 유지되는지는 확정할 수 없다.

## 결론

현재 근거는 수목 그늘의 주간 표면온도 완화 가능성을 지지하지만 범위를 넘는 인과 단정은 허용하지 않는다.
""",
    },
    "management-operations": {
        "category": "management",
        "mode": "editorial",
        "question": "합성 운영 수치를 전통 문서 흐름의 경영분석 보고서로 정리해 주세요.",
        "report": """# 합성 운영 경영분석 보고서

## 집행 요약

2분기 처리량은 1,240건이며 1분기 1,080건보다 증가했다. [운영 집계](vault://fixture/operations.csv)

## 운영 수치

| 지표 | 1분기 | 2분기 | 증감 |
|---|---:|---:|---:|
| 처리량(건) | 1,080 | 1,240 | +160 |
| 평균 처리시간(분) | 46 | 41 | -5 |
| 재작업률(%) | 4.8 | 5.1 | +0.3%p |

## 상충과 변경 이력

처리량과 속도는 개선됐지만 재작업률이 상승해 품질 개선으로 단정할 수 없다.

## 종합의견 및 관리 Check Point

처리량 확대와 재작업 원인을 함께 추적하고, 세부 원인이 없는 상태에서 비용·이익 효과를 지어내지 않는다.

## 한계

재무상태표와 현금흐름 자료가 제공되지 않았으므로 이 보고서는 운영 수치 범위에 한정한다.
""",
    },
    "personal-knowledge": {
        "category": "personal",
        "mode": "editorial",
        "question": "사실과 개인 관점을 구분하면서 혼합 지식노트를 출판 가능한 에세이로 구조화해 주세요.",
        "report": """# 느린 판단을 위한 개인 지식 에세이

## 기록된 사실

세 번의 합성 회고에서 결정 직후보다 하루 뒤에 반대 근거가 더 많이 기록되었다. [회고 기록](vault://fixture/reflection.md)

## 개인 의견

나는 빠른 결론이 불안을 잠시 줄이지만 좋은 판단을 보장하지 않는다고 느낀다. 이 문장은 개인의 관점이다.

## 상충과 변경

초기 메모는 즉시 실행을 선호했으나 후속 메모는 되돌리기 어려운 결정만 하루 유예하기로 바꾸었다.

## 추론

이 기록에서는 짧은 유예가 반대 근거를 볼 기회를 늘렸을 가능성이 있다. 새로운 일반 법칙이 아니라 제한적 추론이다.

## 한계와 미해결 질문

표본이 한 사람의 합성 기록뿐이므로 다른 사람에게 같은 방식이 유효한지는 답할 수 없다.
""",
    },
    "future-product": {
        "category": "product",
        "mode": "research",
        "question": "미래 제품 개념의 사용자 여정과 증거 한계를 구분해 설명해 주세요.",
        "report": """# 오프라인 지식 동반자 제품 시뮬레이션

## 문제 장면

합성 사용자 인터뷰 12건 중 9건은 이동 중 네트워크 없이 최근 메모를 다시 찾기 어렵다고 답했다. [인터뷰 요약](vault://fixture/product-interviews.md)

## 제품 여정

1. 사용자는 로컬 노트 폴더를 명시적으로 선택한다.
2. 장치 안에서 색인이 만들어지고 질문과 관련된 근거만 제시된다.
3. 사용자는 근거와 개인 의견을 구분한 초안을 검토한다.

## 설명용 시뮬레이션

이 장면은 검증된 실제 제품 화면이 아니라 미래 사용 흐름을 설명하는 개념 시뮬레이션이다.

## 결정과 위험

원문 외부 전송을 기본값으로 두지 않기로 결정했다. 편의보다 사적 자료 경계가 우선이다.

## 한계

합성 인터뷰와 개념 흐름만으로 시장 수요나 실제 사용성 성과를 확정할 수 없다.
""",
    },
    "incident-timeline": {
        "category": "timeline",
        "mode": "research",
        "question": "합성 사건 기록을 시간순으로 대조하고 확정되지 않은 연결을 표시해 주세요.",
        "report": """# 서비스 장애 사건 타임라인

## 09:10 최초 신호

오류율이 기준선 0.4%에서 4.2%로 상승했다. [모니터링 기록](vault://fixture/timeline-monitoring.md)

## 09:18 변경 확인

배포 로그에는 캐시 정책 변경이 기록되어 있었다. 시간상 인접하지만 원인으로 확정된 것은 아니다.

## 09:32 상충 기록

초기 채팅 메모는 데이터베이스 지연을 원인으로 적었으나 후속 측정에서는 지연 증가가 관찰되지 않았다.

## 09:47 결정

팀은 캐시 정책을 이전 값으로 되돌리기로 결정했고 10분 뒤 오류율은 0.6%로 낮아졌다.

## 한계와 미해결 질문

롤백과 회복의 시간적 연관성은 강하지만 단일 원인인지 확인할 추가 실험 기록은 없다.
""",
    },
}


def _signature(html_text: str, artifact) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    body = soup.body
    return {
        "renderer": artifact.renderer_id,
        "preset": artifact.design_spec.preset if artifact.design_spec else "",
        "narrative_shape": (
            artifact.design_spec.context_profile.narrative_shape
            if artifact.design_spec and artifact.design_spec.context_profile
            else ""
        ),
        "scene_treatment": body.get("data-scene-treatment", "document-flow"),
        "has_document_main": bool(soup.select_one("main.content")),
        "has_editorial_hero": bool(soup.select_one(".hero[data-design-composition]")),
        "has_scroll_stage": bool(soup.select_one("main.scroll-story-stage")),
        "has_timeline_spine": bool(soup.select_one(".timeline-sequence")),
        "has_product_journey": bool(soup.select_one(".product-journey-sequence")),
        "heading_count": len(soup.select("h1, h2, h3")),
        "article_count": len(soup.select("article")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", required=True)
    args = parser.parse_args()
    qa_root = Path(args.qa_root).expanduser().resolve()
    gallery = qa_root / "renderer-gallery"
    gallery.mkdir(parents=True, exist_ok=True)

    matrix = []
    context_index = {}
    for context_id, fixture in CONTEXTS.items():
        context_dir = gallery / context_id
        context_dir.mkdir(parents=True, exist_ok=True)
        sources = [
            {"title": "합성 근거 A", "url": f"vault://fixture/{context_id}-a.md"},
            {"title": "합성 근거 B", "url": f"vault://fixture/{context_id}-b.md"},
        ]
        report_ir = build_report_ir(
            question=fixture["question"],
            report_markdown=fixture["report"],
            sources=sources,
            category=fixture["category"],
        )
        recommendation = _renderer_recommendation(
            category=fixture["category"],
            research_mode=fixture["mode"],
            selected=[],
        )
        (context_dir / "report-ir.json").write_text(
            json.dumps(report_ir.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        renderer_hashes = {}
        renderer_rows = {}
        for renderer_id in ("document", "editorial", "scroll_story"):
            artifact = render_report(
                renderer_id,
                report_ir=report_ir,
                question=fixture["question"],
                sources=sources,
                stats={"Rounds": 2, "Queries": 6, "Sources": 2},
                category=fixture["category"],
                session_id=f"qa-{context_id}",
                research_mode=fixture["mode"],
                design_image_mode="none",
            )
            html_file = context_dir / f"{renderer_id}.html"
            html_file.write_text(artifact.html, encoding="utf-8")
            renderer_hashes[renderer_id] = artifact.report_ir_hash
            signature = _signature(artifact.html, artifact)
            renderer_rows[renderer_id] = signature
            (context_dir / f"{renderer_id}-design-spec.json").write_text(
                json.dumps(
                    artifact.design_spec.to_dict() if artifact.design_spec else {},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        same_ir = len(set(renderer_hashes.values())) == 1
        row = {
            "context_id": context_id,
            "category": fixture["category"],
            "recommended_renderer": recommendation["renderer"],
            "recommendation_reason": recommendation["reason"],
            "report_ir_hash": report_ir.mapping_hash,
            "renderer_hashes": renderer_hashes,
            "same_ir_all_renderers": same_ir,
            "renderers": renderer_rows,
        }
        matrix.append(row)
        context_index[context_id] = {
            "question": fixture["question"],
            "category": fixture["category"],
            "recommended_renderer": recommendation["renderer"],
            "report_ir_hash": report_ir.mapping_hash,
        }

    recommended_signatures = []
    for row in matrix:
        signature = row["renderers"][row["recommended_renderer"]]
        recommended_signatures.append(
            (
                signature["renderer"],
                signature["preset"],
                signature["narrative_shape"],
                signature["scene_treatment"],
                signature["has_timeline_spine"],
                signature["has_product_journey"],
            )
        )
    diversity = {
        "context_count": len(matrix),
        "same_ir_within_each_context": all(row["same_ir_all_renderers"] for row in matrix),
        "unique_recommended_structural_signatures": len(set(recommended_signatures)),
        "palette_only_change": len(set(recommended_signatures)) < len(matrix),
        "required_structural_axes": [
            "DOM topology",
            "Korean typography and rhythm preset",
            "scene/component treatment",
        ],
        "pass": (
            all(row["same_ir_all_renderers"] for row in matrix)
            and len(set(recommended_signatures)) == len(matrix)
        ),
    }
    manifest = {
        "fixture": "renderer-gallery-five-contexts-v1",
        "private_data_used": False,
        "external_design_services_used": False,
        "external_runtime_dependencies": [],
        "contexts": context_index,
        "diversity": diversity,
        "rows": matrix,
    }
    (gallery / "structural-diversity-matrix.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (gallery / "asset-recipe-manifest.json").write_text(
        json.dumps(design_recipe_manifest(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_rows = [
        "| 문맥 | 자동 추천 | ReportIR 동일 | preset | narrative | scene treatment |",
        "|---|---|---:|---|---|---|",
    ]
    for row in matrix:
        signature = row["renderers"][row["recommended_renderer"]]
        markdown_rows.append(
            "| {context} | {renderer} | {same} | {preset} | {narrative} | {scene} |".format(
                context=row["context_id"],
                renderer=row["recommended_renderer"],
                same="PASS" if row["same_ir_all_renderers"] else "FAIL",
                preset=signature["preset"],
                narrative=signature["narrative_shape"],
                scene=signature["scene_treatment"],
            )
        )
    (gallery / "README.md").write_text(
        "# Generative Report Renderer Gallery\n\n"
        "모든 자료는 비식별 합성 fixture이며 동일 문맥의 세 renderer가 같은 immutable ReportIR을 사용합니다.\n\n"
        + "\n".join(markdown_rows)
        + "\n\n"
        f"- 구조 다양성 판정: **{'PASS' if diversity['pass'] else 'FAIL'}**\n"
        f"- 고유 구조 signature: {diversity['unique_recommended_structural_signatures']}/5\n"
        "- 외부 Figma/Stitch/CDN 호출: 0\n",
        encoding="utf-8",
    )
    if not diversity["pass"]:
        raise SystemExit("structural diversity gate failed")
    print(json.dumps({"ok": True, "gallery": str(gallery), "diversity": diversity}, ensure_ascii=False))


if __name__ == "__main__":
    main()
