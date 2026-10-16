export const NOVELTY_POLICY = 'predicted_path_fraction_v1';
const obj = (v: unknown): Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {};
export function novelty(value: unknown) {
  const data = obj(value);
  const counts = obj(data.counts);
  const number = (v: unknown) => typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : 0;
  const score = data.policy === NOVELTY_POLICY && data.rankable === true && data.coverage === 1 && typeof data.score === 'number' && Number.isFinite(data.score) && data.score >= 0 && data.score <= 1 ? data.score : null;
  return {score, status: data.status === 'partial' ? 'Incomplete path evidence' : 'Not scored',
    coverage: Math.min(1, number(data.coverage)),
    counts: ['observed','predicted','mixed','unknown'].map(key => ({key, count: number(counts[key])})),
    diagnostics: Array.isArray(data.diagnostics) ? data.diagnostics.filter((v): v is string => typeof v === 'string') : [],
    paths: (Array.isArray(data.paths) ? data.paths : []).slice(0,100).map(v => {
      const p = obj(v);
      const text = (key: string) => typeof p[key] === 'string' ? p[key] as string : '';
      return {source: text('source_id'), id: text('path_id'), label: text('label'), status:text('status'),
        rationale:text('rationale'), hash:text('row_sha256'), location:text('source_location'), diagnostic:text('diagnostic')};
    }),
  };
}
