# Research-grade Editorial Synthesis + Designed HTML Release Candidate

## 단일 최종 목표

선택한 Obsidian/로컬 근거만으로 Deep Research의 계획·반복 검색·근거
대조·상충/공백 분석을 수행하고, 고급 writer의
outline -> draft -> critic -> rewrite -> citation audit 공정을 결합해
근거 충실도는 기존보다 낮아지지 않으면서 논리 깊이·한국어
작문·가독성이 향상된 출판급 심층보고서를 생성한다. 기존 legacy HTML을
보존하고 독립적인 designed HTML을 제공하며, 실제 UI E2E·의미 품질
A/B·시각·보안·성능 감사와 사용자 검수 패키지까지 완성한다.

## 자동 개선 폐쇄 루프

1. 목표/출력 계약과 baseline을 고정한다.
2. 실패하는 회귀·acceptance test와 의미 품질 fixture를 만든다.
3. 가장 작은 안전한 구현을 한다.
4. targeted test를 실행한다.
5. 서버·브라우저 E2E, 의미 품질 A/B, 시각·보안·성능 감사를 실행한다.
6. 모든 FAIL, 회귀, reviewer finding, 품질 미달을 심각도/원인별로
   분류한다.
7. 가장 높은 위험부터 코드·prompt·retrieval·workflow·디자인을
   보완한다.
8. 수정 영향 테스트와 전체 회귀를 다시 실행한다.
9. 새 finding이 생기면 6~8을 반복한다.
10. 모든 필수 gate가 PASS하고 검수 패키지 링크가 실제로 열릴 때만
    release candidate로 판정한다.

테스트 실패, E2E 결함, 품질 미달, 시각 회귀, 보안 finding은 중단 조건이
아니라 다음 개선 라운드의 입력이다. 실제 개인정보/유료 외부 호출에 대한
새 권한, push/tag/release 권한, 파괴적·비가역적 선택, 또는 안전한 대안과
반복 진단을 모두 소진한 외부 환경/자격증명 문제만 `BLOCKED` 또는
`NOT TESTED`로 남긴다.

## Outcome

Add an explicit `editorial` research mode, shown to users as
`로컬 근거 기반 심층보고서`, for selected Obsidian/local sources. This is
Research-grade Editorial Synthesis, not summary, copy-editing, or a one-pass
persona prompt. It retains the Deep Research planning and iterative evidence
loop, then adds a multi-pass publishing workflow.

Add `html_designed` as an independent, self-contained artifact while preserving
the existing `html` artifact and its document-flow contract.

## Non-negotiable boundaries

- Editorial mode requires at least one explicitly selected knowledge folder.
- Editorial mode never calls a web search provider.
- Unselected roots, deleted files, and superseded chunks cannot enter retrieval
  or citations.
- Private chunks are untrusted data, not instructions.
- Artifact routes remain owner-scoped and path-confined.
- Legacy HTML remains the default and keeps the established report flow.
- Designed HTML has no remote scripts, fonts, images, Figma runtime, or network
  dependency.
- Management reports remain traditional reports; design tokens may improve
  typography, spacing, tables, quotations, and navigation, but cannot turn
  report prose into a dashboard/card grid.
- The implementation cannot collapse into
  `retrieve once -> concatenate chunks -> one LLM rewrite`.

## Research and publishing loop

1. Analyze the question, purpose, reader, research agenda, and sub-questions.
2. Inventory the selected corpus by document type, time, reliability, and
   relevance before broad evidence synthesis.
3. Retrieve and re-read evidence iteratively for each sub-question.
4. Extract claim units as fact, number, source claim, personal opinion,
   hypothesis, decision, or unresolved question.
5. Compare duplicates, paraphrases, revisions over time, and conflicts at the
   claim/evidence level.
6. Detect gaps and logical leaps, then run additional local retrieval. Missing
   external evidence remains an explicit gap when web access is disabled.
7. Design the thesis and hierarchical outline.
8. Draft from the evidence ledger.
9. Run a separate critical review for factuality, omissions, counterarguments,
   causality, citation integrity, and reader fit.
10. Apply structural rewrite, prose/rhythm/terminology editing, and a final
    citation audit.

Genre-specific rubrics may emphasize analyst, researcher, nonfiction editor, or
management-report editor behavior. Personal voice and intent are preserved when
useful, but opinion is never silently relabeled as fact.

## Dual closed-loop quality model

The implementation keeps research/writing and presentation as two coupled but
separately constrained loops.

### Loop A — content quality

