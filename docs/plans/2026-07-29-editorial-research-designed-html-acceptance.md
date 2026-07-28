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

GitHub public repository metadata was checked on 2026-07-29 KST. Star counts
and pushed dates are time-sensitive. `NOASSERTION` means no code or skill text
may be reused without a separate manual license review. This implementation
adopts workflow ideas only and adds no external package/runtime dependency.

| Repository | Stars | License | Assessment and decision |
| --- | ---: | --- | --- |
| [academic-research-skills-codex](https://github.com/Imbad0202/academic-research-skills-codex) | 7,267 | NOASSERTION | Adopt source passport, integrity gates, staged local workflow; do not vendor. |
| [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) | 39,902 | NOASSERTION | Adopt claim audit, critic/re-review, citation verification patterns only. |
| [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills) | 5,604 | MIT | Adopt claim-evidence and section-flow rubric; localize for Korean long form. |
| [econ-writing-skill](https://github.com/hanlulong/econ-writing-skill) | 497 | MIT | Adopt genre-specific scoring and anti-generic-prose rubric for management reports. |
| [ComputationalReviewTemplate](https://github.com/AllenNeuralDynamics/ComputationalReviewTemplate) | 4 | MIT | Adopt actor/critic/citation-verifier separation; reject deployment scaffolding. |
| [book-genesis-v4](https://github.com/felipelobomotta-blip/book-genesis-v4) | 81 | MIT | Adopt blind evaluation gate; reject book-specific automation. |
| [write-prose](https://github.com/AnswerDotAI/skill-plugins/blob/main/plugins/codex-aai/skills/write-prose/SKILL.md) | 5 | Apache-2.0 | Use only as final prose-polish rubric, never as the research engine. |
| [Cat_synthesis_lab](https://github.com/jy1529098645-gif/Cat_synthesis_lab) | 0 | MIT | Retain citation-cross-check idea; reject as a core reference due to weak adoption evidence. |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | 221,780 | MIT | Use selected reviewer vocabulary only; repository-wide stars do not validate its writing workflow. |
| [Codex-Academic-Skills](https://github.com/Epsilon617/Codex-Academic-Skills) | 157 | MIT | Keep as a discovery watchlist, not an implementation model. |

The selected pattern is source inventory/passport -> claim/evidence extraction
-> iterative local retrieval -> duplicate/conflict/uncertainty ledger ->
outline -> draft -> independent critic -> rewrite -> citation audit -> prose
polish.

## Optional generative-image milestone

Status for this release-candidate scope: `NOT IMPLEMENTED — CAPABILITY NOT
CONFIRMED ON THE OAUTH SUBSCRIPTION PATH`.

A read-only capability probe was performed against the configured
`/backend-api/codex/models` catalog on 2026-07-29. The catalog exposed
`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, and related Codex
models. Several accept image input and web search, but every model reported an
empty `experimental_supported_tools` list and no image-generation output tool.
Image input modality is not evidence of image generation capability. No image
generation request was sent.

OpenAI's official
[image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
documents `gpt-image-2` through the Image API and an `image_generation` tool in
the public Responses API. That public API is a separately authenticated API
surface and cannot be substituted automatically for the current ChatGPT/Codex
OAuth subscription bridge. The app's subscription payload builder currently
supports text Responses inputs and reasoning only; the separate gallery path
uses image-type endpoints and `/images/generations`.

If a future subscription model catalog or explicitly documented endpoint
exposes an image-generation tool, implement it as a designed-HTML-only option
with levels `없음 / 표지·배경 / 섹션 일러스트 포함`. The milestone must:

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
  asset-count/byte caps, and text-first graceful fallback;
- never auto-switch to an API-key-billed image endpoint;
- add image-free/image-enabled reports, adopted/rejected candidates, assets,
  art direction, and desktop/mobile/print screenshots to the user review
  package.

This milestone must not delay or mask the core local research, writer,
security, E2E, and semantic-quality gates.

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
