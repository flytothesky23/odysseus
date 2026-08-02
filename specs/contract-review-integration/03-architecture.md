# Current Odysseus integration

## Backend

- `src/contract_review.py`: filesystem identity, metadata index, bounded retrieval, owner-scoped scope/reuse, MCP descriptor pinning, jobs, result validation, and rendering data.
- `routes/contract_review_routes.py`: authenticated owner-aware REST boundary and explicit report save.
- `routes/chat_helpers.py`: optional untrusted Contract Review context injected before context compaction.
- `routes/chat_routes.py`: form/JSON context preparation and fail-closed Contract Review tool policy.
- `src/tool_policy.py` and `src/tool_execution.py`: namespace-level MCP dispatch backstop.
- `src/mcp_manager.py`: complete non-secret tool descriptors and inventory generation.

## Frontend

- `static/js/contractReviewState.js`: sanitized identifier-only local state.
- `static/js/contractReview.js`: native workspace, progress/cancel/retry, selection, law lookup, explicit report save.
- `static/js/contractReviewRenderer.js`: safe structured result renderer.
- Existing chat modules supply selected context on send and render validated result metadata on live and restored replies.

## Operational boundary

Automated tests and browser E2E run with an isolated data directory and non-production port. Optional live MCP smoke uses disposable non-identifying fixtures and is reported separately from deterministic tests.