`question decomposition -> iterative retrieval -> evidence/claim ledger ->
duplicate/conflict/gap detection -> follow-up retrieval -> outline -> draft ->
independent critic -> rewrite -> citation audit`

The content loop owns facts, numbers, claims, opinions, inferences,
uncertainties, citations, and source traceability. A presentation renderer
cannot silently rewrite these fields.

### Loop B — design quality

`ContextProfile -> DesignSpec 후보 -> deterministic renderer -> DOM and
screenshot audit -> visual finding -> 후보 선택/allowlisted token·layout·asset
patch -> re-render`

`src/report_design.py` is the current minimum schema boundary. It permits
allowlisted layout primitives, tokens, scene roles, local asset assignments,
seed, and variation IDs rather than arbitrary model-authored HTML/CSS/JS.
The current calm editorial overlay and management briefing are baseline
compositions, not the final limit of the system.

### Loop C — joint fit audit

The final audit verifies that visual emphasis follows the report thesis, tables
and limitations remain legible, generated illustrations cannot be mistaken for
evidence, and section order matches the argument. Any design suggestion that
changes wording must return to Loop A and repeat the citation audit. Any content
change that affects hierarchy or scenes must return to Loop B.

## Red-to-green contracts

1. Parallel first searches wait for the same completed auto-index barrier.
2. Modified sources replace their prior chunks and deleted sources leave zero
   searchable chunks.
3. Metadata filtering preserves recall for explicitly selected roots even when
   many unselected roots rank higher globally.
4. Editorial/local-only runs call the web provider zero times.
5. Private prompt-injection text is passed only through an untrusted-context
   message and never concatenated into trusted instructions.
6. `html` alone preserves the existing route and result-button contract.
7. `html_designed` creates a separate artifact route and passes owner/path
   checks.
8. Unchanged files are not re-embedded on later indexing runs.
9. Oversized structured files are bounded before parsing.
10. Editorial context selection is deterministic and bounded by relevance,
    duplicate content, and source diversity.
11. The LLM call trace proves distinct plan/retrieval/synthesis/critic/rewrite/
    citation-audit stages rather than a single rewrite prompt.

## Synthetic corpus

The E2E fixture contains:

- a sourced fact note;
- a personal/opinion note;
- an unstructured draft;
- paraphrased duplicate notes;
- two conflicting notes;
- numerous unrelated distractors;
- a prompt-injection note;
- a note modified and another deleted while the job is active;
- a wide table, long paragraphs, mixed Korean/English;
- JSON, YAML, and CSV sources.

No fixture contains real account data, secrets, email content, OAuth material,
or real vault paths.

## Required E2E journey

Run an isolated server with a temporary data directory, temporary user/database,
synthetic knowledge roots, deterministic fake LLM endpoint, and web-provider
spy. Through Playwright:

1. select editorial mode and exact knowledge folders;
2. select legacy and designed HTML separately and together;
3. submit a job through the real panel;
4. assert request/task state carries the exact mode/folders/artifacts;
5. wait for completion through the real job flow;
6. assert web-provider calls are zero and retrieval starts after indexing;
7. assert unselected/deleted/superseded material is absent;
8. assert duplicates are consolidated and conflicts plus
   fact/opinion/inference/uncertainty are visible;
9. open both owner-scoped artifact routes;
10. reload and confirm option state/result actions;
11. render 1440x900 and 390x844 screenshots;
12. assert no console errors, failed requests, overflow, clipping, broken table
    scrolling, or broken in-document navigation.

## Semantic quality gate

Produce blind A/B artifacts from the same privacy-scrubbed corpus:

- baseline: `v0.1.9-ko` local/Obsidian Deep Research;
- candidate: Research-grade Editorial Synthesis.

The synthetic corpus defines ground-truth claims, intended duplicates,
conflicts, and uncertainty. Automated assertions cover evidence recall,
unsupported claims, conflict/uncertainty disclosure, source traceability, and
unselected-source contamination. A separate critic artifact assesses:

- evidence fidelity and hallucination suppression;
- important evidence recall and omissions;
- conflict handling;
- fact/opinion/inference boundaries;
- logical structure and causal leaps;
- insight beyond summary;
- reader/purpose fit;
- Korean flow, paragraph transitions, and information density;
- repetition, cliché, and generic AI prose;
- citation integrity.

The candidate cannot regress factuality, citation integrity, or core evidence
recall. It must improve structure/readability/duplicate suppression, conceal no
conflict or uncertainty, and produce zero samples judged as polished but
weakly grounded. If a real model is unavailable, structural evaluation remains
required and the subjective long-form quality comparison is explicitly
`Not-tested`; it cannot be reported as passed.

