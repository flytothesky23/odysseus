import Storage, { KEYS } from './storage.js';
import uiModule from './ui.js';
import workspaceModule from './workspace.js';
import contractReviewModule from './contractReview.js';
import * as Modals from './modalManager.js';
import { makeWindowDraggable } from './windowDrag.js';
import { applyEdgeDock, clearDockSide } from './modalSnap.js';
import { topToolWindowZ } from './toolWindowZOrder.js';
import { sanitizePersistedState } from './contractReviewState.js';
import {
  buildVaultTree,
  descendantNotePaths,
  filterVaultNotes,
  folderSelectionState,
  isPathIncludedByScope,
  reconcileSelectedPaths,
  updateBoundedSelection,
  updateScopeSelection,
} from './contractReviewExplorerState.js';

const PANEL_ID = 'vault-explorer-panel';
const MAX_CHAT_EVIDENCE = 8;
const FOLDER_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
const NOTE_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>';
const CHEVRON_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>';

let API_BASE = '';
let open = false;
let indexedNotes = [];
let expandedFolders = new Set();
let pane = null;
let keyHandler = null;
let indexPhase = 'idle';
let indexError = '';

function loadState() {
  return sanitizePersistedState(Storage.getJSON(KEYS.CONTRACT_REVIEW, {}));
}

