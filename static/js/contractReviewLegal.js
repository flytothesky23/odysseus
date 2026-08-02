const DECISION_NUMBER = /\b\d{4}[가-힣]{1,4}\d{3,}\b/u;
const LONG_LAW_NAME = /([가-힣][가-힣\s·]{1,58}?에 관한 법률)(?=상|의|에서|으로|에|을|를|과|와|[,\s]|$)/u;
const SHORT_LAW_NAME = /([가-힣]{1,24}법)(?=상|의|에서|으로|에|을|를|과|와|[,\s]|$)/gu;

export function extractLegalLookup(message) {
  const text = String(message || '').replace(/\s+/g, ' ').trim();
  if (!text) return null;
  const decision = text.match(DECISION_NUMBER);
  if (decision) {
    const court = /대법원/u.test(text) ? '대법원 ' : '';
    return { tool: 'search_decisions', query: `${court}${decision[0]}`.trim() };
  }
  const longName = text.match(LONG_LAW_NAME)?.[1]?.trim();
  if (longName) return { tool: 'search_law', query: longName };
  for (const match of text.matchAll(SHORT_LAW_NAME)) {
    const candidate = match[1];
    if (['위법', '불법', '합법', '사법', '입법'].includes(candidate)) continue;
    return { tool: 'search_law', query: candidate };
  }
  return null;
}
