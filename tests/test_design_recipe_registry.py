from dataclasses import replace

from src.design_quality import run_design_critique_loop
from src.design_recipes import DESIGN_RECIPE_REGISTRY, design_recipe_manifest
from src.report_design import build_design_spec


def test_design_recipe_registry_has_complete_provenance_and_no_runtime_dependency():
    manifest = design_recipe_manifest()

    assert 6 <= len(DESIGN_RECIPE_REGISTRY) <= 10
    assert manifest["complete_provenance"] is True
    assert manifest["external_runtime_dependencies"] == []
    assert all(recipe.offline for recipe in DESIGN_RECIPE_REGISTRY)
    assert all(recipe.accessibility for recipe in DESIGN_RECIPE_REGISTRY)
    assert all(recipe.print_constraint for recipe in DESIGN_RECIPE_REGISTRY)
    assert all(recipe.security_review for recipe in DESIGN_RECIPE_REGISTRY)
    assert any(recipe.repository == "https://github.com/oso95/scroll-world" for recipe in DESIGN_RECIPE_REGISTRY)
    assert any(recipe.source == "frontend-design skill" for recipe in DESIGN_RECIPE_REGISTRY)
    assert any(recipe.source == "design-taste-frontend skill" for recipe in DESIGN_RECIPE_REGISTRY)


def test_bounded_design_critique_repairs_only_allowlisted_spec_fields():
    spec = build_design_spec(
        category="product",
        headings=[{"level": 2, "slug": "journey", "text": "제품 여정"}],
        image_mode="none",
        assets=[],
    )
    unsafe = replace(
        spec,
        tokens=replace(spec.tokens, body_size_px=11, line_height=1.2),
        motion_preset="unbounded-parallax",
        reduced_motion=False,
        print_fallback=False,
        offline=False,
    )

    repaired, trace = run_design_critique_loop(
        unsafe,
        renderer_id="scroll_story",
        max_rounds=2,
    )

    assert repaired.tokens.body_size_px == 16
    assert repaired.tokens.line_height == 1.55
    assert repaired.motion_preset == "scene-observer"
    assert repaired.offline is True
    assert repaired.print_fallback is True
    assert repaired.reduced_motion is True
    assert trace[-1].passed is True
    assert len(trace) <= 3
    assert unsafe.manifest == repaired.manifest
