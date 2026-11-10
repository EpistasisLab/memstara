export type SavedOutputCounts = {results: number; questions: number; run_tags: string[]};

/** Use the active execution consistently in polling, the header and overview. */
export function workspaceOutputHeads(items: {running?: {run_tag: string} | null; latest?: {run_tag: string} | null}[]) {
  return [...new Set(items.flatMap(item => {
    const tag = (item.running ?? item.latest)?.run_tag;
    return tag ? [tag] : [];
  }))].sort();
}

/** Never replace an unavailable total with the bounded live activity cache. */
export function scopedSavedCounts(value: unknown, scope: Set<string>): SavedOutputCounts | null {
  if (!value || typeof value !== 'object') return null;
  const counts = value as SavedOutputCounts;
  if (![counts.results, counts.questions].every(n => Number.isSafeInteger(n) && n >= 0)
    || !Array.isArray(counts.run_tags) || counts.run_tags.some(tag => typeof tag !== 'string')) return null;
  const tags = new Set(counts.run_tags);
  if (tags.size !== scope.size || [...scope].some(tag => !tags.has(tag))) return null;
  return counts;
}
