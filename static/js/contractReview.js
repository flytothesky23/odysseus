import Storage, { KEYS } from './storage.js';
import uiModule from './ui.js';
import workspaceModule from './workspace.js';
import sessionModule from './sessions.js';
import { makeWindowDraggable } from './windowDrag.js';
import {
  buildContractReviewChatContext,
  buildVaultSearchRequest,
  reconcileMcpRuntimeState,
  sanitizePersistedState,
  updateSelectedPathSelection,
} from './contractReviewState.js';
import { isPathIncludedByScope } from './contractReviewExplorerState.js';

let API_BASE = '';
let modal = null;
let indexedNotes = [];
let visibleNotes = [];
let activeJobId = null;

function loadState() {
  return sanitizePersistedState(Storage.getJSON(KEYS.CONTRACT_REVIEW, {}));
}

function saveState(next) {
  const safe = sanitizePersistedState(next);
  Storage.setJSON(KEYS.CONTRACT_REVIEW, safe);
  syncIndicator(safe);
  document.dispatchEvent(new CustomEvent('contract-review-state-change', { detail: safe }));
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

function clearProfileServers() {
  renderServerOptions(modal?.querySelector('#contract-review-kordoc-server'), [], 'Kordoc unavailable');
  renderServerOptions(modal?.querySelector('#contract-review-law-server'), [], 'Korean Law unavailable');
}

async function loadProfile() {
  clearProfileServers();
  const profile = await refreshMcpRuntime();
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
  if (!profile.inventory_available) setStatus('MCP inventory를 읽을 수 없습니다.', 'error');
  else if (loadState().mcp_runtime_stale) {
    setStatus('앱 재기동으로 이전 MCP 근거가 만료되었습니다. Kordoc·법률 조회를 다시 실행하세요.', 'warning');
  }
}

async function refreshMcpRuntime() {
  try {
    const profile = await api('/profile');
    const previous = loadState();
    const reconciled = reconcileMcpRuntimeState(previous, profile.mcp_runtime_id);
    if (JSON.stringify(reconciled) !== JSON.stringify(previous)) saveState(reconciled);
    return profile;
  } catch (error) {
    const previous = loadState();
    if (previous.kordoc_job_ids.length || previous.law_job_ids.length) {
      saveState(reconcileMcpRuntimeState(previous, ''));
    }
    throw error;
  }
}

function selectedPaths() {
  return loadState().selected_paths;
}

function renderNotes(items) {
  const list = modal?.querySelector('#contract-review-results');
  if (!list) return;
  const state = loadState();
  const chosen = new Set(state.selected_paths);
  const scopedItems = items.filter(note => isPathIncludedByScope(note.path, state.note_scope));
  if (!scopedItems.length) {
    list.innerHTML = '<div class="workspace-empty">일치하는 Markdown 노트가 없습니다.</div>';
    return;
  }
  list.innerHTML = scopedItems.map(note => {
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
      active: false,
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
  const previous = loadState();
  const noteScope = previous.vault_id === indexed.vault_id
    ? previous.note_scope
    : { default_included: true, rules: [] };
  saveState({
    active: false, snapshot_id: indexed.snapshot_id, vault_id: indexed.vault_id,
    vault_path: vaultPath, note_scope: noteScope, selected_paths: [],
    kordoc_job_ids: previous.kordoc_job_ids, law_job_ids: previous.law_job_ids,
    mcp_runtime_id: previous.mcp_runtime_id,
    mcp_runtime_stale: previous.mcp_runtime_stale,
  });
  document.dispatchEvent(new CustomEvent('contract-review-vault-indexed', {
    detail: { notes: indexedNotes, snapshot_id: indexed.snapshot_id, vault_id: indexed.vault_id },
  }));
  renderNotes(visibleNotes);
  setStatus(`${indexed.note_count}개 노트 metadata 인덱싱 완료 · 본문 읽기 0회`, 'ok');
}

async function searchVault(includeBody) {
  const state = loadState();
  const query = modal.querySelector('#contract-review-query').value.trim();
  if (!state.snapshot_id) throw new Error('먼저 Vault metadata를 인덱싱하세요.');
  if (!query) throw new Error('검색어를 입력하세요.');
  const candidates = includeBody
    ? visibleNotes
      .filter(note => isPathIncludedByScope(note.path, state.note_scope))
      .map(note => note.path)
      .slice(0, 20)
    : [];
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
  modal.querySelector('#contract-review-parser-output').textContent = '';
  const started = await api('/kordoc/jobs', { method: 'POST', body: JSON.stringify({
    server_id: serverId,
    tool: modal.querySelector('#contract-review-kordoc-tool').value,
    workspace, file_path: filePath, arguments: {},
  }) });
  const completed = await pollJob(started);
  if (completed.state !== 'completed') return;
  const output = String(completed.result?.output || '');
  modal.querySelector('#contract-review-parser-output').textContent = output.slice(0, 12000);
  saveState({
    ...loadState(),
    kordoc_job_ids: [...loadState().kordoc_job_ids, completed.id],
    mcp_runtime_id: completed.mcp_runtime_id,
    mcp_runtime_stale: false,
  });
  setStatus('Kordoc read-only parsing 완료.', 'ok');
}

async function searchLaw() {
  const query = modal.querySelector('#contract-review-law-query').value.trim();
  const serverId = modal.querySelector('#contract-review-law-server').value;
  const tool = modal.querySelector('#contract-review-law-tool').value;
  if (!query) throw new Error('법령 검색어를 입력하세요.');
  if (!serverId) throw new Error('연결된 Korean Law MCP가 없습니다. Settings에서 먼저 연결하세요.');
  modal.querySelector('#contract-review-law-output').textContent = '';
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
  saveState({
    ...loadState(),
    law_job_ids: [...loadState().law_job_ids, completed.id],
    mcp_runtime_id: completed.mcp_runtime_id,
    mcp_runtime_stale: false,
  });
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
    <div class="modal-header"><h4>Contract Review Workspace</h4><button class="close-btn" id="contract-review-close" aria-label="닫기">✖</button></div>
    <div class="modal-body contract-review-body">
      <p class="muted">읽기 전용 · 상대경로와 식별자만 저장 · metadata 우선, 선택 후보 본문만 제한적으로 조회</p>
      <details class="contract-review-help" open>
        <summary>처음 사용하는 경우 · 단계별 사용 방법</summary>
        <ol>
          <li><strong>Vault 연결:</strong> .obsidian 폴더가 들어 있는 Vault 최상위 폴더를 선택하세요. 상위 Workspace를 선택했다면 아래에 Vault 상대경로를 입력합니다.</li>
          <li><strong>Metadata 색인:</strong> 제목·파일명·상대경로·aliases만 먼저 읽습니다. 이 단계에서는 노트 본문을 LLM에 보내지 않습니다.</li>
          <li><strong>후보 선택:</strong> Metadata 검색 결과를 체크한 뒤 필요한 후보의 본문만 제한적으로 조회하세요.</li>
          <li><strong>로컬 문서:</strong> Workspace 안의 PDF·Office·HWP 상대경로를 입력해 Kordoc으로 파싱합니다. 절대경로는 거부됩니다.</li>
          <li><strong>법률 근거:</strong> Korean Law로 찾은 후보는 정확한 법령명·MST를 식별한 뒤 공식 원문으로 다시 확인합니다.</li>
          <li><strong>채팅:</strong> 아래의 ‘선택 근거로 채팅’을 누른 뒤 질문하세요. 파일이 바뀌면 다시 색인해야 합니다.</li>
          <li><strong>저장:</strong> 보고서는 채팅 결과가 검증된 뒤 사용자가 ‘검증 결과를 Documents에 저장’을 눌렀을 때만 명시적으로 저장됩니다.</li>
        </ol>
      </details>
      <section class="contract-review-section"><h5>1. Obsidian Vault 근거</h5>
        <div class="contract-review-row"><button class="confirm-btn" id="contract-review-workspace-select">Vault/Workspace 폴더 선택</button><span id="contract-review-workspace" class="muted contract-review-workspace-readout">선택되지 않음</span></div>
        <div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-vault-path" value="." aria-label="Workspace 기준 Vault 상대경로" placeholder="Workspace 기준 Vault 상대경로 (Vault 자체면 .)"><button class="confirm-btn confirm-btn-primary" id="contract-review-index">Metadata 색인</button></div>
        <div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-query" placeholder="제목, 파일명, 상대경로, aliases"><button class="confirm-btn" id="contract-review-search">Metadata 검색</button><button class="confirm-btn" id="contract-review-body-search">후보 본문 제한 조회</button></div>
        <div id="contract-review-results" class="contract-review-results"></div>
      </section>
      <section class="contract-review-section"><h5>2. 로컬 문서 근거 · Kordoc MCP</h5>
        <div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-document-path" aria-label="Workspace 기준 로컬 문서 상대경로" placeholder="예: documents/contract.pdf"><select class="contract-review-server" id="contract-review-kordoc-server" aria-label="Kordoc 서버"><option value="">Kordoc 불러오는 중…</option></select><select id="contract-review-kordoc-tool" aria-label="Kordoc 읽기 전용 도구"><option>parse_document</option><option>detect_format</option><option>parse_metadata</option><option>parse_pages</option><option>parse_table</option><option>parse_chunks</option><option>parse_form</option></select><button class="confirm-btn" id="contract-review-parse">문서 파싱</button></div>
        <pre id="contract-review-parser-output" class="contract-review-output"></pre>
      </section>
      <section class="contract-review-section"><h5>3. 공식 법률 근거 · Korean Law MCP</h5>
        <div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-law-query" placeholder="법령명 또는 판례 검색어"><select class="contract-review-server" id="contract-review-law-server" aria-label="Korean Law 서버"><option value="">Korean Law 불러오는 중…</option></select><select id="contract-review-law-tool" aria-label="Korean Law 조회 도구"><option>search_law</option><option>search_decisions</option></select><button class="confirm-btn" id="contract-review-law-search">공식 근거 조회</button></div>
        <pre id="contract-review-law-output" class="contract-review-output"></pre>
      </section>
      <section class="contract-review-section"><h5>4. 명시적 보고서 저장</h5><div class="contract-review-row"><input class="styled-prompt-input" id="contract-review-report-title" aria-label="저장할 보고서 제목" value="Contract Review"><button class="confirm-btn" id="contract-review-save">검증 결과를 Documents에 저장</button></div></section>
      <p id="contract-review-status" class="contract-review-status" aria-live="polite"></p>
    </div>
    <div class="modal-footer"><button class="confirm-btn confirm-btn-secondary" id="contract-review-cancel" disabled>진행 중 작업 취소</button><button class="confirm-btn confirm-btn-secondary" id="contract-review-deactivate">근거 연결 해제</button><button class="confirm-btn confirm-btn-primary" id="contract-review-use">선택 근거로 채팅</button></div>
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
    const state = loadState();
    if (!state.selected_paths.length && !state.kordoc_job_ids.length && !state.law_job_ids.length) {
      setStatus('채팅에 연결할 Vault 본문 후보 또는 완료된 MCP 근거가 없습니다.', 'warning');
      return;
    }
    saveState({ ...state, active: true, selected_paths: selectedPaths() });
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
  const hasEvidence = state.selected_paths.length || state.kordoc_job_ids.length || state.law_job_ids.length;
  if (!state.active || !state.snapshot_id || !state.vault_id || !hasEvidence) return null;
  return buildContractReviewChatContext(state);
}

export async function openContractReview() {
  const view = getModal();
  view.querySelector('#contract-review-vault-path').value = loadState().vault_path || '.';
  syncWorkspaceReadout();
  renderNotes(visibleNotes.length ? visibleNotes : indexedNotes);
  view.style.display = 'flex';
  try { await loadProfile(); }
  catch (error) { clearProfileServers(); setStatus(`${error.code ? `${error.code}: ` : ''}${error.message}`, 'error'); }
}

export function closeContractReview() {
  if (modal) modal.style.display = 'none';
}

export function initContractReview(apiBase = '') {
  API_BASE = apiBase;
  syncIndicator();
  refreshMcpRuntime().catch(() => {});
  document.addEventListener('contract-review-state-change', event => {
    syncIndicator(event.detail);
  });
  document.getElementById('overflow-contract-review-btn')?.addEventListener('click', openContractReview);
  document.addEventListener('contract-review-vault-indexed', event => {
    indexedNotes = Array.isArray(event.detail?.notes) ? event.detail.notes : indexedNotes;
    visibleNotes = indexedNotes;
    if (modal) renderNotes(visibleNotes);
  });
}

export default { initContractReview, openContractReview, closeContractReview, getContractReviewChatContext };
