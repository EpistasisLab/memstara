import type { Result } from '../types';
import { validationEvidence } from '../lib/metricEvidence';

export default function ValidationStatus({result}: {result: Result}) {
  const evidence = validationEvidence(result);
  return <div className="my-3 rounded-lg border border-paper-line bg-paper-panel p-3 text-sm" data-testid="validation-status">
    <strong>{evidence.label}</strong><span className="ml-2 text-xs text-ink-soft">Recorded validation status · not an LLM rating</span>
    <p className="mt-1 text-ink-soft">{evidence.reason}</p>
    <p className="mt-1 text-xs text-ink-soft">This does not mean the hypothesis is false, unreproducible or unworthy of further research.</p>
  </div>;
}
