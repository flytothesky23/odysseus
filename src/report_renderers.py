"""Registry of standalone HTML renderers consuming one immutable ReportIR."""
from __future__ import annotations

from dataclasses import dataclass
import html
import json
import re
from typing import Callable, Mapping, Sequence

from src.report_design import DesignSpec, build_design_spec
from src.design_quality import DesignAuditRound, run_design_critique_loop
from src.design_recipes import design_recipe_manifest
from src.report_ir import ReportBlock, ReportIR


HTML_RENDERERS = ("document", "editorial", "scroll_story")
_RENDERER_ALIASES = {
    "legacy": "document",
    "document": "document",
    "doc": "document",
    "designed": "editorial",
    "design": "editorial",
    "html_designed": "editorial",
    "editorial": "editorial",
    "scroll": "scroll_story",
    "scroll-story": "scroll_story",
    "scroll_story": "scroll_story",
}


@dataclass(frozen=True)
class RenderArtifact:
    renderer_id: str
    html: str
    report_ir_hash: str
    design_spec: DesignSpec | None
    audit_trace: tuple[DesignAuditRound, ...] = ()


Renderer = Callable[..., RenderArtifact]


def normalize_html_renderers(
    values: object,
    *,
    artifact_formats: Sequence[str] | None = None,
) -> list[str]:
    """Normalize independent HTML renderer selections with legacy aliases."""
    formats = [str(value or "").strip().lower() for value in (artifact_formats or ())]
    raw_values = values if isinstance(values, (list, tuple, set)) else [values] if values else []
    normalized: list[str] = []
    for value in raw_values:
        key = str(value or "").strip().lower()
        if key == "auto":
            renderer = "document"
        else:
            renderer = _RENDERER_ALIASES.get(key)
        if renderer and renderer not in normalized:
            normalized.append(renderer)
    if not normalized and "html_designed" in formats:
        normalized.append("editorial")
    if not normalized:
        normalized.append("document")
    return normalized


def _headings(report_ir: ReportIR) -> list[dict[str, object]]:
    return [
        {"level": section.level, "text": section.title, "slug": section.section_id}
        for section in report_ir.sections
    ]


def _design_spec(
    report_ir: ReportIR,
    *,
    category: str | None,
    image_mode: str,
    assets: Sequence[Mapping[str, object]] | None,
) -> DesignSpec:
    return build_design_spec(
        category=category or report_ir.category,
        headings=_headings(report_ir),
        image_mode=image_mode,
        assets=assets or (),
    )


def _mapping_ledger(report_ir: ReportIR) -> str:
    claims = "".join(
        '<span data-claim-id="{}" data-claim-type="{}"></span>'.format(
            html.escape(claim.claim_id, quote=True),
            html.escape(claim.claim_type, quote=True),
        )
        for claim in report_ir.claims
    )
    citations = "".join(
        '<span data-citation-id="{}" data-source-id="{}"></span>'.format(
            html.escape(citation.citation_id, quote=True),
            html.escape(citation.source_id, quote=True),
        )
        for citation in report_ir.citations
    )
    return (
        '<section class="report-ir-ledger" hidden aria-hidden="true" '
        'data-report-ir-version="report-ir-v1">'
        f"{claims}{citations}</section>"
    )


