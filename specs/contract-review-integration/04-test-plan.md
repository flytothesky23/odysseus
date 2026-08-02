# Verification plan

## Deterministic service tests

- Korean and Latin metadata queries across filename, title, path, and aliases.
- Owner isolation in auth-enabled mode and the single empty-owner namespace when auth is disabled.
- Zero body reads for metadata search; bounded reads and delta-only follow-up retrieval.
- Stale modification/deletion, Vault identity change, symlink/path escape, credential names, and unreadable placeholder errors.
- Kordoc PDF/Office/HWP fixtures, progress states, cancel, timeout, parser failure, descriptor swap, inventory failure, and allowlist rejection.
- Korean Law statute/decision evidence, follow-up reuse, 429/runtime/configuration diagnostics, and descriptor swap.
- Six-block result validation, evidence-type separation, KST timestamps, and actual-versus-estimated usage.
- No report save until the explicit report endpoint is called.

## Integration and browser tests

- Search → Chat → same-evidence follow-up, including reuse and delta strategy.
- Contract Review prompt injection before normal context compaction and generic MCP executor rejection.
- Native UI entry, metadata search, bounded body search, parsing progress, cancellation, retry, official-law lookup, chat render, and explicit save.
- Existing Chat, Deep Research, renderer gallery, sessions, model/reasoning selection, context budget, and metrics remain green.

## Completion evidence

- Targeted tests first, then full pytest, Python compilation, JavaScript syntax checks, existing static/lint checks, `git diff --check`, and real browser E2E.
- Optional installed Kordoc/Korean Law smoke is reported as PASS, FAIL, or NOT TESTED; absence of configuration is never recorded as success.
