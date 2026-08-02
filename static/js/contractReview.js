import Storage, { KEYS } from './storage.js';
import uiModule from './ui.js';
import workspaceModule from './workspace.js';
import sessionModule from './sessions.js';
import { makeWindowDraggable } from './windowDrag.js';
import {
  buildContractReviewChatContext,
  buildVaultSearchRequest,
  sanitizePersistedState,
  updateSelectedPathSelection,
} from './contractReviewState.js';

let API_BASE = '';
let modal = null;
let indexedNotes = [];
let visibleNotes = [];
let activeJobId = null;
let profileLoaded = false;

function loadState() {
  return sanitizePersistedState(Storage.getJSON(KEYS.CONTRACT_REVIEW, {}));
}

function saveState(next) {
  const safe = sanitizePersistedState(next);
  Storage.setJSON(KEYS.CONTRACT_REVIEW, safe);
  syncIndicator(safe);
  return safe;
}

function syncIndicator(state = loadState()) {
  const button = document.getElementById('overflow-contract-review-btn');
  if (button) button.classList.toggle('active', state.active);
  try { document.dispatchEvent(new CustomEvent('overflow-state-change')); } catch (_) {}
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}/api/contract-review${path}`, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.message || payload.detail?.message || payload.detail || `Request failed (${response.status})`);
    error.code = payload.error || payload.detail?.error || 'request_failed';
    throw error;
  }
  return payload;
}

function setStatus(message, tone = '') {
  const target = modal?.querySelector('#contract-review-status');
  if (!target) return;
  target.textContent = message;
  target.dataset.tone = tone;
}

function syncWorkspaceReadout() {
  const target = modal?.querySelector('#contract-review-workspace');
  if (!target) return;
  const workspace = workspaceModule.getWorkspace();
  target.textContent = workspace || '선택되지 않음';
  target.title = workspace || '';
}

function renderServerOptions(select, servers, emptyLabel) {
  if (!select) return;
  select.innerHTML = servers.length
    ? servers.map(server => `<option value="${uiModule.esc(server.id)}">${uiModule.esc(server.name)}</option>`).join('')
    : `<option value="">${uiModule.esc(emptyLabel)}</option>`;
}

async function loadProfile() {
  if (profileLoaded) return;
  const profile = await api('/profile');
  renderServerOptions(
    modal.querySelector('#contract-review-kordoc-server'),
    Array.isArray(profile.kordoc_servers) ? profile.kordoc_servers : [],
    'Kordoc unavailable',
  );
  renderServerOptions(
    modal.querySelector('#contract-review-law-server'),
    Array.isArray(profile.korean_law_servers) ? profile.korean_law_servers : [],
    'Korean Law unavailable',
  );
  profileLoaded = true;
  if (!profile.inventory_available) setStatus('MCP inventory를 읽을 수 없습니다.', 'error');
}

function selectedPaths() {
  return loadState().selected_paths;
}

function renderNotes(items) {
  const list = modal?.querySelector('#contract-review-results');
  if (!list) return;
  const chosen = new Set(loadState().selected_paths);
  if (!items.length) {
    list.innerHTML = '<div class="workspace-empty">일치하는 Markdown 노트가 없습니다.</div>';
    return;
  }
  list.innerHTML = items.map(note => {
    const path = String(note.path || '');
    const aliases = Array.isArray(note.aliases) && note.aliases.length
      ? `<div class="muted">Aliases: ${uiModule.esc(note.aliases.join(', '))}</div>` : '';
    const excerpt = note.excerpt ? `<div class="muted">${uiModule.esc(note.excerpt.slice(0, 420))}</div>` : '';
    return `<label class="contract-review-note"><input type="checkbox" data-contract-note="${uiModule.esc(path)}" ${chosen.has(path) ? 'checked' : ''}>
      <span><strong>${uiModule.esc(note.title || note.stem || path)}</strong><div class="muted">${uiModule.esc(path)} · ${uiModule.esc(note.evidence_level || 'metadata')}</div>${aliases}${excerpt}</span></label>`;
  }).join('');
  list.querySelectorAll('[data-contract-note]').forEach(input => input.addEventListener('change', () => {
    const state = loadState();
    saveState({
      ...state,
      selected_paths: updateSelectedPathSelection(
        state.selected_paths,
        input.dataset.contractNote,
        input.checked,
      ),
    });
  }));
}

async function indexVault() {
  const workspace = workspaceModule.getWorkspace();
  if (!workspace) throw new Error('먼저 Odysseus Workspace를 선택하세요.');
  const vaultPath = modal.querySelector('#contract-review-vault-path').value.trim() || '.';
  setStatus('Vault metadata를 인덱싱하는 중…');
  const indexed = await api('/vault/index', { method: 'POST', body: JSON.stringify({ workspace, vault_path: vaultPath }) });
  indexedNotes = indexed.notes || [];
  visibleNotes = indexedNotes;
  saveState({
    active: true, snapshot_id: indexed.snapshot_id, vault_id: indexed.vault_id,
    vault_path: vaultPath, selected_paths: [], kordoc_job_ids: [], law_job_ids: [],
  });
  renderNotes(visibleNotes);
  setStatus(`${indexed.note_count}개 노트 metadata 인덱싱 완료 · 본문 읽기 0회`, 'ok');
}

async function searchVault(includeBody) {
  const state = loadState();
  const query = modal.querySelector('#contract-review-query').value.trim();
  if (!state.snapshot_id) throw new Error('먼저 Vault metadata를 인덱싱하세요.');
  if (!query) throw new Error('검색어를 입력하세요.');
  const candidates = includeBody ? visibleNotes.map(note => note.path).slice(0, 20) : [];
  setStatus(includeBody ? '제한된 후보 본문을 확인하는 중…' : 'Metadata만 검색하는 중…');
  const result = await api('/vault/search', {
    method: 'POST',
    body: JSON.stringify(buildVaultSearchRequest(state, query, includeBody, candidates)),
  });
  visibleNotes = result.results || [];
  renderNotes(visibleNotes);
  setStatus(includeBody
    ? `${visibleNotes.length}개 일치 · 후보 본문 ${result.body_read_count}개 읽음`
    : `${visibleNotes.length}개 metadata 일치 · 본문 읽기 0회`, 'ok');
}

async function pollJob(job) {
  activeJobId = job.id;
  modal.querySelector('#contract-review-cancel').disabled = false;
  let current = job;
  try {
    while (['admitted', 'running', 'cancelling'].includes(current.state)) {
      setStatus(current.message || `작업 상태: ${current.stage || current.state}`);
      await new Promise(resolve => setTimeout(resolve, 350));
      current = await api(`/jobs/${encodeURIComponent(job.id)}`);
    }
  } finally {
    activeJobId = null;
    modal.querySelector('#contract-review-cancel').disabled = true;
  }
  if (current.state === 'cancelled') {
    setStatus('작업이 취소되었습니다.');
    return current;
  }
  if (current.state !== 'completed') {
    const error = new Error(current.message || '작업이 실패했습니다.');
    error.code = current.error || 'job_failed';
    throw error;
  }
  return current;
}

async function parseDocument() {
  const workspace = workspaceModule.getWorkspace();
  const filePath = modal.querySelector('#contract-review-document-path').value.trim();
  const serverId = modal.querySelector('#contract-review-kordoc-server').value;
  if (!workspace) throw new Error('먼저 Odysseus Workspace를 선택하세요.');
  if (!filePath) throw new Error('Workspace 상대 문서 경로를 입력하세요.');
  if (!serverId) throw new Error('연결된 Kordoc MCP가 없습니다. Settings에서 먼저 연결하세요.');
  const started = await api('/kordoc/jobs', { method: 'POST', body: JSON.stringify({
    server_id: serverId,
    tool: modal.querySelector('#contract-review-kordoc-tool').value,
    workspace, file_path: filePath, arguments: {},
  }) });
  const completed = await pollJob(started);
  if (completed.state !== 'completed') return;
  const output = String(completed.result?.output || '');
  modal.querySelector('#contract-review-parser-output').textContent = output.slice(0, 12000);
  saveState({ ...loadState(), kordoc_job_ids: [...loadState().kordoc_job_ids, completed.id] });
  setStatus('Kordoc read-only parsing 완료.', 'ok');
}

async function searchLaw() {
  const query = modal.querySelector('#contract-review-law-query').value.trim();
  const serverId = modal.querySelector('#contract-review-law-server').value;
  const tool = modal.querySelector('#contract-review-law-tool').value;
  if (!query) throw new Error('법령 검색어를 입력하세요.');
  if (!serverId) throw new Error('연결된 Korean Law MCP가 없습니다. Settings에서 먼저 연결하세요.');
  const started = await api('/law/jobs', { method: 'POST', body: JSON.stringify({
    server_id: serverId,
    tool,
    arguments: tool === 'search_decisions'
      ? { domain: 'precedent', query, display: 5 }
      : { query, display: 5 },
  }) });
  const completed = await pollJob(started);
  if (completed.state !== 'completed') return;
  modal.querySelector('#contract-review-law-output').textContent = String(completed.result?.output || '').slice(0, 12000);
  saveState({ ...loadState(), law_job_ids: [...loadState().law_job_ids, completed.id] });
  setStatus('공식 법률 근거 조회 완료.', 'ok');
}

async function cancelJob() {
  if (!activeJobId) return;
  await api(`/jobs/${encodeURIComponent(activeJobId)}`, { method: 'DELETE' });
  setStatus('취소 요청을 처리했습니다.');
}

function latestResult() {
  const bubbles = [...document.querySelectorAll('.msg-ai')].reverse();
  return bubbles.map(bubble => bubble._contractReviewResult).find(Boolean) || null;
}

async function saveReport() {
  const result = latestResult();
  const sessionId = sessionModule.getCurrentSessionId?.();
  if (!result) throw new Error('저장할 검증된 Contract Review 결과가 없습니다.');
  if (!sessionId) throw new Error('현재 채팅 세션이 없습니다.');
  const title = modal.querySelector('#contract-review-report-title').value.trim() || 'Contract Review';
  const saved = await api('/reports', {
    method: 'POST', body: JSON.stringify({ session_id: sessionId, title, result }),
  });
  setStatus(`Odysseus Documents에 명시적으로 저장했습니다: ${saved.title}`, 'ok');
}

function wrapped(action) {
  return async () => {
    try { await action(); }
    catch (error) { setStatus(`${error.code ? `${error.code}: ` : ''}${error.message}`, 'error'); }
  };
}

function getModal() {
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'contract-review-modal';
  modal.className = 'modal';
  modal.style.display = 'none';
  modal.innerHTML = `<div class="modal-content contract-review-modal-content">
    <div class="modal-header"><h4>Contract Review Workspace</h4><button class="close-btn" id="contract-review-close" aria-label="Close">✖</button></div>
    <div class="modal-body contract-review-body">
      <p class="muted">읽기 전용 · 상대경로와 식별자만 저장 · metadata 우선, 선택 후보 본문만 제한적으로 조회</p>
      <section class="contract-review-section"><h5>1. Obsidian Vault</h5>
        <div class="contract-review-row"><button class="confirm-btn" id="contract-review-workspace-select">Select Odysseus Workspace</button><span id="contract-review-workspace" class="muted contract-review-workspace-readout">선택되지 않음</span></div>
        <div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-vault-path" value="." placeholder="Workspace-relative Vault path"><button class="confirm-btn confirm-btn-primary" id="contract-review-index">Metadata index</button></div>
        <div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-query" placeholder="제목, 파일명, 상대경로, aliases"><button class="confirm-btn" id="contract-review-search">Search metadata</button><button class="confirm-btn" id="contract-review-body-search">Check bounded bodies</button></div>
        <div id="contract-review-results" class="contract-review-results"></div>
      </section>
      <section class="contract-review-section"><h5>2. Local document · Kordoc MCP</h5>
        <div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-document-path" placeholder="documents/contract.pdf"><select class="contract-review-server" id="contract-review-kordoc-server" aria-label="Kordoc server"><option value="">Loading Kordoc…</option></select><select id="contract-review-kordoc-tool"><option>parse_document</option><option>detect_format</option><option>parse_metadata</option><option>parse_pages</option><option>parse_table</option><option>parse_chunks</option><option>parse_form</option></select><button class="confirm-btn" id="contract-review-parse">Parse</button></div>
        <pre id="contract-review-parser-output" class="contract-review-output"></pre>
      </section>
      <section class="contract-review-section"><h5>3. Official Korean Law evidence</h5>
        <div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-law-query" placeholder="법령명 또는 판례 검색어"><select class="contract-review-server" id="contract-review-law-server" aria-label="Korean Law server"><option value="">Loading Korean Law…</option></select><select id="contract-review-law-tool"><option>search_law</option><option>search_decisions</option></select><button class="confirm-btn" id="contract-review-law-search">Lookup</button></div>
        <pre id="contract-review-law-output" class="contract-review-output"></pre>
      </section>
      <section class="contract-review-section"><h5>4. Explicit report save</h5><div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-report-title" value="Contract Review"><button class="confirm-btn" id="contract-review-save">Save latest validated result</button></div></section>
      <p id="contract-review-status" class="contract-review-status" aria-live="polite"></p>
    </div>
    <div class="modal-footer"><button class="confirm-btn confirm-btn-secondary" id="contract-review-cancel" disabled>Cancel running job</button><button class="confirm-btn confirm-btn-secondary" id="contract-review-deactivate">Deactivate</button><button class="confirm-btn confirm-btn-primary" id="contract-review-use">Use selected evidence in Chat</button></div>
  </div>`;
  document.body.appendChild(modal);
  modal.querySelector('#contract-review-close').addEventListener('click', closeContractReview);
  modal.querySelector('#contract-review-workspace-select').addEventListener('click', async () => {
    await workspaceModule.openWorkspaceBrowser();
    document.getElementById('workspace-use')?.addEventListener('click', syncWorkspaceReadout, { once: true });
  });
  modal.querySelector('#contract-review-index').addEventListener('click', wrapped(indexVault));
  modal.querySelector('#contract-review-search').addEventListener('click', wrapped(() => searchVault(false)));
  modal.querySelector('#contract-review-body-search').addEventListener('click', wrapped(() => searchVault(true)));
  modal.querySelector('#contract-review-parse').addEventListener('click', wrapped(parseDocument));
  modal.querySelector('#contract-review-law-search').addEventListener('click', wrapped(searchLaw));
  modal.querySelector('#contract-review-cancel').addEventListener('click', wrapped(cancelJob));
  modal.querySelector('#contract-review-save').addEventListener('click', wrapped(saveReport));
  modal.querySelector('#contract-review-use').addEventListener('click', () => {
    saveState({ ...loadState(), active: true, selected_paths: selectedPaths() });
    closeContractReview();
    uiModule.showToast?.('Contract Review evidence is active for Chat.');
  });
  modal.querySelector('#contract-review-deactivate').addEventListener('click', () => {
    saveState({ ...loadState(), active: false });
    closeContractReview();
  });
  const content = modal.querySelector('.modal-content');
  const header = modal.querySelector('.modal-header');
  if (content && header) makeWindowDraggable(modal, { content, header });
  return modal;
}

export function getContractReviewChatContext() {
  const state = loadState();
  if (!state.active || !state.snapshot_id || !state.vault_id) return null;
  return buildContractReviewChatContext(state);
}

export async function openContractReview() {
  const view = getModal();
  view.querySelector('#contract-review-vault-path').value = loadState().vault_path || '.';
  syncWorkspaceReadout();
  renderNotes(visibleNotes.length ? visibleNotes : indexedNotes);
  view.style.display = 'flex';
  try { await loadProfile(); }
  catch (error) { setStatus(`${error.code ? `${error.code}: ` : ''}${error.message}`, 'error'); }
}

export function closeContractReview() {
  if (modal) modal.style.display = 'none';
}

export function initContractReview(apiBase = '') {
  API_BASE = apiBase;
  syncIndicator();
  document.getElementById('overflow-contract-review-btn')?.addEventListener('click', openContractReview);
}

export default { initContractReview, openContractReview, closeContractReview, getContractReviewChatContext };
