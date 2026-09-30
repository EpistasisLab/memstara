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
