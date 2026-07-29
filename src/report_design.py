"""Validated presentation specification for designed research artifacts.

Research prose and citations remain immutable inputs. Renderers consume this
small schema instead of accepting arbitrary LLM-authored HTML, CSS, or JS.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable, Mapping, Sequence


VISUAL_ROLES = frozenset({
    "evidence_figure",
    "explanatory_simulation",
    "data_dashboard",
    "editorial_hero",
    "section_background",
    "page_ambient_background",
    "decorative_accent",
})


@dataclass(frozen=True)
class DesignTokens:
    accent: str
    accent_soft: str
    accent_secondary: str = "#315f72"
    accent_secondary_soft: str = "#dbe6ea"
    paper: str = "#f7f4ed"
    surface: str = "#fffdf8"
    surface_alt: str = "#eee6da"
    ink: str = "#1f2529"
    ink_muted: str = "#64615c"
    hero_scrim: str = "#17232c"
    hero_text: str = "#fffaf2"
    hero_kicker: str = "#f2c99f"
    ambient_opacity: float = 0.08
    body_size_px: int = 17
    line_height: float = 1.82


@dataclass(frozen=True)
class DesignScene:
    section_id: str
    title: str
    visual_role: str = "typography"


@dataclass(frozen=True)
class VisualAssetSpec:
    role: str
    visual_role: str
    section_id: str = ""
    focal_x: float = 0.5
    focal_y: float = 0.5
    safe_area: str = "none"
    desktop_aspect: str = "21/9"
    mobile_aspect: str = "4/5"
    overlay_strength: float = 0.55
    palette: str = "editorial-neutral"
    alt_text: str = ""


@dataclass(frozen=True)
class ContextProfile:
    genre: str
    audience: str
    purpose: str
    tone: str
    narrative_shape: str
    evidence_density: str
    source_modality: str
    emotional_temperature: str
    data_weight: str
    image_weight: str
    uncertainty_treatment: str
    accessibility: tuple[str, ...]
    visual_metaphor: str


@dataclass(frozen=True)
class DesignManifest:
    selected_composition: str
    composition_candidates: tuple[str, ...]
    rationale: tuple[str, ...]
    variation_id: str
    seed: str


@dataclass(frozen=True)
class DesignSpec:
    version: str
    preset: str
    tokens: DesignTokens
    image_mode: str
    scenes: tuple[DesignScene, ...]
    asset_roles: tuple[str, ...]
    visual_assets: tuple[VisualAssetSpec, ...] = ()
    motion_preset: str = "subtle-reveal"
    context_profile: ContextProfile | None = None
    manifest: DesignManifest | None = None
    reduced_motion: bool = True
    print_fallback: bool = True
    offline: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


_PRESETS = {
    "management": (
        "document-briefing",
        DesignTokens(
            accent="#285e67",
            accent_soft="#d7e6e3",
            accent_secondary="#9a6b33",
            accent_secondary_soft="#efe0c7",
            paper="#edf3f1",
            surface="#fbfdfc",
            surface_alt="#dfe9e5",
            ink="#173034",
            ink_muted="#52686b",
            hero_scrim="#102b31",
            hero_text="#f7fffd",
            hero_kicker="#e4bd75",
            ambient_opacity=0.065,
        ),
    ),
    "product": (
        "cinematic-banner",
        DesignTokens(
            accent="#007c7e",
            accent_soft="#cde8e5",
            accent_secondary="#c85e47",
            accent_secondary_soft="#f2d8d1",
            paper="#edf5f3",
            surface="#f8fffc",
            surface_alt="#d9ebe6",
            ink="#142d2e",
            ink_muted="#526a68",
            hero_scrim="#062e36",
            hero_text="#f4fffd",
            hero_kicker="#ffbf8f",
            ambient_opacity=0.075,
        ),
    ),
    "comparison": (
        "evidence-dossier",
        DesignTokens(
            accent="#744a8d",
            accent_soft="#e6d9ed",
            accent_secondary="#b77a21",
            accent_secondary_soft="#f1e1c6",
            paper="#f4f0f7",
            surface="#fdfaff",
            surface_alt="#e8deed",
            ink="#2d2033",
            ink_muted="#685d70",
            hero_scrim="#25162f",
            hero_text="#fff9ff",
            hero_kicker="#f2c66d",
            ambient_opacity=0.07,
        ),
    ),
    "factcheck": (
        "evidence-dossier",
        DesignTokens(
            accent="#2d6083",
            accent_soft="#d7e4ee",
            accent_secondary="#b34f48",
            accent_secondary_soft="#efd8d5",
            paper="#edf2f7",
            surface="#fbfdff",
            surface_alt="#dce5ee",
            ink="#172635",
            ink_muted="#5b6976",
            hero_scrim="#11283a",
            hero_text="#f7fbff",
            hero_kicker="#efb47b",
            ambient_opacity=0.065,
        ),
    ),
    "howto": (
        "technical-blueprint",
        DesignTokens(
            accent="#3e7447",
            accent_soft="#d9e8d7",
            accent_secondary="#b77920",
            accent_secondary_soft="#f0e1c7",
            paper="#eff5ec",
            surface="#fbfff8",
            surface_alt="#dfeadb",
            ink="#1d3020",
            ink_muted="#5b6c5c",
            hero_scrim="#17351f",
            hero_text="#f7fff5",
            hero_kicker="#f0c478",
            ambient_opacity=0.075,
        ),
    ),
    "default": (
        "editorial-overlay",
        DesignTokens(
            accent="#a24f38",
            accent_soft="#f0ddd4",
            accent_secondary="#2f6470",
            accent_secondary_soft="#d8e7e9",
            paper="#f5efe5",
            surface="#fffaf3",
            surface_alt="#e8ddcf",
            ink="#25272b",
            ink_muted="#676058",
            hero_scrim="#1d2931",
            hero_text="#fff9ef",
            hero_kicker="#f0c08c",
            ambient_opacity=0.08,
        ),
    ),
}


def _bounded_ratio(value: object, default: float) -> float:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, ratio))


def _context_profile(
    category_key: str,
    *,
    heading_count: int,
    image_mode: str,
) -> ContextProfile:
    if category_key == "management":
        return ContextProfile(
            genre="management-analysis",
            audience="decision-makers",
            purpose="operational decision support",
            tone="disciplined and calm",
            narrative_shape="decision and evidence",
            evidence_density="high",
            source_modality="mixed notes and structured tables",
            emotional_temperature="low",
            data_weight="high",
            image_weight="low" if image_mode == "none" else "supporting",
            uncertainty_treatment="explicit limits and follow-up actions",
            accessibility=("mobile", "print", "reduced-motion", "screen-reader"),
            visual_metaphor="measured briefing table",
        )
    if category_key == "product":
        return ContextProfile(
            genre="product-analysis",
            audience="evaluators and builders",
            purpose="explain a product journey and decision",
            tone="future-facing but evidence-led",
            narrative_shape="product journey",
            evidence_density="medium-high",
            source_modality="notes, specifications, and scenarios",
            emotional_temperature="medium",
            data_weight="medium",
            image_weight="high" if image_mode != "none" else "low",
            uncertainty_treatment="separate simulation from verified behavior",
            accessibility=("mobile", "print", "reduced-motion", "screen-reader"),
            visual_metaphor="prototype becoming a usable system",
        )
    if category_key in {"comparison", "factcheck"}:
        return ContextProfile(
            genre=category_key,
            audience="critical readers",
            purpose="compare claims without hiding conflict",
            tone="analytical and transparent",
            narrative_shape="comparison and counter-evidence",
            evidence_density="high",
            source_modality="traceable source fragments",
            emotional_temperature="low-medium",
            data_weight="medium",
            image_weight="supporting" if image_mode != "none" else "low",
            uncertainty_treatment="prominent conflict and evidence gaps",
            accessibility=("mobile", "print", "reduced-motion", "screen-reader"),
            visual_metaphor="intersecting evidence paths",
        )
    return ContextProfile(
        genre="research-editorial",
        audience="thoughtful general readers",
        purpose="turn selected private evidence into a publishable argument",
        tone="human, reflective, and rigorous",
        narrative_shape="hierarchical synthesis" if heading_count > 3 else "focused essay",
        evidence_density="medium-high",
        source_modality="mixed personal notes and local documents",
        emotional_temperature="medium",
        data_weight="low-medium",
        image_weight="supporting" if image_mode != "none" else "low",
        uncertainty_treatment="keep fact, opinion, inference, and gaps visible",
        accessibility=("mobile", "print", "reduced-motion", "screen-reader"),
        visual_metaphor="raw notes woven into a coherent publication",
    )


def _composition_plan(
    profile: ContextProfile,
    *,
    image_mode: str,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if profile.genre == "management-analysis":
        candidates = (
            "document-briefing",
            "data-led-brief",
            "minimal-paper",
        )
        selected = "document-briefing"
        rationale = (
            "운영 수치와 넓은 표가 장식보다 우선이므로 문서 흐름을 유지합니다.",
            "이미지는 근거 표나 데이터 차트를 대체하지 않습니다.",
        )
    elif profile.genre == "product-analysis":
        candidates = (
            "product-showcase",
            "cinematic-banner",
            "technical-blueprint",
        )
        selected = "cinematic-banner" if image_mode != "none" else "technical-blueprint"
        rationale = (
            "제품 여정을 설명하는 장르이므로 장면 전환과 시뮬레이션 경계를 강조합니다.",
            "검증된 사실과 생성 개념 이미지를 명시적으로 분리합니다.",
        )
    elif profile.narrative_shape == "comparison and counter-evidence":
        candidates = (
            "editorial-overlay",
            "split-narrative",
            "evidence-dossier",
        )
        selected = "editorial-overlay" if image_mode != "none" else "evidence-dossier"
        rationale = (
            "상충 근거가 핵심이므로 비교 경로와 불확실성 표지를 우선합니다.",
            "시각 강조는 결론이 아니라 근거 대조 순서를 따릅니다.",
        )
    else:
        candidates = (
            "editorial-overlay",
            "minimal-paper",
            "split-narrative",
        )
        selected = "editorial-overlay" if image_mode != "none" else "minimal-paper"
        rationale = (
            "개인 노트의 목소리를 지우지 않으면서 근거 계층을 읽기 쉽게 만듭니다.",
            "이미지와 타이포그래피를 하나의 독서 흐름으로 구성합니다.",
        )
    return selected, candidates, rationale


def build_design_spec(
    *,
    category: str | None,
    headings: Iterable[Mapping[str, object]],
    image_mode: str,
    assets: Sequence[Mapping[str, object]],
) -> DesignSpec:
    """Create a deterministic, allowlisted design plan from report structure."""
    category_key = str(category or "").strip().lower()
    _base_preset, tokens = _PRESETS[
        category_key if category_key in _PRESETS else "default"
    ]
    normalized_mode = str(image_mode or "none").strip().lower()
    if normalized_mode not in {"none", "cover", "editorial"}:
        normalized_mode = "none"
    asset_roles = tuple(
        role
        for role in ("hero", "section", "ambient")
        if any(str(asset.get("role") or "").strip().lower() == role for asset in assets)
    )
    default_visual_roles = {
        "hero": "editorial_hero",
        "section": "section_background",
        "ambient": "page_ambient_background",
    }
    visual_assets = []
    for role in asset_roles:
        asset = next(
            item
            for item in assets
            if str(item.get("role") or "").strip().lower() == role
        )
        visual_role = str(
            asset.get("visual_role") or default_visual_roles[role]
        ).strip().lower()
        if visual_role not in VISUAL_ROLES:
            visual_role = default_visual_roles[role]
        safe_area = str(asset.get("safe_area") or "none").strip().lower()
        if safe_area not in {"none", "left", "right", "top", "bottom"}:
            safe_area = "none"
        visual_assets.append(VisualAssetSpec(
            role=role,
            visual_role=visual_role,
            section_id=str(asset.get("section_id") or "")[:120],
            focal_x=_bounded_ratio(asset.get("focal_x"), 0.5),
            focal_y=_bounded_ratio(asset.get("focal_y"), 0.5),
            safe_area=safe_area,
            desktop_aspect=str(asset.get("desktop_aspect") or "21/9")[:16],
            mobile_aspect=str(asset.get("mobile_aspect") or "4/5")[:16],
            overlay_strength=_bounded_ratio(asset.get("overlay_strength"), 0.55),
            palette=str(asset.get("palette") or "editorial-neutral")[:80],
            alt_text=str(asset.get("alt") or asset.get("alt_text") or "")[:240],
        ))
    scenes = []
    section_number = 0
    for heading in headings:
        if int(heading.get("level") or 0) != 2:
            continue
        section_number += 1
        visual_role = (
            "section_background"
            if normalized_mode == "editorial" and "section" in asset_roles and section_number == 2
            else "typography"
        )
        scenes.append(DesignScene(
            section_id=str(heading.get("slug") or f"section-{section_number}"),
            title=str(heading.get("text") or "")[:160],
            visual_role=visual_role,
        ))
    profile = _context_profile(
        category_key,
        heading_count=len(scenes),
        image_mode=normalized_mode,
    )
    preset, composition_candidates, rationale = _composition_plan(
        profile,
        image_mode=normalized_mode,
    )
    seed_payload = {
        "genre": profile.genre,
        "narrative_shape": profile.narrative_shape,
        "image_mode": normalized_mode,
        "headings": [scene.section_id for scene in scenes],
    }
    seed = hashlib.sha256(
        json.dumps(seed_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    manifest = DesignManifest(
        selected_composition=preset,
        composition_candidates=composition_candidates,
        rationale=rationale,
        variation_id=f"{preset}-{seed[:8]}",
        seed=seed,
    )
    return DesignSpec(
        version="design-spec-v2",
        preset=preset,
        tokens=tokens,
        image_mode=normalized_mode,
        scenes=tuple(scenes),
        asset_roles=asset_roles,
        visual_assets=tuple(visual_assets),
        context_profile=profile,
        manifest=manifest,
    )
