# Contract Review Workspace v2

## Outcome

Odysseus remains the application shell. Contract Review is a native, read-only evidence workspace that reuses the existing session, endpoint/model, reasoning, context-budget, compaction, metrics, MCP manager, and Documents systems.

## Required user flow

1. Select an Obsidian Vault within the current Odysseus workspace.
2. Index only note metadata: title, filename/stem, Vault-relative path, aliases, size, modified time, and a stat fingerprint.
3. Search metadata first, select an owner-scoped candidate set, then read only a bounded subset of candidate bodies.
4. Parse a selected local contract through a pinned read-only Kordoc tool.
5. Retrieve official statute or decision evidence through a pinned Korean Law tool.
6. Send only the selected, revalidated, bounded evidence into the normal Odysseus chat context.
7. Reuse unchanged evidence for a follow-up and retrieve only changed/new evidence when a delta is required.
8. Render document evidence, Vault evidence, official legal evidence, model interpretation, and uncertainty as visibly distinct sections.
9. Save a report to Odysseus Documents only after an explicit save action.

## Non-goals

- No Doculytics application stack, Firebase state, or separate CLI/thread budget system.
- No body-wide Vault ingestion, background indexing of private content, or implicit report persistence.
- No direct model access to generic MCP, filesystem, shell, or document mutation tools during a Contract Review turn.
- No claims that estimated tokens are provider-measured usage.
