# Report IR and generative renderer roadmap

## Decision

Odysseus research and writer stages produce one evidence-locked structured
report. Presentation is a separate renderer layer. Research is not repeated
for each visual style.

## Minimum report IR

The long-term `ReportIR` should contain:

- title, purpose, reader, genre, thesis, executive summary;
- ordered sections and stable section IDs;
- typed blocks: prose, quote, callout, table, list, limitation, conflict,
  decision, source note;
- claim IDs linked to evidence IDs and safe source labels;
- fact, opinion, inference, hypothesis, uncertainty, and unresolved-question
  types;
- duplicate groups, temporal revisions, conflicts, and evidence gaps;
- citation-audit state and content-quality findings;
- safe presentation hints that do not alter claims.

`ReportIR` must not contain credentials, private absolute paths, raw executable
HTML, arbitrary CSS/JS, or model tool instructions.

## Renderer interface

A renderer consumes an immutable `ReportIR` plus a validated presentation
specification:

```text
render(report_ir, presentation_spec, local_assets) -> standalone artifact
```

The current `DesignSpec` is the first small schema:

- deterministic `ContextProfile` covering genre, audience, purpose, tone,
  narrative shape, evidence/source density, uncertainty, accessibility, and
  visual metaphor;
- allowlisted composition primitives rather than a fixed final theme;
- paper/ink/accent/spacing/typography tokens;
- ordered section-to-scene mapping;
- typed visual roles, focal point, safe area, responsive aspect, overlay,
  palette, and alt text;
- reproducible `DesignManifest` seed, variation ID, alternatives, and rationale;
- offline, print, and reduced-motion requirements.

A renderer may adjust layout, typography, scene rhythm, and local asset
placement. It may not rewrite facts, figures, claims, or citations. Wording
feedback returns to the content loop and repeats citation audit.

## Generative design grammar

The calm premium editorial result is one baseline, not the product ceiling.
The system should assemble context-appropriate UI/UX from validated primitives
in the same conceptual way image generation combines a prompt with constrained
parameters:

```text
ContextProfile
  -> candidate DesignSpec JSON
  -> deterministic renderer
  -> DOM/screenshot/accessibility/performance audit
  -> visual critic finding
  -> allowlisted patch or candidate hybrid
  -> joint content/design audit
```

The grammar may vary layout topology, grid/density/rhythm, Korean type scale,
palette/surfaces, image roles, section transitions, citation/uncertainty
treatment, restrained motion, and mobile/print fallbacks. Variation is
context-explainable and seed-reproducible; it is not random decoration.

Reusable libraries should accumulate:

- genre/context art-direction prompt fragments;
- composition-aware image prompts and safe-area/crop recipes;
- Korean typography and line-break recipes;
- layout, component, motion, table, citation, and uncertainty patterns;
- visual critic rubrics and anti-patterns;
- Figma-tested token/layout/motion recipes;
- open-license local assets with provenance in an `AssetManifest`.

Figma, Google Stitch, Pencil, and frontend-design workflows are interchangeable
optional design laboratories for exploring composition, auto-layout,
responsive behavior, and motion. Selected results must be reduced back into
renderer primitives so production artifacts remain standalone and do not
require any vendor at runtime.

These laboratories are used occasionally to discover new design language, not
once per report. Figma's official MCP plan table limits Starter and View/Collab
read calls to six per month; selected write tools may be exempt, but lookup and
analysis dependence is still prohibited. Computer Use may prototype the Stitch
web UI when explicitly approved, but its latency and UI fragility exclude it
from production generation.

The adapter boundary is:

```text
propose_designs(redacted_context_profile, redacted_brief)
  -> schema-valid DesignSpec/DesignManifest candidates
```

Adapter unavailability, quota exhaustion, or authentication failure always
falls back to the deterministic local renderer. Raw private notes and paths
never cross this boundary. Any external call is explicit opt-in and receives
only a privacy-scrubbed profile/brief.

