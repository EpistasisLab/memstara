# Research priorities and next experiments

Recommend which hypotheses deserve the next experiment and explain why.

## Focus

Focus the executive recommendation on at most two feasible next experiments.
Compare knowledge grounding, the uncertainty each experiment could resolve,
available predictors and supporting or conflicting measurements. AUC alone must
not determine priority. A weak or null result may motivate a discriminating test,
but is not positive evidence for the original claim.

For each leading proposal, state the specific next test, comparator, required
additional evidence, and observations that would support or weaken it. Distinguish
new knowledge-grounded questions from refinements of earlier results. Use only
recorded matched model comparisons to claim incremental predictive value. If no
candidate has an informative feasible next test, say so instead of forcing a winner.

## Reporting contract

This skill changes emphasis and presentation, not the underlying measurements or
pipeline configuration. Preserve the base report prompt's required sections,
Ranked hypotheses table, word limit and final_answer submission contract. Place
these perspectives within the required sections instead of replacing the schema.
Use only records available to this execution. Cite result/task IDs and recorded
Loop numbers; do not infer cross-pipeline access or invent a missing Loop mapping.

Keep measured metrics separate from LLM judgments. Explicitly label qualitative
rank, evidence strength, clinical actionability, novelty and recommendations as
LLM assessments, not computed scores. Novelty is relative to consulted sources,
not proof of an original discovery. Do not introduce Confidence or Reproducibility
rating columns. Report refit evidence separately from multi-split robustness and
independent validation, using actual records rather than requested settings.

Report missing, failed and unfavorable evidence. Do not invent features, effect
directions, metrics, thresholds, citations, patient details or clinical approval.
Preserve recorded provisional/reviewer-pending notices. Distinguish an exploratory
association from causation and research priority from clinical readiness. An
interesting follow-up may merit study without being clinically actionable; never
inflate the evidence to justify that recommendation. Mark previous-result-informed
refinements as adaptive exploration, not independent confirmation. Use Loop for
pipeline cycles; retain analysis IDs when a reliable Loop mapping is unavailable.
