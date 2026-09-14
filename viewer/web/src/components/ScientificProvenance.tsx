import type { Result } from '../types';
import { scientificProvenance } from '../lib/scientificProvenance';
export default function ScientificProvenance({result}: {result?: Result}) {
  const provenance = scientificProvenance(result?.evaluation, !!result);
  return <div className="my-3 rounded-lg border border-paper-line bg-paper p-3 text-xs" data-testid="scientific-provenance">
    <strong>{provenance.label}</strong>
    <p className="mt-1 text-ink-soft">{provenance.detail}</p>
  </div>;
}
