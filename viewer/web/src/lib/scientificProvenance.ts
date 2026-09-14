/** Missing history is never upgraded to knowledge-only or independent validation. */
export function scientificProvenance(evaluation?: {
  hypothesis_policy?: {version?: string; kind?: string; validation_status?: string};
}, hasResult = true) {
  if (!hasResult) return {
    label: 'Generation provenance pending',
    detail: 'The generation policy will be shown when a linked evaluation record is available.',
  };
  const policy = evaluation?.hypothesis_policy;
  if (policy?.version === 'knowledge_only_v1' && policy.kind === 'primary_knowledge_driven') return {
    label: 'Knowledge-driven primary hypothesis',
    detail: 'Generated under a policy excluding prior ML score feedback. This label does not establish independent validation or incremental value.',
  };
  return {
    label: 'Generation provenance not recorded or unrecognized',
    detail: 'This record cannot be classified as a knowledge-only hypothesis. Earlier experiments may have used ML feedback.',
  };
}
