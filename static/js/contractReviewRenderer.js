// Pure, safe renderer for validated Contract Review result metadata.

const BLOCKS = [
  ['review_summary', 'Review summary / 검토 요약'],
  ['local_document_evidence', 'Local document evidence / 로컬 문서 근거'],
  ['vault_note_evidence', 'Vault note evidence / Vault 노트 근거'],
  ['official_legal_evidence', 'Official legal evidence / 법령·판례 공식 근거'],
  ['model_interpretation', 'Model interpretation / 모델의 해석·권고'],
  ['uncertainty_and_follow_up', 'Uncertainty and follow-up / 불확실성·추가 확인'],
];

function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function renderValue(value) {
  if (Array.isArray(value)) {
    if (!value.length) return '<p class="contract-review-empty">No verified evidence.</p>';
    return `<ul>${value.map(item => {
      if (!item || typeof item !== 'object') return `<li>${esc(item)}</li>`;
      const label = item.title || item.path || item.citation_id || item.risk || item.issue || item.id || 'Evidence';
      const state = item.verification_state ? `<span class="contract-review-proof">${esc(item.verification_state)}</span>` : '';
      const detail = item.text || item.content || item.excerpt || item.analysis || item.detail || '';
      const followUp = item.follow_up ? `<p><strong>Follow-up:</strong> ${esc(item.follow_up)}</p>` : '';
      return `<li><div><strong>${esc(label)}</strong>${state}</div>${detail ? `<p>${esc(detail)}</p>` : ''}${followUp}</li>`;
    }).join('')}</ul>`;
  }
  if (value && typeof value === 'object') {
    if (value.text) return `<p>${esc(value.text)}</p>`;
    if (value.content) return `<p>${esc(value.content)}</p>`;
    if (Array.isArray(value.items)) return renderValue(value.items);
    return `<dl>${Object.entries(value).map(([key, item]) => `<dt>${esc(key)}</dt><dd>${esc(item)}</dd>`).join('')}</dl>`;
  }
  return `<p>${esc(value || 'No content.')}</p>`;
}

export function renderContractReviewResult(result) {
  if (!result || result.schema_version !== 'contract-review.v2' || !result.blocks) return '';
  const usage = result.usage || {};
  const usageLabel = usage.source === 'actual' ? 'Actual provider usage'
    : usage.source === 'estimated' ? 'Estimated usage'
      : 'Usage unavailable';
  const counts = Number.isInteger(usage.input_tokens) && Number.isInteger(usage.output_tokens)
    ? ` · ${usage.input_tokens} in / ${usage.output_tokens} out`
    : '';
  return `<article class="contract-review-result" data-schema="contract-review.v2">
    <header><div><strong>Contract Review</strong><span>${esc(result.generated_at || '')}</span></div>
      <span class="contract-review-usage" data-source="${esc(usage.source || 'unavailable')}">${esc(usageLabel + counts)}</span></header>
    ${BLOCKS.map(([key, label]) => `<section data-contract-block="${key}"><h3>${esc(label)}</h3>${renderValue(result.blocks[key])}</section>`).join('')}
    <footer class="contract-review-result-actions">
      <button type="button" class="confirm-btn contract-review-save-report" data-contract-review-save>Documents에 보고서 저장</button>
      <span class="contract-review-save-status" data-contract-review-save-status role="status" aria-live="polite"></span>
    </footer>
  </article>`;
}

export default { renderContractReviewResult };