def _annotate_existing_html(
    rendered: str,
    *,
    renderer_id: str,
    report_ir: ReportIR,
    design_spec: DesignSpec | None,
    audit_trace: tuple[DesignAuditRound, ...],
) -> str:
    body_attributes = (
        f' data-html-renderer="{html.escape(renderer_id, quote=True)}"'
        f' data-report-ir-hash="{report_ir.mapping_hash}"'
    )
    rendered = re.sub(r"<body\b", f"<body{body_attributes}", rendered, count=1)
    if renderer_id == "editorial":
        composition = (
            design_spec.manifest.selected_composition
            if design_spec and design_spec.manifest
            else "editorial"
        )
        rendered = re.sub(
            r'<(?P<tag>section|div) class="hero\b',
            '<\\g<tag> data-design-composition="{}" class="hero'.format(
                html.escape(composition, quote=True)
            ),
            rendered,
            count=1,
        )
    ledger = _mapping_ledger(report_ir)
    design_metadata = json.dumps(
        {
            "design_spec": design_spec.to_dict() if design_spec else None,
            "audit_trace": [item.to_dict() for item in audit_trace],
            "recipe_manifest": design_recipe_manifest(),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).replace("</", "<\\/")
    metadata = (
        '<script type="application/json" id="report-design-metadata">'
        f"{design_metadata}</script>"
    )
    return rendered.replace("</body>", f"{ledger}{metadata}</body>", 1)


def _render_document_or_editorial(
    *,
    renderer_id: str,
    report_ir: ReportIR,
    question: str,
    sources: list[dict] | None,
    stats: dict | None,
    category: str | None,
    session_id: str | None,
    hidden_images: list[str] | None,
    research_mode: str,
    design_image_mode: str,
    designed_visual_assets: list[dict] | None,
    design_assets_status: str | None,
) -> RenderArtifact:
    from src.visual_report import generate_visual_report

    image_mode = design_image_mode if renderer_id == "editorial" else "none"
    design_spec, audit_trace = run_design_critique_loop(
        _design_spec(
            report_ir,
            category=category,
            image_mode=image_mode,
            assets=designed_visual_assets,
        ),
        renderer_id=renderer_id,
    )
    rendered = generate_visual_report(
        question=question,
        report_markdown=report_ir.to_markdown(),
        sources=sources,
        stats=stats,
        category=category,
        session_id=session_id,
        hidden_images=hidden_images,
        report_style="designed" if renderer_id == "editorial" else "legacy",
        research_mode=research_mode,
        design_image_mode=image_mode,
        designed_visual_assets=designed_visual_assets,
        design_assets_status=design_assets_status,
    )
    return RenderArtifact(
        renderer_id=renderer_id,
        html=_annotate_existing_html(
            rendered,
            renderer_id=renderer_id,
            report_ir=report_ir,
            design_spec=design_spec,
            audit_trace=audit_trace,
        ),
        report_ir_hash=report_ir.mapping_hash,
        design_spec=design_spec,
        audit_trace=audit_trace,
    )


def _render_block(block: ReportBlock) -> str:
    from src.visual_report import _md_to_html, _wrap_report_tables

    content = _wrap_report_tables(_md_to_html(block.markdown))
    claims = " ".join(block.claim_ids)
    citations = " ".join(block.citation_ids)
    return (
        '<div class="scroll-story-block" '
        f'data-block-id="{html.escape(block.block_id, quote=True)}" '
        f'data-block-type="{html.escape(block.block_type, quote=True)}" '
        f'data-claim-id="{html.escape(claims, quote=True)}" '
        f'data-citation-refs="{html.escape(citations, quote=True)}">'
        f"{content}</div>"
    )


def _scroll_story_css(spec: DesignSpec) -> str:
    tokens = spec.tokens
    return f"""
:root {{
  color-scheme: light;
  --paper: {tokens.paper};
  --surface: {tokens.surface};
  --surface-alt: {tokens.surface_alt};
  --ink: {tokens.ink};
  --muted: {tokens.ink_muted};
  --accent: {tokens.accent};
  --accent-soft: {tokens.accent_soft};
  --display: ui-serif, "Iowan Old Style", "Apple SD Gothic Neo", serif;
  --body: "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; background: var(--paper); }}
body {{
  margin: 0; color: var(--ink); background:
  radial-gradient(circle at 86% 8%, var(--accent-soft), transparent 31rem),
  var(--paper); font-family: var(--body); line-height: 1.78;
}}
.scroll-story-ambient {{ position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; opacity: .075; }}
.scroll-story-ambient img {{ width: 100%; height: 100%; object-fit: cover; filter: saturate(.72) contrast(.84); }}
.scroll-story-header, .scroll-story-route, .scroll-story-stage {{ position: relative; z-index: 1; }}
a {{ color: var(--accent); text-underline-offset: .2em; }}
.skip-link {{ position: fixed; z-index: 20; left: 1rem; top: -5rem; padding: .8rem 1rem; background: var(--ink); color: white; }}
.skip-link:focus {{ top: 1rem; }}
.scroll-story-header {{
  min-height: min(82vh, 760px); display: grid; align-items: end;
  padding: clamp(5rem, 12vw, 11rem) clamp(1.25rem, 8vw, 9rem) clamp(3rem, 8vw, 7rem);
  background: linear-gradient(132deg, color-mix(in srgb, var(--ink) 95%, var(--accent)), var(--accent));
  color: white; position: relative; overflow: clip;
}}
.scroll-story-header > img {{
  position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
  object-position: var(--focal-x, 50%) var(--focal-y, 50%);
}}
.scroll-story-header::before {{
  content: ""; position: absolute; inset: 0; z-index: 1;
  background: linear-gradient(90deg,
    rgba(10, 18, 24, var(--hero-overlay, .72)) 0%,
    rgba(10, 18, 24, .52) 48%,
    rgba(10, 18, 24, .18) 100%);
}}
.scroll-story-header::after {{
  content: ""; position: absolute; z-index: 2; inset: 10% -10% auto 48%; aspect-ratio: 1;
  border: 1px solid color-mix(in srgb, white 38%, transparent);
  border-radius: 50%; transform: rotate(-12deg);
}}
.scroll-story-header > div {{ position: relative; z-index: 3; }}
.scroll-story-generated-disclosure {{ display: block; margin-top: 1.25rem; max-width: 58ch; font-size: .75rem; opacity: .74; }}
.scroll-story-kicker {{ letter-spacing: .18em; text-transform: uppercase; font-size: .78rem; opacity: .78; }}
.scroll-story-header h1 {{
  margin: .6rem 0 0; max-width: 13ch; font-family: var(--display);
  font-size: clamp(2.8rem, 7.2vw, 7rem); line-height: .98; letter-spacing: -.045em;
  word-break: keep-all; text-wrap: balance;
}}
.scroll-story-route {{
  position: fixed; z-index: 10; right: 1rem; top: 50%; transform: translateY(-50%);
  display: grid; gap: .55rem; padding: .75rem; border-radius: 999px;
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  border: 1px solid color-mix(in srgb, var(--ink) 14%, transparent);
  backdrop-filter: blur(12px);
}}
.scroll-story-route a {{
  width: .72rem; height: .72rem; border-radius: 50%; background: var(--muted);
  overflow: hidden; text-indent: 2rem; white-space: nowrap; opacity: .42;
}}
.scroll-story-route a[aria-current="true"] {{ background: var(--accent); opacity: 1; transform: scale(1.28); }}
.scroll-story-stage {{ width: min(100%, 1600px); margin: 0 auto; }}
.scroll-story-sequence {{ margin: 0; padding: 0; list-style: none; }}
.scroll-story-sequence > li {{ margin: 0; padding: 0; }}
.scroll-story-scene {{
  min-height: 110vh; display: grid; grid-template-columns: minmax(16rem, .8fr) minmax(0, 1.35fr);
  gap: clamp(2rem, 7vw, 8rem); padding: clamp(3rem, 8vw, 8rem) clamp(1.25rem, 7vw, 7rem);
  border-bottom: 1px solid color-mix(in srgb, var(--ink) 12%, transparent);
}}
.scroll-story-scene:nth-child(even) {{ background: color-mix(in srgb, var(--surface-alt) 62%, transparent); }}
.product-journey-sequence .scroll-story-scene:nth-child(even) .scroll-story-scene-copy {{ order: 2; }}
.product-journey-sequence .scroll-story-scene:nth-child(even) .scroll-story-reading {{ order: 1; }}
.timeline-sequence {{
  position: relative; padding-left: clamp(1rem, 5vw, 5rem);
  border-left: .22rem solid color-mix(in srgb, var(--accent) 54%, transparent);
}}
.timeline-sequence > li {{ position: relative; }}
.timeline-sequence > li::before {{
  content: ""; position: absolute; z-index: 2; left: calc(clamp(1rem, 5vw, 5rem) * -1 - .72rem);
  top: clamp(5rem, 12vw, 9rem); width: 1.15rem; height: 1.15rem; border-radius: 50%;
  background: var(--surface); border: .28rem solid var(--accent);
}}
body[data-context-genre="academic-evidence"] .scroll-story-reading {{
  border-top: .28rem solid var(--accent); box-shadow: none;
}}
body[data-context-genre="personal-knowledge-essay"] .scroll-story-scene {{
  grid-template-columns: minmax(15rem, .65fr) minmax(0, 1fr);
}}
.scroll-story-scene-copy {{
  align-self: start; position: sticky; top: 14vh; padding-block: 1rem;
}}
.scroll-story-index {{ color: var(--accent); font-weight: 700; letter-spacing: .12em; }}
.scroll-story-scene h2 {{
  margin: .8rem 0; font-family: var(--display); font-size: clamp(2rem, 4.6vw, 4.8rem);
  line-height: 1.08; letter-spacing: -.035em; word-break: keep-all; text-wrap: balance;
}}
.scroll-story-scene-deck {{ color: var(--muted); max-width: 30ch; font-size: clamp(1rem, 1.4vw, 1.2rem); }}
.scroll-story-reading {{
  align-self: center; min-width: 0; padding: clamp(1.5rem, 4vw, 4rem);
  background: color-mix(in srgb, var(--surface) 94%, transparent);
  border: 1px solid color-mix(in srgb, var(--ink) 11%, transparent);
  box-shadow: 0 2rem 5rem color-mix(in srgb, var(--ink) 8%, transparent);
}}
.scroll-story-scene-visual {{ margin: 0 0 2rem; border: 1px solid color-mix(in srgb, var(--ink) 12%, transparent); background: var(--surface-alt); }}
.scroll-story-scene-visual img {{ display: block; width: 100%; aspect-ratio: 16 / 7; object-fit: cover; }}
.scroll-story-scene-visual figcaption {{ padding: .65rem .85rem; color: var(--muted); font-size: .78rem; }}
.scroll-story-block + .scroll-story-block {{ margin-top: 1.6rem; }}
.scroll-story-block p, .scroll-story-block li {{ font-size: clamp(1.02rem, 1.3vw, 1.18rem); }}
.scroll-story-block blockquote {{ margin: 0; padding: 1rem 1.5rem; border-left: .3rem solid var(--accent); background: var(--accent-soft); }}
.table-scroll {{ max-width: 100%; overflow-x: auto; overscroll-behavior-inline: contain; }}
.table-scroll table {{ width: max-content; min-width: 100%; border-collapse: collapse; word-break: keep-all; }}
th, td {{ padding: .75rem 1rem; border: 1px solid color-mix(in srgb, var(--ink) 16%, transparent); text-align: left; }}
.scroll-story-scene.is-active .scroll-story-reading {{ border-color: color-mix(in srgb, var(--accent) 48%, transparent); }}
.scroll-story-noscript {{ padding: 1rem; background: #fff4cc; color: #2c2610; }}
.report-ir-ledger {{ display: none !important; }}
@media (max-width: 780px) {{
  .scroll-story-header {{ min-height: 68vh; padding-top: 7rem; }}
  .scroll-story-route {{ position: sticky; top: 0; right: auto; transform: none; display: flex; justify-content: center; border-radius: 0; }}
  .scroll-story-scene {{ min-height: auto; grid-template-columns: 1fr; padding-block: 4rem; }}
  .product-journey-sequence .scroll-story-scene:nth-child(even) .scroll-story-scene-copy,
  .product-journey-sequence .scroll-story-scene:nth-child(even) .scroll-story-reading {{ order: initial; }}
  .timeline-sequence {{ padding-left: 1rem; }}
  .scroll-story-scene-copy {{ position: static; }}
  .scroll-story-reading {{ padding: 1.35rem; }}
}}
@media (prefers-reduced-motion: reduce) {{
  html {{ scroll-behavior: auto; }}
  *, *::before, *::after {{ animation: none !important; transition: none !important; }}
  .scroll-story-scene-copy {{ position: static; }}
}}
@media print {{
  @page {{ margin: 14mm; }}
  body {{ background: white !important; color: #111 !important; }}
  .skip-link, .scroll-story-route {{ display: none !important; }}
  .scroll-story-ambient, .scroll-story-scene-visual {{ display: none !important; }}
  .scroll-story-header {{ min-height: 0; padding: 1.5rem 0 2rem; color: #111; background: white; }}
  .scroll-story-header > img {{ opacity: .14; filter: grayscale(1); }}
  .scroll-story-header::before {{ display: none; }}
  .scroll-story-header h1 {{ max-width: none; font-size: 28pt; }}
  .scroll-story-stage {{ width: 100%; }}
  .scroll-story-scene {{ display: block; min-height: 0; padding: 1.2rem 0; break-inside: auto; }}
  .scroll-story-scene-copy {{ position: static; }}
  .scroll-story-reading {{ padding: 0; border: 0; box-shadow: none; }}
  .table-scroll {{ overflow: visible; }}
  .table-scroll table {{ width: 100% !important; min-width: 0 !important; font-size: 8.5pt; }}
}}
"""


def _scroll_story_script() -> str:
    return """
(() => {
  document.documentElement.classList.add('js');
  const scenes = [...document.querySelectorAll('.scroll-story-scene')];
  const links = new Map([...document.querySelectorAll('.scroll-story-route a')].map(link => [link.hash.slice(1), link]));
  if (!('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      scenes.forEach(scene => scene.classList.toggle('is-active', scene === entry.target));
      links.forEach((link, id) => link.setAttribute('aria-current', id === entry.target.id ? 'true' : 'false'));
    }
  }, { rootMargin: '-34% 0px -48% 0px', threshold: 0.05 });
  scenes.forEach(scene => observer.observe(scene));
})();
"""


def _render_scroll_story(
    *,
    report_ir: ReportIR,
    question: str,
    sources: list[dict] | None,
    stats: dict | None,
    category: str | None,
    session_id: str | None,
    hidden_images: list[str] | None,
    research_mode: str,
    design_image_mode: str,
    designed_visual_assets: list[dict] | None,
    design_assets_status: str | None,
) -> RenderArtifact:
    del sources, stats, session_id, hidden_images, research_mode, design_assets_status
    from src.visual_report import _load_designed_visual_assets

    safe_assets = _load_designed_visual_assets(designed_visual_assets)
    assets_by_role = {asset["role"]: asset for asset in safe_assets}
    hero_asset = assets_by_role.get("hero")
    section_asset = assets_by_role.get("section")
    ambient_asset = assets_by_role.get("ambient")
    spec, audit_trace = run_design_critique_loop(
        _design_spec(
            report_ir,
            category=category,
            image_mode=design_image_mode,
            assets=designed_visual_assets,
        ),
        renderer_id="scroll_story",
    )
    route_links = []
    scenes = []
    profile = spec.context_profile
    context_genre = str(getattr(profile, "genre", "") or "research-editorial")
    narrative_shape = str(getattr(profile, "narrative_shape", "") or "hierarchical synthesis")
    scene_treatment = (
        "chronology-spine"
        if narrative_shape == "chronology"
        else "alternating-product-journey"
        if narrative_shape == "product journey"
        else "sticky-evidence-panels"
    )
    count = len(report_ir.sections)
    for index, section in enumerate(report_ir.sections, start=1):
        route_links.append(
            '<a href="#{}" aria-label="{}"{current}>{}</a>'.format(
                html.escape(section.section_id, quote=True),
                html.escape(section.title, quote=True),
                html.escape(section.title),
                current=' aria-current="true"' if index == 1 else "",
            )
        )
        blocks = "".join(_render_block(block) for block in section.blocks)
        section_visual = ""
        if section_asset and index == min(2, count):
            section_visual = (
                '<figure class="scroll-story-scene-visual" '
                'data-generated-image="true" data-visual-role="section_background">'
                f'<img src="{section_asset["data_uri"]}" '
                f'alt="{html.escape(section_asset.get("alt") or "", quote=True)}" loading="eager">'
                '<figcaption>AI 생성 개념 이미지 · 사실 근거나 데이터 시각화가 아닙니다.</figcaption>'
                '</figure>'
            )
        scenes.append(
            '<article class="scroll-story-scene" id="{}" data-section-id="{}">'
            '<span class="scroll-story-scene-treatment" hidden>{}</span>'
            '<header class="scroll-story-scene-copy">'
            '<span class="scroll-story-index">{:02d} / {:02d}</span>'
            '<h2>{}</h2>'
            '<p class="scroll-story-scene-deck">근거와 인용을 보존한 장면별 읽기 흐름</p>'
            '</header>'
            '<div class="scroll-story-reading">{}{}</div>'
            '</article>'.format(
                html.escape(section.section_id, quote=True),
                html.escape(section.section_id, quote=True),
                html.escape(scene_treatment),
                index,
                count,
                html.escape(section.title),
                section_visual,
                blocks,
            )
        )
    if narrative_shape == "chronology":
        scene_sequence = (
            '<ol class="scroll-story-sequence timeline-sequence" '
            'aria-label="시간순 보고서 장면">'
            + "".join(f"<li>{scene}</li>" for scene in scenes)
            + "</ol>"
        )
    elif narrative_shape == "product journey":
        scene_sequence = (
            '<div class="scroll-story-sequence product-journey-sequence">'
            + "".join(scenes)
            + "</div>"
        )
    else:
        scene_sequence = "".join(scenes)
    manifest_json = json.dumps(
        {
            "design_manifest": spec.manifest.__dict__ if spec.manifest else {},
            "audit_trace": [item.to_dict() for item in audit_trace],
            "recipe_manifest": design_recipe_manifest(),
        },
        ensure_ascii=False,
        sort_keys=True,
    ).replace("</", "<\\/")
    hero_visual = ""
    hero_style = ""
    hero_disclosure = ""
    if hero_asset:
        hero_visual = (
            f'<img src="{hero_asset["data_uri"]}" '
            f'alt="{html.escape(hero_asset.get("alt") or "", quote=True)}" fetchpriority="high">'
        )
        hero_style = (
            f' style="--focal-x:{float(hero_asset.get("focal_x", .5)) * 100:.1f}%;'
            f'--focal-y:{float(hero_asset.get("focal_y", .5)) * 100:.1f}%;'
            f'--hero-overlay:{max(.35, min(.9, float(hero_asset.get("overlay_strength", .65)))):.2f}"'
        )
        hero_disclosure = (
            '<span class="scroll-story-generated-disclosure">'
            'AI 생성 개념 이미지 · 사실 근거나 데이터 시각화가 아님</span>'
        )
    ambient_visual = ""
    if ambient_asset:
        ambient_visual = (
            '<div class="scroll-story-ambient" data-visual-role="page_ambient_background" '
            'aria-hidden="true">'
            f'<img src="{ambient_asset["data_uri"]}" alt="" aria-hidden="true">'
            '</div>'
        )
    rendered = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{html.escape(report_ir.title)}</title>
<style>{_scroll_story_css(spec)}</style>
</head>
<body data-html-renderer="scroll_story" data-report-ir-hash="{report_ir.mapping_hash}"
      data-context-genre="{html.escape(context_genre, quote=True)}"
      data-scene-treatment="{html.escape(scene_treatment, quote=True)}"
      data-design-preset="{html.escape(spec.preset, quote=True)}">
{ambient_visual}
<a class="skip-link" href="#scroll-story-content">본문으로 건너뛰기</a>
<header class="scroll-story-header"{hero_style}>
  {hero_visual}
  <div>
    <div class="scroll-story-kicker">Odysseus · Scroll Story</div>
    <h1>{html.escape(report_ir.title)}</h1>
    <p>{html.escape(question or report_ir.question)}</p>
    {hero_disclosure}
  </div>
</header>
<nav class="scroll-story-route" aria-label="보고서 장면 이동">{''.join(route_links)}</nav>
<noscript><p class="scroll-story-noscript">JavaScript 없이도 전체 보고서를 순서대로 읽을 수 있습니다.</p></noscript>
<main class="scroll-story-stage" id="scroll-story-content" tabindex="-1">{scene_sequence}</main>
{_mapping_ledger(report_ir)}
<script type="application/json" id="design-manifest">{manifest_json}</script>
<script>{_scroll_story_script()}</script>
</body>
</html>"""
    return RenderArtifact(
        renderer_id="scroll_story",
        html=rendered,
        report_ir_hash=report_ir.mapping_hash,
        design_spec=spec,
        audit_trace=audit_trace,
    )


def _document_renderer(**kwargs) -> RenderArtifact:
    return _render_document_or_editorial(renderer_id="document", **kwargs)


def _editorial_renderer(**kwargs) -> RenderArtifact:
    return _render_document_or_editorial(renderer_id="editorial", **kwargs)


RENDERER_REGISTRY: dict[str, Renderer] = {
    "document": _document_renderer,
    "editorial": _editorial_renderer,
    "scroll_story": _render_scroll_story,
}


def render_report(
    renderer_id: str,
    *,
    report_ir: ReportIR,
    question: str,
    sources: list[dict] | None = None,
    stats: dict | None = None,
    category: str | None = None,
    session_id: str | None = None,
    hidden_images: list[str] | None = None,
    research_mode: str = "research",
    design_image_mode: str = "none",
    designed_visual_assets: list[dict] | None = None,
    design_assets_status: str | None = None,
) -> RenderArtifact:
    normalized = _RENDERER_ALIASES.get(str(renderer_id or "").strip().lower())
    if normalized not in RENDERER_REGISTRY:
        normalized = "document"
    return RENDERER_REGISTRY[normalized](
        report_ir=report_ir,
        question=question,
        sources=sources,
        stats=stats,
        category=category,
        session_id=session_id,
        hidden_images=hidden_images,
        research_mode=research_mode,
        design_image_mode=design_image_mode,
        designed_visual_assets=designed_visual_assets,
        design_assets_status=design_assets_status,
    )
