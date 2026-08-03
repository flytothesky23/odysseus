const DECISION_NUMBER = /\b\d{4}[가-힣]{1,4}\d{3,}\b/u;
const LONG_LAW_NAME = /([가-힣][가-힣\s·]{1,58}?에 관한 법률)(?=상|의|에서|으로|에|을|를|과|와|[,\s]|$)/u;
const SHORT_LAW_NAME = /([가-힣]{1,24}법)(?=상|의|에서|으로|에|을|를|과|와|[,\s]|$)/gu;
const ARTICLE_REFERENCE = /제\s*\d+\s*조(?:의\s*\d+)?/u;

export function extractLegalLookup(message) {
  const text = String(message || '').replace(/\s+/g, ' ').trim();
  if (!text) return null;
  const decision = text.match(DECISION_NUMBER);
  if (decision) {
    const court = /대법원/u.test(text) ? '대법원 ' : '';
    return { tool: 'search_decisions', query: `${court}${decision[0]}`.trim() };
  }
  const article = text.match(ARTICLE_REFERENCE)?.[0]?.replace(/\s+/g, '') || '';
  const longName = text.match(LONG_LAW_NAME)?.[1]?.trim();
  if (longName) return { tool: 'search_law', query: longName, ...(article ? { jo: article } : {}) };
  for (const match of text.matchAll(SHORT_LAW_NAME)) {
    const candidate = match[1];
    if (['위법', '불법', '합법', '사법', '입법'].includes(candidate)) continue;
    return { tool: 'search_law', query: candidate, ...(article ? { jo: article } : {}) };
  }
  return null;
}

export function buildLegalLookupArguments(lookup) {
  if (!lookup || typeof lookup !== 'object') return null;
  if (lookup.tool === 'search_decisions') {
    return { domain: 'precedent', query: String(lookup.query || ''), display: 5 };
  }
  if (lookup.tool === 'search_law') {
    return {
      query: String(lookup.query || ''),
      display: 5,
      ...(lookup.jo ? { jo: String(lookup.jo) } : {}),
    };
  }
  return null;
}
