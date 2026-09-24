import type { Result } from '../types';

type Point = NonNullable<NonNullable<NonNullable<Result['evaluation']>['explanation']>['operating_point']>;
export function precisionExplanation(point: Point): string | null {
  if (point.precision != null && Number.isFinite(point.precision)) return null;
  if (point.true_positive === 0 && point.false_positive === 0) return 'No positive predictions at this cutoff. Precision = TP / (TP + FP) = 0 / 0, so it is undefined, not 0%. Sensitivity can be 0% while specificity is 100% when every prediction is negative.';
  return 'Precision was not recorded or cannot be calculated from the available evidence. The interface does not infer a zero value or an all-negative prediction pattern.';
}

export function validationEvidence(result: Result) {
  const evaluation = result.evaluation;
  if (evaluation?.hypothesis_policy?.validation_status === 'exploratory_not_independently_validated'
      || evaluation?.evaluation?.score_scope === 'adaptive_exploration'
      || evaluation?.evaluation?.validation_reserve?.status === 'reserved_not_evaluated') {
    return {label: 'Not validated', reason: evaluation?.evaluation?.validation_reserve?.status === 'reserved_not_evaluated'
      ? 'Exploratory evaluation only. Reserved validation data has not been evaluated.'
      : 'This result is recorded as exploratory, without independent validation.'};
  }
  return {label: 'Validation not recorded', reason: 'No supported independent-validation record is available. AUC, repeated splits and reproducible refits do not establish independent validation.'};
}

export function splitEvidence(result: Result) {
  const evaluation = result.evaluation?.evaluation;
  const runs = evaluation?.replicates ?? [];
  const unique = new Set(runs.map(r => r.split_id).filter(Boolean)).size;
  const requested = evaluation?.plan?.replicates;
  return {runs, unique, requested, summary: !runs.length
    ? 'Executed split records are unavailable. Configuration alone does not prove that splits were evaluated.'
    : unique === 0 ? 'Evaluations were recorded without split identifiers. The number of distinct splits cannot be verified.'
    : unique > 1 ? `${runs.length} evaluations across ${unique} distinct hold-out splits were recorded. This measures split sensitivity, not independent clinical validation.`
    : 'One distinct hold-out split was evaluated. Robustness across different splits has not been assessed; the original computation can still be reproducible.'};
}
