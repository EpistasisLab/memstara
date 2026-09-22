import ContentOrigin from "./ContentOrigin";
import type { Result, QuestionContract } from '../types';
import { scientificProvenance } from '../lib/scientificProvenance';
export default function ScientificProvenance({result, contract}: {result?: Result; contract?: QuestionContract}) {
  const lineage = result?.evaluation?.question_contract ?? contract;
  const evaluation = result?.evaluation ?? (lineage?.kind ? {hypothesis_policy: {
    version: 'iterative_discovery_v1', kind: lineage.kind,
  }} : undefined);
  const provenance = scientificProvenance(evaluation, !!evaluation);
  return <div className="my-3 rounded-lg border border-paper-line bg-paper p-3 text-xs" data-testid="scientific-provenance">
    <strong>{provenance.label}</strong>
    <p className="mt-1 text-ink-soft">{provenance.detail}</p>
    {lineage?.origin_wave !== undefined && <p className="mt-2">Loop {lineage.origin_wave + 1}</p>}
    {!!lineage?.parent_task_ids?.length && <p className="mt-1">Builds on prior task(s): {lineage.parent_task_ids.join(', ')}</p>}
    {lineage?.learning_goal && <p className="mt-2 text-sm"><ContentOrigin kind="proposal" compact/><strong>What this follow-up tests: </strong>{lineage.learning_goal}</p>}
  </div>;
}