function saveState(next) {
  const safe = sanitizePersistedState(next);
  Storage.setJSON(KEYS.CONTRACT_REVIEW, safe);
  document.dispatchEvent(new CustomEvent('contract-review-state-change', { detail: safe }));
  try { document.dispatchEvent(new CustomEvent('overflow-state-change')); } catch (_) {}
  return safe;
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

function workspaceLabel() {
  const workspace = workspaceModule.getWorkspace();
  if (!workspace) return 'Workspace 미선택';
  return workspace.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || 'Workspace';
}

function setStatus(message, tone = '') {
  const target = pane?.querySelector('#vault-explorer-status');
  if (!target) return;
  target.textContent = message;
  target.dataset.tone = tone;
}

function bringToFront() {
  const backdrop = document.getElementById('vault-explorer-backdrop');
  if (!backdrop) return;
  backdrop.style.setProperty('z-index', String(topToolWindowZ({ exclude: backdrop }) + 1), 'important');
}

function clearDock(paneElement) {
  if (!paneElement) return;
  const right = paneElement.classList.contains('modal-right-docked');
  const left = paneElement.classList.contains('modal-left-docked');
  if (right) clearDockSide('right', paneElement);
  if (left) clearDockSide('left', paneElement);
  paneElement.classList.remove('modal-right-docked', 'modal-left-docked');
}

function selectedPaths() {
  return loadState().selected_paths;
}

function noteScope() {
  return loadState().note_scope;
}

function scopedPaths(notes = indexedNotes) {
  const scope = noteScope();
  return (Array.isArray(notes) ? notes : [])
    .filter(note => isPathIncludedByScope(note.path, scope))
    .map(note => note.path);
}

function selectedSummary(total = indexedNotes.length) {
  const inScope = indexPhase === 'ready' ? scopedPaths().length : 0;
  const evidence = indexPhase === 'ready' ? selectedPaths().length : 0;
  if (indexPhase === 'indexing') return 'Vault metadata 확인 중… 본문은 읽지 않습니다.';
  return `${total.toLocaleString('ko-KR')}개 MD 색인 · ${inScope.toLocaleString('ko-KR')}/${total.toLocaleString('ko-KR')}개 분석 범위 · ${evidence}/${MAX_CHAT_EVIDENCE}개 본문 후보`;
}

function renderFolder(folder, level, searching) {
  const paths = descendantNotePaths(folder);
  const selection = folderSelectionState(paths, scopedPaths());
  const isExpanded = searching || expandedFolders.has(folder.path);
  const children = isExpanded
    ? `<ul>${folder.folders.map(child => renderFolder(child, level + 1, searching)).join('')}${folder.notes.map(note => renderNote(note, level + 1)).join('')}</ul>`
    : '';
  return `<li class="vault-explorer-folder" role="none">
    <div class="vault-explorer-folder-row" role="treeitem" aria-level="${level}" aria-expanded="${isExpanded}" data-scope-state="${selection.state}" style="--tree-level:${level}">
      <button type="button" class="vault-explorer-folder-toggle" data-folder-toggle="${uiModule.esc(folder.path)}" aria-label="${uiModule.esc(folder.name)} 폴더 ${isExpanded ? '접기' : '펼치기'}">
        <span class="vault-explorer-guide" aria-hidden="true"></span>
        <span class="vault-explorer-caret ${isExpanded ? 'is-expanded' : ''}">${CHEVRON_ICON}</span>
        <span class="vault-explorer-folder-name">${uiModule.esc(folder.name)}</span>
        <small>${selection.selected}/${selection.total}</small>
      </button>
      <input type="checkbox" data-folder-select="${uiModule.esc(folder.path)}" aria-label="${uiModule.esc(folder.name)} 폴더 분석 범위 선택" ${selection.state === 'checked' ? 'checked' : ''}>
    </div>${children}</li>`;
}

function renderNote(note, level) {
  const included = isPathIncludedByScope(note.path, noteScope());
  const evidence = selectedPaths().includes(note.path);
  const aliases = Array.isArray(note.aliases) && note.aliases.length ? ` · ${note.aliases.join(', ')}` : '';
  return `<li role="none">
    <label class="vault-explorer-note-row" role="treeitem" aria-level="${level}" data-included="${included}" data-evidence="${evidence}" style="--tree-level:${level}" title="${uiModule.esc(`${note.path}${aliases}`)}">
      <span class="vault-explorer-guide" aria-hidden="true"></span>
      <input type="checkbox" data-note-select="${uiModule.esc(note.path)}" aria-label="${uiModule.esc(note.title || note.filename || note.path)} 분석 범위 선택" ${included ? 'checked' : ''}>
      <span class="vault-explorer-note-icon">${NOTE_ICON}</span>
      <span class="vault-explorer-note-copy"><strong>${uiModule.esc(note.title || note.stem || note.path)}</strong><small>${uiModule.esc(note.path)}</small></span>
      ${evidence ? '<span class="vault-explorer-evidence-marker">본문 후보</span>' : ''}
    </label>
  </li>`;
}

function renderTree() {
  if (!pane) return;
  const input = pane.querySelector('#vault-explorer-search');
  const query = input?.value || '';
  const notes = filterVaultNotes(indexedNotes, query);
  const tree = buildVaultTree(notes);
  const treeHost = pane.querySelector('#vault-explorer-tree');
  const meta = pane.querySelector('#vault-explorer-meta');
  meta.textContent = selectedSummary(indexedNotes.length);
  if (notes.length) {
    treeHost.innerHTML = `<ul role="tree" aria-label="Obsidian Vault 노트">${tree.folders.map(folder => renderFolder(folder, 1, Boolean(query.trim()))).join('')}${tree.notes.map(note => renderNote(note, 1)).join('')}</ul>`;
  } else if (indexPhase === 'indexing') {
    treeHost.innerHTML = '<div class="vault-explorer-empty"><span class="vault-explorer-empty-spinner" aria-hidden="true"></span><strong>Vault metadata를 색인하는 중입니다.</strong><span>노트 본문은 읽지 않습니다.</span></div>';
  } else if (indexedNotes.length) {
    treeHost.innerHTML = '<div class="vault-explorer-empty"><strong>검색 결과가 없습니다.</strong><span>제목·파일명·상대경로·aliases에서 일치하는 metadata를 찾지 못했습니다.</span></div>';
  } else {
    const message = indexError || 'Obsidian Vault 루트 폴더를 고르면 metadata를 색인하고 폴더 트리를 만듭니다.';
    treeHost.innerHTML = `<div class="vault-explorer-empty"><strong>${indexError ? 'Vault를 연결하지 못했습니다.' : '먼저 Vault를 연결하세요.'}</strong><span>${uiModule.esc(message)}</span><button type="button" id="vault-explorer-empty-select">Vault 폴더 선택</button></div>`;
  }
  treeHost.querySelectorAll('[data-folder-select]').forEach(inputEl => {
    const folder = findFolder(tree, inputEl.dataset.folderSelect);
    const selection = folderSelectionState(descendantNotePaths(folder), scopedPaths());
    inputEl.indeterminate = selection.state === 'mixed';
  });
  const useButton = pane.querySelector('#vault-explorer-use-chat');
  if (useButton) useButton.disabled = indexPhase !== 'ready' || selectedPaths().length === 0;
  const selectVisible = pane.querySelector('#vault-explorer-select-visible');
  if (selectVisible) {
    const inScopeVisible = notes.filter(note => isPathIncludedByScope(note.path, noteScope()));
    selectVisible.disabled = indexPhase !== 'ready' || !query.trim() || inScopeVisible.length === 0;
  }
  pane.querySelectorAll('#vault-explorer-include-all, #vault-explorer-exclude-all')
    .forEach(button => { button.disabled = indexPhase !== 'ready' || indexedNotes.length === 0; });
  const clearEvidence = pane.querySelector('#vault-explorer-clear-evidence');
  if (clearEvidence) clearEvidence.disabled = selectedPaths().length === 0;
}

function findFolder(folder, path) {
  if (!folder) return null;
  if (folder.path === path) return folder;
  for (const child of folder.folders || []) {
    const match = findFolder(child, path);
    if (match) return match;
  }
  return null;
}

function currentTree() {
  const query = pane?.querySelector('#vault-explorer-search')?.value || '';
  return buildVaultTree(filterVaultNotes(indexedNotes, query));
}

function applyEvidenceSelection(paths) {
  const state = loadState();
  const included = paths.filter(path => isPathIncludedByScope(path, state.note_scope));
  const result = updateBoundedSelection([], included, true, MAX_CHAT_EVIDENCE);
  saveState({ ...state, active: false, selected_paths: result.selected_paths });
  renderTree();
  if (result.rejected_count) {
    setStatus(`검색 결과 중 앞의 ${MAX_CHAT_EVIDENCE}개만 본문 후보로 지정했습니다. 검색어를 더 좁히면 다른 후보를 선택할 수 있습니다.`, 'warning');
  } else {
    setStatus(`${result.selected_paths.length}/${MAX_CHAT_EVIDENCE}개 노트를 제한된 본문 후보로 지정했습니다.`, 'ok');
  }
}

function applyScopeRule(path, included) {
  const state = loadState();
  const nextScope = updateScopeSelection(state.note_scope, path, included);
  const nextSelection = state.selected_paths.filter(candidate => isPathIncludedByScope(candidate, nextScope));
  saveState({ ...state, active: false, note_scope: nextScope, selected_paths: nextSelection });
  renderTree();
  setStatus(`${scopedPaths().length.toLocaleString('ko-KR')}개 노트를 분석 범위에 포함했습니다. 본문은 아직 읽지 않았습니다.`, 'ok');
}

function applyWholeVaultScope(included) {
  const state = loadState();
  const nextScope = { default_included: included, rules: [] };
  saveState({
    ...state,
    active: false,
    note_scope: nextScope,
    selected_paths: included ? state.selected_paths : [],
  });
  renderTree();
  setStatus(included
    ? '전체 Vault를 metadata 분석 범위로 선택했습니다. 본문은 아직 읽지 않았습니다.'
    : '전체 Vault를 분석 범위에서 제외했습니다.', included ? 'ok' : '');
}

function friendlyIndexError(error) {
  if (error?.code === 'invalid_vault') {
    return '선택한 폴더에서 .obsidian을 찾지 못했습니다. Obsidian Vault의 최상위 폴더를 선택하세요.';
  }
  if (error?.code === 'invalid_workspace') {
    return '선택한 폴더를 사용할 수 없습니다. Vault 폴더를 다시 선택하세요.';
  }
  return `${error?.code ? `${error.code}: ` : ''}${error?.message || 'Vault metadata 색인에 실패했습니다.'}`;
}

function handleIndexError(error) {
  indexPhase = 'error';
  indexError = friendlyIndexError(error);
  indexedNotes = [];
  const state = loadState();
  saveState({ ...state, active: false, snapshot_id: '', vault_id: '', selected_paths: [] });
  renderTree();
  setStatus(indexError, 'error');
}

async function indexVault({ preserveSelection = false } = {}) {
  const workspace = workspaceModule.getWorkspace();
  if (!workspace) throw new Error('먼저 Obsidian Vault 폴더를 선택하세요.');
  const vaultPath = pane.querySelector('#vault-explorer-vault-path').value.trim() || '.';
  const previousState = loadState();
  indexPhase = 'indexing';
  indexError = '';
  setStatus('Vault metadata를 색인하는 중… 본문은 읽지 않습니다.');
  renderTree();
  const result = await api('/vault/index', {
    method: 'POST',
    body: JSON.stringify({ workspace, vault_path: vaultPath }),
  });
  indexedNotes = Array.isArray(result.notes) ? result.notes : [];
  indexPhase = 'ready';
  expandedFolders = new Set(buildVaultTree(indexedNotes).folders.map(folder => folder.path));
  const sameVault = preserveSelection && previousState.vault_id === result.vault_id;
  const nextScope = sameVault
    ? previousState.note_scope
    : { default_included: true, rules: [] };
  const nextSelection = reconcileSelectedPaths(
    sameVault ? previousState.selected_paths : [], indexedNotes, MAX_CHAT_EVIDENCE,
  ).filter(path => isPathIncludedByScope(path, nextScope));
  saveState({
    active: false,
    snapshot_id: result.snapshot_id,
    vault_id: result.vault_id,
    vault_path: vaultPath,
    note_scope: nextScope,
    selected_paths: nextSelection,
    kordoc_job_ids: previousState.kordoc_job_ids,
    law_job_ids: previousState.law_job_ids,
  });
  document.dispatchEvent(new CustomEvent('contract-review-vault-indexed', {
    detail: { notes: indexedNotes, snapshot_id: result.snapshot_id, vault_id: result.vault_id },
  }));
  syncRootReadout();
  renderTree();
  const preserved = nextSelection.length ? ` · 기존 본문 후보 ${nextSelection.length}개 재확인` : '';
  setStatus(`${result.note_count}개 metadata 색인 완료 · Vault 본문 읽기 0회${preserved}`, 'ok');
}

function syncRootReadout() {
  if (!pane) return;
  const label = pane.querySelector('#vault-explorer-workspace-label');
  if (label) label.textContent = workspaceLabel();
}

function ensureChipRegistered() {
  if (Modals.isRegistered(PANEL_ID)) return;
  Modals.register(PANEL_ID, {
    railBtnId: 'rail-vault-explorer',
    sidebarBtnId: 'tool-vault-explorer-btn',
    restoreFn: () => openPanel(),
    closeFn: () => forceClose(),
  });
}

function forceClose() {
  open = false;
  clearDock(pane);
  pane?.remove();
  document.getElementById('vault-explorer-backdrop')?.remove();
  pane = null;
  document.body.classList.remove('vault-explorer-view');
  document.getElementById('tool-vault-explorer-btn')?.classList.remove('active');
  if (keyHandler) document.removeEventListener('keydown', keyHandler);
  keyHandler = null;
  try { Modals.unregister(PANEL_ID); } catch (_) {}
}

function wirePanel() {
  pane.querySelector('#vault-explorer-close').addEventListener('click', () => closePanel());
  pane.querySelector('#vault-explorer-minimize').addEventListener('click', () => closePanel('minimize'));
  pane.querySelector('#vault-explorer-refresh').addEventListener('click', () => indexVault({ preserveSelection: true }).catch(handleIndexError));
  pane.querySelector('#vault-explorer-root-select').addEventListener('click', async () => {
    await workspaceModule.openWorkspaceBrowser({
      title: 'Obsidian Vault 폴더 선택',
      useLabel: '이 폴더를 Vault로 사용',
      note: 'Obsidian의 <strong>.obsidian</strong> 폴더가 들어 있는 Vault 최상위 폴더를 선택하세요. 선택 후 본문이 아니라 metadata만 먼저 색인합니다.',
      onSelect: () => {
        pane.querySelector('#vault-explorer-vault-path').value = '.';
        syncRootReadout();
        indexVault({ preserveSelection: false }).catch(handleIndexError);
      },
    });
  });
  pane.querySelector('#vault-explorer-vault-path').addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    indexVault({ preserveSelection: true }).catch(handleIndexError);
  });
  pane.querySelector('#vault-explorer-search').addEventListener('input', renderTree);
  pane.querySelector('#vault-explorer-clear-search').addEventListener('click', () => {
    pane.querySelector('#vault-explorer-search').value = '';
    renderTree();
    pane.querySelector('#vault-explorer-search').focus();
  });
  pane.querySelector('#vault-explorer-select-visible').addEventListener('click', () => {
    const query = pane.querySelector('#vault-explorer-search').value.trim();
    if (!query) {
      setStatus('본문 후보를 정하려면 metadata 검색어를 먼저 입력하세요.', 'warning');
      return;
    }
    const paths = filterVaultNotes(indexedNotes, query).map(note => note.path);
    applyEvidenceSelection(paths);
  });
  pane.querySelector('#vault-explorer-include-all').addEventListener('click', () => applyWholeVaultScope(true));
  pane.querySelector('#vault-explorer-exclude-all').addEventListener('click', () => applyWholeVaultScope(false));
  pane.querySelector('#vault-explorer-clear-evidence').addEventListener('click', () => {
    const state = loadState();
    saveState({ ...state, active: false, selected_paths: [] });
    renderTree();
    setStatus('제한된 본문 후보를 모두 지웠습니다.');
  });
  pane.querySelector('#vault-explorer-use-chat').addEventListener('click', () => {
    const state = loadState();
    if (!state.selected_paths.length) return;
    saveState({ ...state, active: true });
    closePanel();
    uiModule.showToast?.(`${state.selected_paths.length}개 Vault 근거를 현재 채팅에 연결했습니다.`);
  });
  pane.querySelector('#vault-explorer-open-workspace').addEventListener('click', () => {
    closePanel();
    contractReviewModule.openContractReview();
  });
  pane.querySelector('#vault-explorer-tree').addEventListener('click', event => {
    if (event.target.closest('#vault-explorer-empty-select')) {
      pane.querySelector('#vault-explorer-root-select').click();
      return;
    }
    const folderToggle = event.target.closest('[data-folder-toggle]');
    if (folderToggle) {
      const path = folderToggle.dataset.folderToggle;
      if (expandedFolders.has(path)) expandedFolders.delete(path);
      else expandedFolders.add(path);
      renderTree();
    }
  });
  pane.querySelector('#vault-explorer-tree').addEventListener('change', event => {
    const noteInput = event.target.closest('[data-note-select]');
    if (noteInput) {
      applyScopeRule(noteInput.dataset.noteSelect, noteInput.checked);
      return;
    }
    const folderInput = event.target.closest('[data-folder-select]');
    if (folderInput) {
      const folder = findFolder(currentTree(), folderInput.dataset.folderSelect);
      if (folder) applyScopeRule(folder.path, folderInput.checked);
    }
  });
  pane.addEventListener('pointerdown', bringToFront, true);
  pane.addEventListener('focusin', bringToFront, true);
  keyHandler = event => {
    if (event.key === 'Escape' && open) closePanel();
  };
  document.addEventListener('keydown', keyHandler);
}

