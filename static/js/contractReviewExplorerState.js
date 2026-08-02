const collator = new Intl.Collator('ko-KR', { numeric: true, sensitivity: 'base' });

function normalized(value) {
  return String(value || '').normalize('NFKC').toLocaleLowerCase('ko-KR');
}

function safeRelativeMarkdownPath(value) {
  const path = String(value || '').trim().replace(/\\/g, '/');
  if (!path || path.startsWith('/') || /^[A-Za-z]:\//.test(path)) return '';
  if (!path.toLocaleLowerCase('en-US').endsWith('.md')) return '';
  if (path.split('/').some(part => !part || part === '.' || part === '..' || part.startsWith('.'))) return '';
  return path;
}

function safeRelativeScopePath(value) {
  const path = String(value || '').trim().replace(/\\/g, '/');
  if (!path || path.startsWith('/') || /^[A-Za-z]:\//.test(path)) return '';
  if (path.split('/').some(part => !part || part === '.' || part === '..' || part.startsWith('.'))) return '';
  return path;
}

function safeScope(value) {
  const input = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const rules = [];
  const seen = new Set();
  for (const raw of Array.isArray(input.rules) ? input.rules.slice(0, 2000) : []) {
    const path = safeRelativeScopePath(raw?.path);
    if (!path || typeof raw?.included !== 'boolean' || seen.has(path)) continue;
    seen.add(path);
    rules.push({ path, included: raw.included });
  }
  return { default_included: input.default_included !== false, rules };
}

export function isPathIncludedByScope(path, scope) {
  const target = safeRelativeScopePath(path);
  const safe = safeScope(scope);
  if (!target) return false;
  let included = safe.default_included;
  let specificity = -1;
  safe.rules.forEach((rule, index) => {
    if (target !== rule.path && !target.startsWith(`${rule.path}/`)) return;
    const ruleSpecificity = rule.path.split('/').length * 10000 + index;
    if (ruleSpecificity >= specificity) {
      included = rule.included;
      specificity = ruleSpecificity;
    }
  });
  return included;
}

export function updateScopeSelection(scope, path, included) {
  const safe = safeScope(scope);
  const normalizedPath = safeRelativeScopePath(path);
  if (!normalizedPath || typeof included !== 'boolean') return safe;
  const prefix = `${normalizedPath}/`;
  const rules = safe.rules.filter(rule => rule.path !== normalizedPath && !rule.path.startsWith(prefix));
  rules.push({ path: normalizedPath, included });
  return { default_included: safe.default_included, rules: rules.slice(-2000) };
}

function noteSort(a, b) {
  return collator.compare(String(a.filename || a.title || a.path), String(b.filename || b.title || b.path));
}

export function filterVaultNotes(notes, query) {
  const needle = normalized(query).trim();
  const valid = (Array.isArray(notes) ? notes : [])
    .filter(note => safeRelativeMarkdownPath(note?.path));
  const matched = needle
    ? valid.filter(note => normalized([
      note.title,
      note.filename,
      note.stem,
      note.path,
      ...(Array.isArray(note.aliases) ? note.aliases : []),
    ].join('\n')).includes(needle))
    : valid;
  return [...matched].sort((a, b) => collator.compare(a.path, b.path));
}

export function buildVaultTree(notes) {
  const root = { name: '', path: '', folders: new Map(), notes: [] };
  for (const note of filterVaultNotes(notes, '')) {
    const parts = note.path.split('/');
    let current = root;
    for (const name of parts.slice(0, -1)) {
      const path = current.path ? `${current.path}/${name}` : name;
      if (!current.folders.has(name)) {
        current.folders.set(name, { name, path, folders: new Map(), notes: [] });
      }
      current = current.folders.get(name);
    }
    current.notes.push(note);
  }

  const freeze = folder => ({
    name: folder.name,
    path: folder.path,
    folders: [...folder.folders.values()]
      .sort((a, b) => collator.compare(a.name, b.name))
      .map(freeze),
    notes: [...folder.notes].sort(noteSort),
  });
  return freeze(root);
}

export function descendantNotePaths(folder) {
  if (!folder) return [];
  return [
    ...(Array.isArray(folder.notes) ? folder.notes.map(note => note.path) : []),
    ...(Array.isArray(folder.folders) ? folder.folders.flatMap(descendantNotePaths) : []),
  ].filter(safeRelativeMarkdownPath);
}

export function folderSelectionState(paths, selectedPaths) {
  const candidates = [...new Set((Array.isArray(paths) ? paths : []).map(safeRelativeMarkdownPath).filter(Boolean))];
  const selectedSet = new Set((Array.isArray(selectedPaths) ? selectedPaths : []).map(safeRelativeMarkdownPath).filter(Boolean));
  const selected = candidates.filter(path => selectedSet.has(path)).length;
  return {
    state: selected === 0 ? 'unchecked' : selected === candidates.length ? 'checked' : 'mixed',
    selected,
    total: candidates.length,
  };
}

export function updateBoundedSelection(current, paths, checked, limit = 8) {
  const cap = Math.max(1, Math.min(Number(limit) || 8, 50));
  const selected = new Set(
    (Array.isArray(current) ? current : []).map(safeRelativeMarkdownPath).filter(Boolean).slice(0, cap),
  );
  const candidates = [...new Set(
    (Array.isArray(paths) ? paths : []).map(safeRelativeMarkdownPath).filter(Boolean),
  )];
  let rejectedCount = 0;
  for (const path of candidates) {
    if (!checked) {
      selected.delete(path);
      continue;
    }
    if (selected.has(path)) continue;
    if (selected.size >= cap) {
      rejectedCount += 1;
      continue;
    }
    selected.add(path);
  }
  return { selected_paths: [...selected], rejected_count: rejectedCount };
}

export function reconcileSelectedPaths(current, notes, limit = 8) {
  const cap = Math.max(1, Math.min(Number(limit) || 8, 50));
  const available = new Set(
    (Array.isArray(notes) ? notes : [])
      .map(note => safeRelativeMarkdownPath(note?.path))
      .filter(Boolean),
  );
  return [...new Set(
    (Array.isArray(current) ? current : [])
      .map(safeRelativeMarkdownPath)
      .filter(path => path && available.has(path)),
  )].slice(0, cap);
}
