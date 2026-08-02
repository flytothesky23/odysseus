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
    selected_paths: selected,
    kordoc_job_ids: sanitizeJobIds(input.kordoc_job_ids),
    law_job_ids: sanitizeJobIds(input.law_job_ids),
  };
}

export function buildContractReviewChatContext(value) {
  const state = sanitizePersistedState(value);
  return {
    snapshot_id: state.snapshot_id,
    vault_id: state.vault_id,
    selected_paths: state.selected_paths,
    kordoc_job_ids: state.kordoc_job_ids,
    law_job_ids: state.law_job_ids,
  };
}

export function buildVaultSearchRequest(value, query, includeBody, candidatePaths = []) {
  const state = sanitizePersistedState(value);
  return {
    snapshot_id: state.snapshot_id,
    vault_id: state.vault_id,
    query: String(query || '').trim(),
    include_body: Boolean(includeBody),
    candidate_paths: (Array.isArray(candidatePaths) ? candidatePaths : [])
      .filter(path => isRelativePath(path))
      .slice(0, 20),
  };
}