export function openPanel() {
  if (open) {
    bringToFront();
    return;
  }
  open = true;
  document.body.classList.add('vault-explorer-view');
  document.getElementById('tool-vault-explorer-btn')?.classList.add('active');

  const state = loadState();
  pane = document.createElement('aside');
  pane.id = 'vault-explorer-pane';
  pane.className = 'notes-pane vault-explorer-pane';
  pane.setAttribute('aria-label', 'Obsidian Vault Explorer');
  pane.innerHTML = `
    <div class="notes-mobile-grabber" aria-hidden="true"></div>
    <div class="notes-pane-header vault-explorer-header">
      <h4 class="notes-pane-title">${FOLDER_ICON}<span>Vault Explorer</span></h4>
      <span class="vault-explorer-readonly">metadata first</span>
      <button id="vault-explorer-minimize" class="modal-minimize-btn" title="Minimize" aria-label="Vault Explorer 최소화"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" aria-hidden="true"><path d="M6 18h12"/></svg></button>
      <button id="vault-explorer-close" class="doc-action-icon-btn" title="Close" aria-label="Vault Explorer 닫기"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
    </div>
    <div class="vault-explorer-rootbar">
      <button type="button" id="vault-explorer-root-select" class="vault-explorer-root-btn">${FOLDER_ICON}<span class="vault-explorer-root-copy"><strong>Vault 폴더 선택</strong><small id="vault-explorer-workspace-label">${uiModule.esc(workspaceLabel())}</small></span></button>
      <button type="button" id="vault-explorer-refresh" class="vault-explorer-index-btn" title="Vault metadata 다시 색인"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 11a8 8 0 1 0 2 5.3"/><path d="M20 4v7h-7"/></svg><span>Metadata 색인</span></button>
    </div>
    <details class="vault-explorer-advanced">
      <summary>상위 Workspace 안의 Vault 사용</summary>
      <label for="vault-explorer-vault-path">Vault 상대경로</label>
      <input id="vault-explorer-vault-path" value="${uiModule.esc(state.vault_path || '.')}" aria-label="Workspace 상대 Vault 경로" placeholder="예: Notes/MyVault (Vault 자체를 골랐다면 .)" spellcheck="false">
    </details>
    <div class="vault-explorer-searchbar">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="10" cy="10" r="7"/><path d="m21 21-4.4-4.4"/></svg>
      <input id="vault-explorer-search" placeholder="제목, 파일명, 경로, aliases 검색" autocomplete="off">
      <button id="vault-explorer-clear-search" type="button" aria-label="검색 지우기">×</button>
    </div>
    <div id="vault-explorer-meta" class="vault-explorer-meta">${uiModule.esc(selectedSummary())}</div>
    <div class="vault-explorer-scope-actions">
      <button type="button" id="vault-explorer-include-all">전체 범위</button>
      <button type="button" id="vault-explorer-exclude-all">전체 해제</button>
      <span>체크박스 = metadata 검색·분석 범위</span>
    </div>
    <div class="vault-explorer-scope-actions vault-explorer-evidence-actions">
      <button type="button" id="vault-explorer-select-visible">검색 결과를 본문 후보로</button>
      <button type="button" id="vault-explorer-clear-evidence">후보 지우기</button>
      <span>LLM에 읽힐 본문 후보는 최대 ${MAX_CHAT_EVIDENCE}개</span>
    </div>
    <div id="vault-explorer-tree" class="notes-pane-body vault-explorer-tree"></div>
    <p id="vault-explorer-status" class="vault-explorer-status" aria-live="polite">먼저 체크박스로 분석 범위를 정하고, 검색 결과를 제한된 본문 후보로 지정하세요.</p>
    <div class="notes-pane-footer vault-explorer-footer">
      <button type="button" id="vault-explorer-open-workspace" class="confirm-btn confirm-btn-secondary">MCP·법률 도구</button>
      <button type="button" id="vault-explorer-use-chat" class="confirm-btn confirm-btn-primary">현재 후보로 채팅</button>
    </div>`;

  const backdrop = document.createElement('div');
  backdrop.id = 'vault-explorer-backdrop';
  backdrop.className = 'notes-pane-backdrop vault-explorer-backdrop';
  backdrop.appendChild(pane);
  document.body.appendChild(backdrop);
  makeWindowDraggable(pane, {
    content: pane,
    header: pane.querySelector('.vault-explorer-header'),
    skipSelector: 'button, input, label, .notes-mobile-grabber',
    enableDock: true,
    enableLeftDock: true,
  });
  if (window.innerWidth > 768) applyEdgeDock(pane, 'right');
  bringToFront();
  wirePanel();
  renderTree();
  if (workspaceModule.getWorkspace() && state.snapshot_id && state.vault_id) {
    indexVault({ preserveSelection: true }).catch(handleIndexError);
  }
}

