from src.report_design import build_design_spec
from src.research_handler import _design_image_prompt_specs


def test_management_design_spec_preserves_document_preset_and_maps_one_scene():
    spec = build_design_spec(
        category="management",
        headings=[
            {"level": 2, "slug": "summary", "text": "경영 요약"},
            {"level": 2, "slug": "conflict", "text": "상충 근거"},
        ],
        image_mode="editorial",
        assets=[{"role": "hero"}, {"role": "section"}],
    )

    assert spec.preset == "document-briefing"
    assert spec.tokens.accent == "#285e67"
    assert spec.image_mode == "editorial"
    assert [scene.visual_role for scene in spec.scenes] == [
        "typography",
        "section_background",
    ]
    assert [asset.visual_role for asset in spec.visual_assets] == [
        "editorial_hero",
        "section_background",
    ]
    assert spec.offline is True
    assert spec.reduced_motion is True
    assert spec.print_fallback is True


def test_design_spec_rejects_unknown_modes_and_arbitrary_tokens():
    spec = build_design_spec(
        category="unknown",
        headings=[{"level": 2, "slug": "intro", "text": "서론"}],
        image_mode="<script>alert(1)</script>",
        assets=[{"role": "remote-script"}, {"role": "hero"}],
    )

    assert spec.preset == "minimal-paper"
    assert spec.image_mode == "none"
    assert spec.asset_roles == ("hero",)
    assert "<script>" not in str(spec.to_dict())


def test_design_spec_bounds_visual_asset_layering_metadata():
    spec = build_design_spec(
        category="comparison",
        headings=[{"level": 2, "slug": "intro", "text": "서론"}],
        image_mode="editorial",
        assets=[
            {
                "role": "hero",
                "visual_role": "editorial_hero",
                "focal_x": 8,
                "focal_y": -2,
                "safe_area": "left",
                "overlay_strength": 9,
                "alt": "통합 표지",
            },
            {
                "role": "ambient",
                "visual_role": "page_ambient_background",
            },
        ],
    )

    hero = spec.visual_assets[0]
    assert hero.visual_role == "editorial_hero"
    assert hero.focal_x == 1.0
    assert hero.focal_y == 0.0
    assert hero.overlay_strength == 1.0
    assert hero.safe_area == "left"
    assert spec.visual_assets[1].visual_role == "page_ambient_background"


def test_context_profile_changes_structure_for_management_and_product():
    management = build_design_spec(
        category="management",
        headings=[{"level": 2, "slug": "metrics", "text": "운영 수치"}],
        image_mode="editorial",
        assets=[{"role": "hero"}],
    )
    product = build_design_spec(
        category="product",
        headings=[{"level": 2, "slug": "journey", "text": "제품 여정"}],
        image_mode="editorial",
        assets=[{"role": "hero"}],
    )

    assert management.context_profile.genre == "management-analysis"
    assert management.preset == "document-briefing"
    assert product.context_profile.genre == "product-analysis"
    assert product.preset == "cinematic-banner"
    assert management.manifest.composition_candidates != (
        product.manifest.composition_candidates
    )
    assert management.manifest.rationale != product.manifest.rationale
    assert management.manifest.seed != product.manifest.seed


def test_context_palettes_change_surface_and_secondary_color_not_only_accent():
    common = {
        "headings": [{"level": 2, "slug": "summary", "text": "요약"}],
        "image_mode": "editorial",
        "assets": [{"role": "hero"}],
    }

    editorial = build_design_spec(category=None, **common)
    product = build_design_spec(category="product", **common)
    comparison = build_design_spec(category="comparison", **common)
    howto = build_design_spec(category="howto", **common)

    palettes = {
        (
            spec.tokens.paper,
            spec.tokens.surface,
            spec.tokens.surface_alt,
            spec.tokens.accent,
            spec.tokens.accent_secondary,
            spec.tokens.hero_scrim,
        )
        for spec in (editorial, product, comparison, howto)
    }

    assert len(palettes) == 4
    assert product.tokens.paper != editorial.tokens.paper
    assert comparison.tokens.accent_secondary != product.tokens.accent_secondary
    assert howto.tokens.surface != comparison.tokens.surface


def test_image_prompt_uses_redacted_context_design_not_private_report_text():
    spec = build_design_spec(
        category="product",
        headings=[
            {
                "level": 2,
                "slug": "private-heading-id",
                "text": "내부 회사명과 매출 91억이 들어간 비공개 제목",
            }
        ],
        image_mode="editorial",
        assets=[],
    )

    prompts = _design_image_prompt_specs("product", "editorial", spec)
    combined = "\n".join(item["prompt"] for item in prompts)

    assert spec.context_profile.visual_metaphor in combined
    assert spec.manifest.selected_composition in combined
    assert spec.tokens.paper in combined
    assert "내부 회사명" not in combined
    assert "91억" not in combined
    assert "/Users/" not in combined
    assert "No readable text" in combined
