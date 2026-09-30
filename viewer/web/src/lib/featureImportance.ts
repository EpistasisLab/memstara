/** Read historical flat maps and explicitly labelled permutation rankings without coercion. */
export function featureImportance(raw: unknown) {
  const record = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
  const method = typeof record.method === 'string' ? record.method : '';
  const note = typeof record.note === 'string' ? record.note : '';
  const ranking = record.permutation_ranking ?? record.ranking;
  const entries: [string, number][] = [];
  if (Array.isArray(ranking)) {
    for (const row of ranking) {
      if (row && typeof row.feature === 'string' && typeof row.score === 'number' && Number.isFinite(row.score)) entries.push([row.feature, row.score]);
    }
  } else {
    for (const [key, value] of Object.entries(record)) {
      if (typeof value === 'number' && Number.isFinite(value)) entries.push([key, value]);
    }
  }
  const values = Object.fromEntries(entries);
  return {values, method, note, unsupported: Object.keys(record).length > 0 && entries.length === 0};
}

/** Rank recorded numeric values, never absolute values. Missing values are not zero. */
export function rankedContributions(raw: unknown, exclude = '', magnitude = false) {
  return Object.entries(featureImportance(raw).values)
    .filter(([name, value]) => name !== exclude && (!magnitude || value >= 0))
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function contributionScale(entries: [string, number][]) {
  const low = Math.min(0, ...entries.map(([, value]) => value));
  const high = Math.max(0, ...entries.map(([, value]) => value));
  const range = high - low || 1;
  return {low, high, range, position: (value: number) => (value - low) / range * 100};
}