export function closePanel(mode = 'close') {
  if (!open) return;
  open = false;
  const minimize = mode === 'minimize';
  if (minimize) ensureChipRegistered();
  else if (Modals.isRegistered(PANEL_ID)) Modals.unregister(PANEL_ID);
  if (keyHandler) document.removeEventListener('keydown', keyHandler);
  keyHandler = null;
  document.body.classList.remove('vault-explorer-view');
  document.getElementById('tool-vault-explorer-btn')?.classList.remove('active');
  clearDock(pane);
  pane?.remove();
  document.getElementById('vault-explorer-backdrop')?.remove();
  pane = null;
  if (minimize) Modals.minimize(PANEL_ID);
}

export function togglePanel() {
  if (open) closePanel();
  else if (Modals.isRegistered(PANEL_ID) && Modals.isMinimized(PANEL_ID)) Modals.restore(PANEL_ID);
  else openPanel();
}

export function isPanelOpen() {
  return open;
}

export function initContractReviewExplorer(apiBase = '') {
  API_BASE = apiBase;
  document.addEventListener('contract-review-vault-indexed', event => {
    indexedNotes = Array.isArray(event.detail?.notes) ? event.detail.notes : indexedNotes;
    if (open) renderTree();
  });
  document.addEventListener('contract-review-state-change', () => {
    if (open) renderTree();
  });
}

export default {
  initContractReviewExplorer,
  openPanel,
  closePanel,
  togglePanel,
  isPanelOpen,
};
