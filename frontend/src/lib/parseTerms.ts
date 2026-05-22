// Splits a free-text search box into clean, de-duplicated search terms.
// Splits on newlines AND commas (never spaces, so multi-word phrases survive),
// and strips leading list markers like "1.", "2)", "-", "•", "*".
const LIST_MARKER = /^\s*(\d+[.)]|[-*•])\s+/;

export function parseTerms(raw: string): string[] {
  if (!raw) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const piece of raw.split(/[\n,]/)) {
    const term = piece.replace(LIST_MARKER, "").trim();
    if (!term) continue;
    const key = term.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(term);
  }
  return out;
}
