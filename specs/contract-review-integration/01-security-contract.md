# Security and identity contract

## Owner and scope

- Every Vault snapshot, evidence handle, parser job, law job, and session scope is stamped with the effective owner.
- Auth-enabled requests may only read objects owned by the current user. Auth-disabled mode uses the single empty-owner namespace.
- Route checks and service checks are both required; guessing an opaque identifier must not cross owners.

## Filesystem identity

- Browser state and API payloads contain only Vault-relative or workspace-relative paths.
- Absolute paths, parent traversal, empty components, symlinked files/directories, hidden files, credential filenames, and paths outside the selected roots are rejected.
- A Vault is identified by its canonical root plus device/inode identity. That identity, the workspace root, and the `.obsidian` marker are revalidated at index, search, open, context preparation, reuse, and analysis boundaries.
- Each note/document is identified by an admission-time stat fingerprint. The path, regular-file type, root containment, and fingerprint are revalidated before and after body/parser access.
- Placeholder or on-demand cloud files that cannot be read are reported as unavailable evidence, never as a successful empty result.

## MCP identity and fail-closed behavior

- Contract Review discovers candidate tools from the current MCP manager inventory. Inventory access, policy interpretation, annotations, or connection-status failures make the adapter unavailable.
- Admission pins server id/name, connection identity/status, tool name, qualified name, schema, annotations, and MCP inventory generation in a descriptor fingerprint.
- The same descriptor and file identity are checked immediately before execution and again before evidence publication. Any mismatch is a server/tool swap error.
- Kordoc allows read-only parser tools only; write/form-fill/comparison variants are rejected.
- Korean Law allows only the dedicated official-evidence search/detail tools.
- A Contract Review chat turn disables all generic MCP calls at both prompt/schema composition and executor dispatch. Dedicated adapters provide the only MCP path.

## Data minimization

- Long-lived state stores opaque ids, relative paths, metadata, fingerprints, and bounded source descriptors only.
- Raw Vault bodies, document text, prompts, conversations, credentials, and absolute paths are not written to browser storage, Git-tracked artifacts, logs, metrics ledgers, or operating notes.
- Parser and law failures remain typed failures; they are not converted to successful evidence or silent fallbacks.
