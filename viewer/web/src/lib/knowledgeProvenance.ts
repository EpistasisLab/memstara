/** Defensive rendering of recorded source declarations, never a novelty score. */
const object = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
const labels: Record<string, string> = {
  observed: 'Observed relations declared', predicted: 'Predicted relations declared',
  mixed: 'Mixed relations declared', unknown: 'Unverified or conflicting annotation',
  not_applicable: 'Literature evidence; metapath classification not applicable',
};
export function knowledgeProvenance(value: unknown) {
  const record = object(value);
  if (record?.version !== 'hypothesis_provenance_v1') return null;
  const sources = Array.isArray(record.sources) ? record.sources : [];
  return {
    empty: record.status === 'no_declared_sources',
    total: sources.length,
    sources: sources.slice(0, 50).map(value => {
      const row = object(value) ?? {};
      const metadata = object(row.provenance) ?? {};
      const inventory = object(metadata.path_inventory);
      const pathCount = inventory?.version === 'path_inventory_v1' && Number.isSafeInteger(inventory.row_count)
        && Number(inventory.row_count) >= 0 ? Number(inventory.row_count) : null;
      const diagnostics = Array.isArray(metadata.diagnostics) ? metadata.diagnostics.filter(v => typeof v === 'string') : [];
      if (typeof row.diagnostic === 'string') diagnostics.push(row.diagnostic);
      return {
        ref: typeof row.id === 'string' ? row.id : typeof row.declared_ref === 'string' ? row.declared_ref : 'Reference unavailable',
        label: typeof row.status === 'string' && Object.hasOwn(labels, row.status) ? labels[row.status] : labels.unknown,
        fingerprint: typeof metadata.parsed_source_sha256 === 'string' ? metadata.parsed_source_sha256 : '',
        diagnostics,
        pathCount,
      };
    }),
  };
}
