"""Build stable offline designed-report QA artifacts from a sanitized session."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.report_design import build_design_spec
from src.visual_report import (
    _extract_headings,
    _extract_report_title,
    generate_visual_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--hero-filename", required=True)
    parser.add_argument("--section-filename", required=True)
    parser.add_argument("--ambient-filename", required=True)
    args = parser.parse_args()

    session = json.loads(Path(args.session_json).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    visual_assets = [
        {
            "role": "hero",
            "visual_role": "editorial_hero",
            "filename": args.hero_filename,
            "alt": "흩어진 근거가 검토를 거쳐 하나의 보고서로 정리되는 과정을 표현한 생성형 표지 일러스트",
            "model": "Codex built-in imagegen",
            "focal_x": 0.78,
            "focal_y": 0.5,
            "safe_area": "left",
            "desktop_aspect": "21/9",
            "mobile_aspect": "4/5",
            "overlay_strength": 0.62,
            "palette": "midnight-parchment-copper",
        },
        {
            "role": "section",
            "visual_role": "section_background",
            "filename": args.section_filename,
            "alt": "상충하는 기록과 불확실성을 비교하는 과정을 표현한 생성형 편집 일러스트",
            "model": "Codex built-in imagegen",
            "focal_x": 0.5,
            "focal_y": 0.5,
            "safe_area": "left",
            "desktop_aspect": "16/7",
            "mobile_aspect": "4/3",
            "overlay_strength": 0.54,
            "palette": "midnight-parchment-copper",
        },
        {
            "role": "ambient",
            "visual_role": "page_ambient_background",
            "filename": args.ambient_filename,
            "alt": "보고서 배경에 낮은 대비로 사용되는 생성형 종이 질감",
            "model": "Codex built-in imagegen",
            "focal_x": 0.5,
            "focal_y": 0.5,
            "safe_area": "none",
            "desktop_aspect": "1/1",
            "mobile_aspect": "1/1",
            "overlay_strength": 0.88,
            "palette": "warm-paper-sage",
        },
    ]
    common = {
        "question": session.get("query") or "로컬 근거 기반 심층보고서",
        "report_markdown": session.get("result") or "",
        "sources": session.get("sources") or [],
        "stats": session.get("stats") or {},
        "category": session.get("category") or None,
        "session_id": session.get("session_id") or "qa-designed-images",
        "report_style": "designed",
        "research_mode": "editorial",
    }
    no_images = generate_visual_report(
        **common,
        design_image_mode="none",
        designed_visual_assets=[],
    )
    with_images = generate_visual_report(
        **common,
        design_image_mode="editorial",
        designed_visual_assets=visual_assets,
    )
    (output_dir / "candidate-designed-no-images.html").write_text(no_images, encoding="utf-8")
    (output_dir / "candidate-designed-generated-images.html").write_text(
        with_images,
        encoding="utf-8",
    )
    # Figma capture copy is intentionally separate. The production artifact
    # above remains offline and contains no remote script.
    figma_capture = with_images.replace(
        "</head>",
        '<script src="https://mcp.figma.com/mcp/html-to-design/capture.js" async></script>\n</head>',
        1,
    )
    (output_dir / "candidate-designed-figma-capture.html").write_text(
        figma_capture,
        encoding="utf-8",
    )

    _, markdown_without_title = _extract_report_title(
        common["report_markdown"],
        common["question"],
    )
    design_spec = build_design_spec(
        category=common["category"],
        headings=_extract_headings(markdown_without_title),
        image_mode="editorial",
        assets=visual_assets,
    )
    (output_dir / "design-spec.json").write_text(
        json.dumps(design_spec.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
