/**
 * Parse timestamps returned by Odysseus APIs.
 *
 * SQLAlchemy stores application timestamps as naive UTC. Browsers otherwise
 * interpret those strings as local wall time, which makes recent items appear
 * nine hours old in Asia/Seoul. Explicit ISO-8601 offsets remain authoritative.
 */
export function parseOdysseusTimestamp(value) {
  const raw = String(value || '').trim();
  if (!raw) return new Date(NaN);
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw);
  const normalized = hasOffset ? raw : raw.replace(' ', 'T') + 'Z';
  return new Date(normalized);
}