## External workflow research

GitHub public repository metadata was checked through the GitHub repository API
on 2026-07-29 KST. Stars and pushed dates are time-sensitive. This
implementation adopts workflow patterns only, copies no skill code, and adds no
external package/runtime dependency.

| Repository | Stars | License | Assessment and decision |
| --- | ---: | --- | --- |
| [WenyuChiou/ai-research-skills](https://github.com/WenyuChiou/ai-research-skills) | 177 | MIT | Adopt staged handoff, gap schema, and unsupported-claim boundaries; reject Zotero/Python runtime coupling. |
| [jin-s13/ai-research-writing-skill](https://github.com/jin-s13/ai-research-writing-skill) | 13 | MIT | Adopt claim/evidence engineering and reviewer critique despite low stars; structure matters more than popularity. |
| [pedrohcgs/claude-code-my-workflow](https://github.com/pedrohcgs/claude-code-my-workflow) | 1,432 | MIT | Adopt adversarial critic/fixer convergence; reject LaTeX/R/Beamer assumptions. |
| [wanshuiyin/Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) | 13,967 | MIT | Adopt Markdown-only stage artifacts and cross-review; reject autonomous experiment/GPU scope. |
| [AlterLab-IEU/AlterLab-Academic-Skills](https://github.com/AlterLab-IEU/AlterLab-Academic-Skills) | 53 | MIT | Adapt deterministic citation checking to selected local sources; reject external academic APIs as a local-only dependency. |
| [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) | 29,137 | MIT | Discovery index only; listed skills are not automatically trusted or suitable for private data. |
| [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | 23,811 | MIT | Adopt researcher/critic/verifier role separation; do not copy Claude-specific subagents. |
| [openai/codex](https://github.com/openai/codex) | 102,139 | Apache-2.0 | Reference for local Codex/skill hosting only; it is not a report-writing workflow. |
| [oso95/scroll-world](https://github.com/oso95/scroll-world) | 5,606 | MIT | Adopt scene continuity, portrait mobile composition, reduced-motion and portable vanilla-JS ideas for a later renderer; reject Higgsfield/ffmpeg as core dependencies. |

The selected pattern is source inventory/passport -> claim/evidence extraction
-> iterative local retrieval -> duplicate/conflict/uncertainty ledger ->
outline -> draft -> independent critic -> rewrite -> citation audit -> prose
polish.

## Opt-in generative-image layer

Status for this release-candidate scope:
`IMPLEMENTED AND E2E VERIFIED; OAUTH TEXT-ENDPOINT IMAGE CAPABILITY NOT
CONFIRMED`.

A read-only capability probe was performed against the configured
`/backend-api/codex/models` catalog on 2026-07-29. The catalog exposed
`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, and related Codex
models. Several accept image input and web search, but every model reported an
empty `experimental_supported_tools` list and no image-generation output tool.
Image input modality is not evidence of image generation capability. The
Odysseus OAuth text endpoint was not treated as an image API and no API-key
billed fallback was added.

OpenAI's official
[image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
documents `gpt-image-2` through the Image API and an `image_generation` tool in
the public Responses API. That public API is a separately authenticated API
surface and cannot be substituted automatically for the current ChatGPT/Codex
OAuth subscription bridge.

The implemented designed-HTML-only option provides
`없음 / 표지·배경만 / 표지 + 섹션 일러스트`. It uses the existing configured
image-type endpoint contract and `/images/generations`; environments without an
image model finish with a text-first designed report and an explicit fallback
status. The legacy artifact never consumes these assets.

The image layer:

- produce a privacy-scrubbed art-direction summary before any prompt leaves the
  app and never transmit private note text, names, internal figures, or paths;
- establish a coherent palette/style for cover, restrained texture, chapter
  dividers, conceptual editorial illustrations, and supporting ornaments;
- generate multiple candidates when useful, composite them into the actual
  HTML, then audit desktop/mobile/print and regenerate, reposition, tone down,
  or remove images that do not improve comprehension, structure, memory, or
  atmosphere;
- keep data charts, documentary evidence, and real-event depictions outside
  the illustration layer;
- store metadata-stripped local assets, meaningful Korean alt text, decorative
  `aria-hidden` treatment, offline rendering, prompt/model-version cache keys,
  same-owner cache isolation, asset-count/byte caps, and text-first graceful
  fallback;
- never auto-switch to an API-key-billed image endpoint;
- add image-free/image-enabled reports, adopted/rejected candidates, assets,
  art direction, and desktop/mobile/print screenshots to the user review
  package.

The deterministic browser E2E passed four fake image-generation calls through
the real UI -> API -> background job -> local asset -> offline HTML boundary.
The generated-image review sample used the Codex Desktop built-in image tool to
create three privacy-safe editorial assets, stripped metadata, embedded all
three locally as hero, section background, and ambient background, and passed
desktop, mobile, print, offline,
console, network, alt-text, and non-evidence-caption checks. This proves the
visual workflow and output, not OAuth image-API support inside Odysseus.

### Visual-role and layering contract

`VisualAssetSpec.visual_role` distinguishes:

- evidence figures;
- explanatory simulations;
- data dashboards backed by structured data;
- editorial heroes;
- section backgrounds;
- page ambient backgrounds;
- decorative accents.

Generated images are never treated as quantitative charts or documentary
evidence. Hero and section titles remain semantic HTML text over separate image
layers. Focal point, safe area, desktop/mobile aspect, overlay strength,
palette, alt text, print fallback, and reduced-motion behavior are carried by
the validated `DesignSpec`. The current Hero Composer uses a full-width local
image, real HTML typography, contrast scrim, responsive focal crop, explicit
generated-image disclosure, and static print fallback.

### Figma design-laboratory result

Figma was used as a design laboratory for the report capture, hierarchy, token,
and image-placement inspection. The connected account successfully created a
new design-lab file, but the authenticated team seat reported `View`; both
plugin execution and HTML-to-design capture returned `INVALID_ARGUMENT`.
Therefore new editable composition variants are `NOT TESTED` in Figma rather
than silently claimed as complete. The production renderer does not depend on
Figma, and the actual offline HTML was still audited through browser screenshots.
The earlier report capture and DesignSpec capture remain in the review package.
Figma's official MCP access table gives Starter and View/Collab seats up to six
read tool calls per month, with per-minute limits in addition; only selected
write tools are exempt. Figma lookup and analysis therefore cannot be a
per-report or always-on pipeline even when a write operation is available.

Figma is not a required adapter. Google Stitch is the preferred design-lab
candidate for a later capability probe, but it is also optional. Google
Codelabs' 2026 Stitch MCP guide requires a Stitch account, a separately issued
Stitch API key, Node.js 18+, and a billing-enabled Google Cloud project.
Signing into the Stitch UI with Google OAuth is therefore not proof that MCP is
authenticated or free of charge. The current Codex tool catalog exposes no
callable Stitch connector, so Stitch design generation is `NOT TESTED`.

No billable call, Cloud billing activation, or new API-key provisioning is
performed in this release candidate. A future Stitch adapter may receive only
an explicitly approved, privacy-scrubbed `ContextProfile` and design brief. It
must never receive raw private notes, email content, names, internal figures,
absolute paths, OAuth/session data, or secrets. Stitch API keys and Cloud
project identifiers remain in OS keychain/environment boundaries and never
enter source, logs, artifacts, screenshots, or Second Brain records.
Driving the Stitch website through Computer Use may be acceptable for an
occasional, explicitly approved prototype, but it is slower and vulnerable to
UI changes. It cannot become a production report-generation dependency.

Official capability references checked on 2026-07-29:

- Figma MCP plan access and limits:
  https://developers.figma.com/docs/figma-mcp-server/rate-limits-access/
- Google Stitch MCP setup codelab:
  https://codelabs.developers.google.com/design-to-code-with-antigravity-stitch
- Google Stitch iteration and Antigravity export overview:
  https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-updates/

## Generative Report Design System direction

The long-term invariant is not one premium theme or a small list of color
presets. Each report produces a deterministic `ContextProfile` that records its
genre, audience, purpose, tone, narrative shape, evidence density, source
modality, emotional temperature, data/image weight, uncertainty treatment,
accessibility requirements, and useful visual metaphor.

That profile selects and combines a validated design grammar:

- layout topology such as editorial spread, split narrative, cinematic hero,
  timeline, atlas, dossier, product showcase, technical blueprint, data-led
  brief, or minimal paper;
- Korean display/body typography and line-breaking rules;
- grid, density, spacing, rhythm, palette, and surface treatment;
- hero, transition, quote, table, source, conflict, and limitation grammar;
- image role, focal crop, safe-area, and overlay rules;
- restrained motion plus mobile, print, and reduced-motion fallbacks.

`DesignManifest` stores the selected composition, alternatives, context-based
rationale, reproducible seed, and variation ID. A future design planner may
propose multiple schema-valid candidates, but the renderer remains
deterministic and cannot receive arbitrary HTML, CSS, or JavaScript. Candidate
screenshots, DOM metrics, accessibility/performance rules, and an independent
visual critic decide whether to select, hybridize, or repair a design.

The current vertical slice proves two structurally distinct report families:
the image-integrated editorial overlay and the traditional management document
briefing. Product cinematic banner, evidence dossier/split narrative, minimal
paper, and scroll-story primitives remain explicit follow-up milestones. The
five-context diversity fixture—academic evidence report, operations management,
personal knowledge essay, future product simulation, and event timeline—must
prove differences in layout, typography, image strategy, rhythm, and motion,
not mere palette swaps, before the design grammar is considered generalized.

External design labs implement a vendor-neutral adapter contract:

```text
design_lab.propose(redacted_context_profile, redacted_design_brief)
  -> candidate DesignSpec/DesignManifest
```

Figma, Stitch, Pencil, or another future laboratory can provide candidates,
but none can replace the deterministic fallback renderer or become a runtime
requirement. Disconnection, quota exhaustion, adapter failure, or user opt-out
must still produce the self-contained designed HTML. Acceptance includes
Stitch-unavailable fallback, secret redaction, and zero private-source egress.
Successful external experiments are generalized into local design tokens,
composition primitives, prompt fragments, and renderer rules, then reused
without another vendor call.

## Renderer polymorphism and Scroll World direction

Research is performed once. A structured report model and its evidence
contract should be consumed by one or more presentation renderers:

- `문서형`: current legacy renderer and the management default;
- `에디토리얼 디자인형`: current deterministic designed renderer;
- `스크롤 스토리형`: later progressive-enhancement renderer mapping major
  sections to sticky visual scenes;
- `시네마틱형`: later capability-gated renderer, never a core dependency;
- future timeline, atlas/gallery, and executive-brief presets.

The user may eventually select multiple renderers for the same report. Style
recommendations can be model-assisted but the selected styles and generated
artifacts must remain explicit. The current interface is documented in
`docs/plans/2026-07-29-report-renderer-ir.md`.

## Verification gate

- changed Python modules compile;
- targeted research/RAG/artifact/security tests pass;
- the complete private RAG/research/artifact test family passes;
- full pytest passes with every skip/xfailed result explained;
- changed JavaScript passes `node --check`;
- `git diff --check` passes;
- isolated `/api/health` responds successfully;
- Playwright E2E and screenshot inspection pass;
- secret scan finds no credentials, tokens, real private paths, or personal
  content in diff/log/screenshot/Second Brain updates;
- performance fixture records indexing/search time and proves unchanged-file
  embed call count is zero.

## User review package

Keep the review package outside disposable worktree/temp storage at:

`/Users/flytothesky/Downloads/odysseus-qa/editorial-research-rc-2026-07-29`

Its `README.md` must link relatively to every artifact and record
`PASS / FAIL / NOT TESTED`, generation time, non-secret model identifier, and
fixture identifier. It includes:

- a privacy-safe fixture description listing intended facts, opinions,
  duplicates, conflicts, uncertainty, injection text, distractors, expected
  claims, and intentionally unanswerable questions;
- baseline and candidate reports;
- legacy HTML, designed HTML, Markdown, and session JSON where selected;
- at least one general report, one management report, and one mixed personal
  knowledge report;
- full-page 1440x900 and 390x844 screenshots for each HTML plus focused
  screenshots for wide tables, table of contents, citations, conflicts, and
  limitations;
- a blind A/B semantic-quality table, deterministic assertions, independent
  critic findings, and correction history;
- privacy-scrubbed E2E evidence for UI -> API -> job -> artifacts, console and
  network status, web-provider call count, stale-source count, unselected-source
  contamination, commands, and exit codes.

Before handoff, verify that every link resolves and scan all package files for
credentials, tokens, email content, real vault paths, and absolute private
source paths. The final response provides clickable absolute links to the
README, representative HTML/Markdown/JSON artifacts, and desktop/mobile
screenshots. Agent visual review is reported separately from pending user
approval; no claim of visual perfection is permitted.

## Completion record

The final evidence table must use:

`요구사항 | 검증 방법/명령 | 결과 | 증거 경로 | 잔여 위험`

Only after the gate passes: create a Lore Protocol commit and update the
Second Brain output contract, decision log, risk prevention, session record,
and active handoff. Push, tag, and release remain out of scope.