Google's official Stitch MCP codelab currently lists a Stitch account, Stitch
API key, Node.js 18+, and a billing-enabled Cloud project. Google OAuth UI login
and MCP authentication are separate. Until free/paid limits are verified, the
adapter cannot claim zero cost. API-key creation, billing activation, or a
billable call requires explicit user authorization, and secret/project
identifiers must stay outside source, logs, artifacts, and operational notes.
The current Codex environment has no callable Stitch tool, so this adapter is
capability-gated follow-up work rather than an RC dependency.

When an experiment yields a good result, its palette, typography, layout,
motion, prompt, and validation lessons are generalized into vendor-neutral
local tokens/primitives and reused without Figma or Stitch calls.

Official references checked on 2026-07-29:

- https://developers.figma.com/docs/figma-mcp-server/rate-limits-access/
- https://codelabs.developers.google.com/design-to-code-with-antigravity-stitch
- https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-updates/

## Visual roles

| Role | Placement contract |
| --- | --- |
| `evidence_figure` | Body figure with caption/source/alt; no destructive crop or misleading overlay. |
| `explanatory_simulation` | Clearly labeled generated concept or scenario, never presented as verified reality. |
| `data_dashboard` | Generated only from validated structured data; generative imagery cannot fabricate numeric UI or charts. |
| `editorial_hero` | Full-width background with focal/safe area and semantic HTML title/deck/metadata above it. |
| `section_background` | Edge-to-edge chapter transition with short semantic heading and readable body surface following it. |
| `page_ambient_background` | Low-contrast texture/artwork behind opaque reading surfaces, removed or simplified for print. |
| `decorative_accent` | Non-semantic ornament excluded from the accessibility tree. |

Every local generated asset remains owner-scoped. Cache reuse requires both the
deterministic prompt/model/version key and the same owner; renderer loading is
path-confined and bounded by role count, per-file bytes, and total bytes.

## Supported and planned styles

| Style | State | Contract |
| --- | --- | --- |
| Document | Existing | Legacy HTML; traditional report flow and management default. |
| Editorial | RC | Deterministic designed HTML with optional local generated images. |
| Scroll story | Follow-up prototype | Sticky visual + readable text panels; progressive enhancement; no scroll hijacking. |
| Cinematic | Capability-gated follow-up | Optional scene/frame assets; static poster and text remain complete without video. |
| Timeline / atlas / executive brief | Roadmap | Separate allowlisted renderers consuming the same IR. |

## Scroll World patterns selected for later use

Reference: `oso95/scroll-world` (MIT, 5,606 stars checked 2026-07-29).

Adopt as design principles:

- map each major report section to one scene;
- keep color, composition, subject, and typography continuous across scenes;
- use scroll as reading sequence, not decoration;
- pair sticky visuals with readable searchable text;
- generate a separate portrait composition or static poster for mobile;
- preserve citations, tables, limitations, and source text outside
  canvas/video;
- support `prefers-reduced-motion`, keyboard/screen readers, print, and
  JavaScript-free reading;
- bound frame count, bytes, preload, memory, and animation intensity.

Reject as core dependencies:

- Higgsfield credits or any external video service;
- ffmpeg/ffprobe runtime requirements;
- remote CDN/tracking;
- generated images or video as substitutes for evidence or quantitative
  charts.

## Next prototype gate

First prove the design grammar across five sanitized contexts: calm academic
evidence, operations management, personal knowledge essay, future
product/technology simulation, and event timeline. Their outputs must differ
across multiple structural axes—not only palette—while preserving facts,
citations, accessibility, and a coherent Odysseus quality baseline.

Then produce document, editorial, and scroll-story artifacts from one
ReportIR. Capture desktop/mobile scroll positions, reduced-motion,
JavaScript-off and print fallbacks, asset bytes, loading time, console/network
results, and section-to-source mapping. Promote a renderer only when the visual
sequence improves comprehension without obscuring claims or evidence.
