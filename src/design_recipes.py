"""Allowlisted design recipes and provenance for offline report renderers."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DesignRecipe:
    recipe_id: str
    primitive: str
    source: str
    repository: str
    license: str
    provenance: str
    dependencies: tuple[str, ...]
    offline: bool
    accessibility: str
    print_constraint: str
    security_review: str
    code_adopted: bool

    def to_dict(self) -> dict:
        return asdict(self)


DESIGN_RECIPE_REGISTRY: tuple[DesignRecipe, ...] = (
    DesignRecipe(
        recipe_id="odysseus-document-flow",
        primitive="document",
        source="Odysseus legacy management report contract",
        repository="local:odysseus",
        license="AGPL-3.0-only",
        provenance="Existing report flow retained and wrapped behind ReportIR.",
        dependencies=(),
        offline=True,
        accessibility="semantic headings, tables, landmarks",
        print_constraint="traditional document flow and readable wide tables",
        security_review="existing sanitizer and local-only standalone artifact",
        code_adopted=True,
    ),
    DesignRecipe(
        recipe_id="odysseus-editorial-overlay",
        primitive="editorial",
        source="Odysseus designed HTML release candidate",
        repository="local:odysseus",
        license="AGPL-3.0-only",
        provenance="Hero composer, typography, surface, and image-role contracts.",
        dependencies=(),
        offline=True,
        accessibility="semantic HTML text above optional local imagery",
        print_constraint="static hero, no animation, high contrast",
        security_review="allowlisted tokens and confined local assets only",
        code_adopted=True,
    ),
    DesignRecipe(
        recipe_id="scroll-ordered-scenes",
        primitive="scroll_story",
        source="Scroll World ordered scene concept",
        repository="https://github.com/oso95/scroll-world",
        license="MIT",
        provenance="Principle only: major report sections map to ordered scenes; no third-party code copied.",
        dependencies=(),
        offline=True,
        accessibility="semantic searchable scene articles remain primary content",
        print_constraint="scenes flatten to document order",
        security_review="reimplemented locally; no remote media, CDN, or arbitrary script",
        code_adopted=False,
    ),
    DesignRecipe(
        recipe_id="scroll-sticky-readable-copy",
        primitive="sticky_copy",
        source="Scroll World sticky copy pattern",
        repository="https://github.com/oso95/scroll-world",
        license="MIT",
        provenance="Principle only: sticky chapter context beside normal document flow.",
        dependencies=(),
        offline=True,
        accessibility="copy remains selectable and headings remain in DOM",
        print_constraint="sticky positioning disabled",
        security_review="CSS-only layout; no scroll hijacking",
        code_adopted=False,
    ),
    DesignRecipe(
        recipe_id="scroll-route-rail",
        primitive="route_rail",
        source="Scroll World route navigation concept",
        repository="https://github.com/oso95/scroll-world",
        license="MIT",
        provenance="Principle only: native anchors plus IntersectionObserver state.",
        dependencies=(),
        offline=True,
        accessibility="anchor labels, keyboard focus, aria-current",
        print_constraint="route rail omitted",
        security_review="same-document anchors only",
        code_adopted=False,
    ),
    DesignRecipe(
        recipe_id="frontend-context-art-direction",
        primitive="context_profile",
        source="frontend-design skill",
        repository="local-skill:frontend-design",
        license="Apache-2.0",
        provenance="Workflow principle: explicit context-led aesthetic direction before implementation.",
        dependencies=(),
        offline=True,
        accessibility="quality criteria include semantic and responsive behavior",
        print_constraint="renderer owns deterministic print fallback",
        security_review="principles only; no generated dependency or third-party code",
        code_adopted=False,
    ),
    DesignRecipe(
        recipe_id="frontend-native-css-first",
        primitive="native_css",
        source="frontend-design skill",
        repository="local-skill:frontend-design",
        license="Apache-2.0",
        provenance="Workflow principle: prefer native CSS and bounded vanilla JS.",
        dependencies=(),
        offline=True,
        accessibility="progressive enhancement",
        print_constraint="all visual treatments have print rules",
        security_review="no remote packages or arbitrary runtime code",
        code_adopted=False,
    ),
    DesignRecipe(
        recipe_id="taste-responsive-stability",
        primitive="responsive_stability",
        source="design-taste-frontend skill",
        repository="local-skill:design-taste-frontend",
        license="reference-only; license not bundled",
        provenance="Heuristic review only: responsive stability and restrained motion; no code copied.",
        dependencies=(),
        offline=True,
        accessibility="reduced motion and mobile reading surface",
        print_constraint="motion and sticky behavior removed",
        security_review="unlicensed code excluded; only general design heuristic retained",
        code_adopted=False,
    ),
)


def design_recipe_manifest() -> dict:
    recipes = [recipe.to_dict() for recipe in DESIGN_RECIPE_REGISTRY]
    return {
        "version": "design-recipe-manifest-v1",
        "recipe_count": len(recipes),
        "complete_provenance": all(
            item["source"]
            and item["repository"]
            and item["license"]
            and item["security_review"]
            for item in recipes
        ),
        "external_runtime_dependencies": [],
        "recipes": recipes,
    }
