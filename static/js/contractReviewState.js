// Identifier-only browser state for Contract Review. Raw evidence never enters
// localStorage; the server resolves and revalidates these opaque ids per turn.

function isRelativePath(value, allowDot = false) {
  if (typeof value !== 'string') return false;
  const path = value.trim().replace(/\\/g, '/');
  if (allowDot && path === '.') return true;
  if (!path || path.startsWith('/') || /^[A-Za-z]:\//.test(path)) return false;
  return !path.split('/').some(part => !part || part === '.' || part === '..' || part.startsWith('.'));
}
function sanitizeJobIds(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map(String).filter(id => /^[a-f0-9]{32}$/.test(id)))].slice(0, 20);
}
function sanitizeRuntimeId(value) {
  const runtimeId = typeof value === 'string' ? value : '';
  return /^[a-f0-9]{32}$/.test(runtimeId) ? runtimeId : '';
}

export function sanitizeNoteScope(value) {
  const input = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const defaultIncluded = input.default_included !== false;
  const deduped = new Map();
  for (const rule of Array.isArray(input.rules) ? input.rules.slice(0, 2000) : []) {
    if (!rule || typeof rule !== 'object' || typeof rule.included !== 'boolean') continue;
    const path = typeof rule.path === 'string' ? rule.path.trim().replace(/\\/g, '/') : '';
    if (!isRelativePath(path)) continue;
    if (deduped.has(path)) deduped.delete(path);
    deduped.set(path, { path, included: rule.included });
  }
  return { default_included: defaultIncluded, rules: [...deduped.values()] };
}

export function updateSelectedPathSelection(current, path, checked) {
  const selected = new Set(
    (Array.isArray(current) ? current : []).filter(candidate => isRelativePath(candidate)),
  );
  const normalizedPath = typeof path === 'string' ? path.trim().replace(/\\/g, '/') : '';
  if (!isRelativePath(normalizedPath)) return [...selected].slice(0, 8);
  if (checked) selected.add(normalizedPath);
  else selected.delete(normalizedPath);
  return [...selected].slice(0, 8);
}

export function sanitizePersistedState(value) {
  const input = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const selected = Array.isArray(input.selected_paths)
    ? [...new Set(input.selected_paths.filter(path => isRelativePath(path)))].slice(0, 8)
    : [];
  const vaultPath = String(input.vault_path || '.');
  return {
    active: Boolean(input.active),
    snapshot_id: String(input.snapshot_id || '').slice(0, 128),
    vault_id: String(input.vault_id || '').slice(0, 128),
    vault_path: isRelativePath(vaultPath, true) ? vaultPath : '.',
    note_scope: sanitizeNoteScope(input.note_scope),
    selected_paths: selected,
    kordoc_job_ids: sanitizeJobIds(input.kordoc_job_ids),
    law_job_ids: sanitizeJobIds(input.law_job_ids),
    mcp_runtime_id: sanitizeRuntimeId(input.mcp_runtime_id),
    mcp_runtime_stale: Boolean(input.mcp_runtime_stale),
  };
}

export function reconcileMcpRuntimeState(value, runtimeId) {
  const state = sanitizePersistedState(value);
  const currentRuntimeId = sanitizeRuntimeId(runtimeId);
  const hasMcpJobs = Boolean(state.kordoc_job_ids.length || state.law_job_ids.length);
  if (hasMcpJobs && (!currentRuntimeId || state.mcp_runtime_id !== currentRuntimeId)) {
    return {
      ...state,
      active: false,
      kordoc_job_ids: [],
      law_job_ids: [],
      mcp_runtime_id: currentRuntimeId,
      mcp_runtime_stale: true,
    };
  }
  if (!hasMcpJobs && currentRuntimeId) {
    return { ...state, mcp_runtime_id: currentRuntimeId };
  }
  if (hasMcpJobs) {
    return { ...state, mcp_runtime_id: currentRuntimeId, mcp_runtime_stale: false };
  }
  return state;
}

export function buildContractReviewChatContext(value) {
  const state = sanitizePersistedState(value);
  return {
    snapshot_id: state.snapshot_id,
    vault_id: state.vault_id,
    note_scope: state.note_scope,
    selected_paths: state.selected_paths,
    kordoc_job_ids: state.kordoc_job_ids,
    law_job_ids: state.law_job_ids,
    mcp_runtime_id: state.mcp_runtime_id,
  };
}

export function buildVaultSearchRequest(value, query, includeBody, candidatePaths = []) {
  const state = sanitizePersistedState(value);
  return {
    snapshot_id: state.snapshot_id,
    vault_id: state.vault_id,
    note_scope: state.note_scope,
    query: String(query || '').trim(),
    include_body: Boolean(includeBody),
    candidate_paths: (Array.isArray(candidatePaths) ? candidatePaths : [])
      .filter(path => isRelativePath(path))
      .slice(0, 20),
  };
}
