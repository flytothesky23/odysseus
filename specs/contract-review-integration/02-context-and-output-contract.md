# Context and output contract

## Retrieval order

1. `metadata`: no note bodies read.
2. `candidate_body`: at most the configured candidate count and character budget.
3. `selected_evidence`: only explicitly selected, freshly revalidated evidence enters chat.
4. `follow_up`: reuse identical evidence handles; read only new or changed candidates.

Every prepared context includes a deterministic scope fingerprint and reports `fresh`, `reuse`, or `delta`. A stale note, missing file, changed Vault root, changed owner, or changed MCP descriptor invalidates reuse.

## Model boundary

Contract Review evidence is inserted as an untrusted context block before the existing compaction and context-budget pass. It cannot override system instructions. The normal Odysseus endpoint, model, reasoning, compaction, and metrics path remains authoritative.

## Result schema

The persisted and rendered schema is `contract-review.v2` with an Asia/Seoul ISO 8601 timestamp and these required blocks:

1. `review_summary`
2. `local_document_evidence`
3. `vault_note_evidence`
4. `official_legal_evidence`
5. `model_interpretation`
6. `uncertainty_and_follow_up`

Each evidence item carries an evidence type, opaque source id, relative/display locator, excerpt or bounded text, and verification state. Model conclusions never masquerade as source text.

Usage metadata distinguishes `actual`, `estimated`, and `unavailable`. Only provider-reported usage may use `actual`.

## Persistence

Chat messages may persist the validated structured result in owner-scoped session metadata for renderer restoration. Report creation is a separate explicit POST action and is never called from search, parse, law lookup, context preparation, or ordinary chat completion.
