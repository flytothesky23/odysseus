// Explicit, per-response save destinations.  Import-time code stays free of
// browser globals so the path/title rules remain directly unit-testable.

function _isSafeRelativePath(value) {
  if (typeof value !== 'string') return false;
  const path = value.trim().replace(/\\/g, '/');
  if (!path || path.startsWith('/') || /^[A-Za-z]:\//.test(path)) return false;
  return !path.split('/').some(part => !part || part === '.' || part === '..' || part.startsWith('.'));
}

export function recommendVaultFolder(selectedPaths) {
  const directories = (Array.isArray(selectedPaths) ? selectedPaths : [])
    .filter(_isSafeRelativePath)
    .map(path => path.replace(/\\/g, '/').split('/').slice(0, -1));
  if (!directories.length) return '.';
  const common = [...directories[0]];
  for (const parts of directories.slice(1)) {
    while (common.length && parts[common.length - 1] !== common[common.length - 1]) common.pop();
  }
  return common.join('/') || '.';
}

export function suggestSavedResultTitle(content) {
  const first = String(content || '')
    .split(/\r?\n/)
    .map(line => line.trim())
    .find(Boolean) || '';
  const cleaned = first
    .replace(/^#{1,6}\s+/, '')
    .replace(/^(?:[-*>]|\d+[.)])\s+/, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_`~]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return (cleaned || 'AI 응답').slice(0, 80);
}

async function _fetchJson(path, options) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.message || payload.detail?.message || payload.detail || `저장 실패 (${response.status})`);
    error.code = payload.error || payload.detail?.error || 'save_failed';
    throw error;
  }
  return payload;
}

function _currentSessionId() {
  return window.sessionModule?.getCurrentSessionId?.() || '';
}

async function _toast(message, duration = 3000) {
  try {
    const ui = await import('./ui.js');
    (ui.showToast || ui.default?.showToast)?.(message, duration);
  } catch (_) {}
}

function _closeOpenMenu() {
  const existing = document.querySelector('.msg-save-menu');
  if (existing?._dismiss) existing._dismiss();
  else existing?.remove();
}

function _positionMenu(menu, trigger) {
  menu.style.visibility = 'hidden';
  document.body.appendChild(menu);
  const triggerRect = trigger.getBoundingClientRect();
  const menuRect = menu.getBoundingClientRect();
  const above = triggerRect.top - menuRect.height - 6;
  menu.style.top = `${Math.max(8, above >= 8 ? above : triggerRect.bottom + 6)}px`;
  menu.style.left = `${Math.max(8, Math.min(triggerRect.left, window.innerWidth - menuRect.width - 8))}px`;
  menu.style.visibility = '';
}

function _makeDestination(label, description, disabled = false) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'msg-save-destination';
  button.disabled = disabled;
  const primary = document.createElement('strong');
  primary.textContent = label;
  const secondary = document.createElement('span');
  secondary.textContent = description;
  button.append(primary, secondary);
  return button;
}

async function _saveDocument(msgElement, title, markdown) {
  if (msgElement?._contractReviewResult?.schema_version === 'contract-review.v2') {
    const contractReview = await import('./contractReview.js');
    return contractReview.saveContractReviewReport(msgElement._contractReviewResult, title);
  }
  return _fetchJson('/api/document', {
    method: 'POST',
    body: JSON.stringify({
      session_id: _currentSessionId() || null,
      title,
      language: 'markdown',
      content: markdown,
    }),
  });
}

async function _saveMemo(title, content) {
  return _fetchJson('/api/notes', {
    method: 'POST',
    body: JSON.stringify({
      title,
      content,
      note_type: 'note',
      label: 'chat',
      source: 'chat',
      session_id: _currentSessionId() || null,
    }),
  });
}

async function _vaultContext() {
  try {
    const contractReview = await import('./contractReview.js');
    return contractReview.getVaultSaveContext?.() || null;
  } catch (_) {
    return null;
  }
}

export async function openMessageSaveMenu(msgElement, trigger, content) {
  const alreadyOpen = document.querySelector('.msg-save-menu')?._trigger === trigger;
  _closeOpenMenu();
  if (alreadyOpen) return;

  const markdown = String(content || '').trim();
  const title = suggestSavedResultTitle(markdown);
  const vault = await _vaultContext();
  if (!trigger.isConnected) return;

  const menu = document.createElement('div');
  menu.className = 'msg-save-menu';
  menu.setAttribute('role', 'dialog');
  menu.setAttribute('aria-label', 'AI 답변 저장');
  menu._trigger = trigger;
  trigger.setAttribute('aria-expanded', 'true');

  const heading = document.createElement('div');
  heading.className = 'msg-save-heading';
  heading.textContent = '이 답변 저장';
  const destinations = document.createElement('div');
  destinations.className = 'msg-save-destinations';
  const status = document.createElement('div');
  status.className = 'msg-save-status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  menu.append(heading, destinations, status);

  let disposed = false;
  let outsideHandler;
  let keyHandler;
  const dismiss = () => {
    if (disposed) return;
    disposed = true;
    document.removeEventListener('pointerdown', outsideHandler, true);
    document.removeEventListener('keydown', keyHandler, true);
    trigger.setAttribute('aria-expanded', 'false');
    menu.remove();
  };
  menu._dismiss = dismiss;
  outsideHandler = event => {
    if (!menu.contains(event.target) && event.target !== trigger) dismiss();
  };
  keyHandler = event => {
    if (event.key === 'Escape') dismiss();
  };

  function setStatus(message, kind = '') {
    status.textContent = message;
    status.dataset.kind = kind;
  }

  async function runSave(button, pendingLabel, save, successLabel) {
    const original = button.querySelector('strong')?.textContent || button.textContent;
    button.disabled = true;
    if (button.querySelector('strong')) button.querySelector('strong').textContent = pendingLabel;
    setStatus('');
    try {
      const saved = await save();
      if (button.querySelector('strong')) button.querySelector('strong').textContent = successLabel;
      setStatus(saved.path || saved.title || '저장되었습니다.', 'ok');
      return saved;
    } catch (error) {
      button.disabled = false;
      if (button.querySelector('strong')) button.querySelector('strong').textContent = original;
      setStatus(error?.message || '저장하지 못했습니다.', 'error');
      throw error;
    }
  }

  const documentButton = _makeDestination(
    msgElement.dataset.savedDocumentId ? 'Documents에 저장됨' : 'Documents에 저장',
    '현재 채팅과 연결된 편집 가능한 보고서',
    Boolean(msgElement.dataset.savedDocumentId),
  );
  documentButton.addEventListener('click', async event => {
    event.stopPropagation();
    try {
      const saved = await runSave(documentButton, 'Documents 저장 중…', () => _saveDocument(msgElement, title, markdown), 'Documents에 저장됨');
      msgElement.dataset.savedDocumentId = String(saved.id || 'saved');
      const reportShortcut = msgElement.querySelector('[data-contract-review-save]');
      if (reportShortcut) {
        reportShortcut.disabled = true;
        reportShortcut.textContent = 'Documents에 저장됨';
        reportShortcut.dataset.savedDocumentId = String(saved.id || 'saved');
      }
      await _toast(`Documents에 저장했습니다: ${saved.title || title}`);
    } catch (_) {}
  });

  const memoButton = _makeDestination(
    msgElement.dataset.savedMemoId ? '메모에 저장됨' : '메모에 저장',
    '우측 메모 패널에서 다시 찾고 근거로 고정',
    Boolean(msgElement.dataset.savedMemoId),
  );
  memoButton.addEventListener('click', async event => {
    event.stopPropagation();
    try {
      const saved = await runSave(memoButton, '메모 저장 중…', () => _saveMemo(title, markdown), '메모에 저장됨');
      msgElement.dataset.savedMemoId = String(saved.id || 'saved');
      document.dispatchEvent(new CustomEvent('notes-changed'));
      await _toast(`메모에 저장했습니다: ${saved.title || title}`);
    } catch (_) {}
  });

  const vaultButton = _makeDestination(
    msgElement.dataset.savedVaultPath ? 'Obsidian MD로 저장됨' : 'Obsidian MD로 저장',
    vault ? `기존 폴더 추천 · ${recommendVaultFolder(vault.selected_paths)}` : 'Vault Explorer에서 먼저 근거 노트를 선택하세요',
    Boolean(msgElement.dataset.savedVaultPath) || !vault,
  );

  function renderVaultForm() {
    destinations.replaceChildren();
    heading.textContent = 'Obsidian MD로 저장';
    const form = document.createElement('form');
    form.className = 'msg-save-vault-form';
    const folderLabel = document.createElement('label');
    folderLabel.textContent = '기존 Vault 폴더';
    const folderInput = document.createElement('input');
    folderInput.name = 'folder';
    folderInput.value = recommendVaultFolder(vault.selected_paths);
    folderInput.placeholder = '예: 10_계약';
    folderInput.autocomplete = 'off';
    folderLabel.appendChild(folderInput);
    const titleLabel = document.createElement('label');
    titleLabel.textContent = '노트 제목';
    const titleInput = document.createElement('input');
    titleInput.name = 'title';
    titleInput.value = title;
    titleInput.maxLength = 120;
    titleLabel.appendChild(titleInput);
    const hint = document.createElement('p');
    hint.textContent = '명시적 저장 · 새 파일만 생성 · 기존 노트 덮어쓰기 없음';
    const controls = document.createElement('div');
    controls.className = 'msg-save-vault-controls';
    const back = document.createElement('button');
    back.type = 'button';
    back.textContent = '뒤로';
    const confirm = document.createElement('button');
    confirm.type = 'submit';
    confirm.className = 'confirm-btn';
    confirm.textContent = 'MD 노트 생성';
    controls.append(back, confirm);
    form.append(folderLabel, titleLabel, hint, controls);
    destinations.appendChild(form);
    back.addEventListener('click', () => {
      heading.textContent = '이 답변 저장';
      destinations.replaceChildren(documentButton, memoButton, vaultButton);
      setStatus('');
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      event.stopPropagation();
      confirm.disabled = true;
      confirm.textContent = '생성 중…';
      setStatus('');
      try {
        const saved = await _fetchJson('/api/contract-review/vault/notes', {
          method: 'POST',
          body: JSON.stringify({
            snapshot_id: vault.snapshot_id,
            vault_id: vault.vault_id,
            folder: folderInput.value.trim() || '.',
            title: titleInput.value.trim(),
            markdown,
          }),
        });
        msgElement.dataset.savedVaultPath = saved.path || 'saved';
        confirm.textContent = '생성됨';
        setStatus(`${saved.path} · Explorer 재색인 필요`, 'ok');
        await _toast(`Obsidian 노트를 생성했습니다: ${saved.path}`);
      } catch (error) {
        confirm.disabled = false;
        confirm.textContent = 'MD 노트 생성';
        setStatus(error?.message || 'Obsidian 노트를 생성하지 못했습니다.', 'error');
      }
    });
    folderInput.focus();
    folderInput.select();
  }

  vaultButton.addEventListener('click', event => {
    event.stopPropagation();
    if (vault) renderVaultForm();
  });

  destinations.append(documentButton, memoButton, vaultButton);
  _positionMenu(menu, trigger);
  setTimeout(() => {
    if (disposed) return;
    document.addEventListener('pointerdown', outsideHandler, true);
    document.addEventListener('keydown', keyHandler, true);
  }, 0);
}

export default {
  openMessageSaveMenu,
  recommendVaultFolder,
  suggestSavedResultTitle,
};
