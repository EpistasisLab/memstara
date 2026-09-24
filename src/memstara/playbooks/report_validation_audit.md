# Evidence and validation audit

Examine whether each conclusion is supported and what verification remains.

<!-- Purpose-specific project report skill. Retains the existing report schema and measured-evidence contract. -->

## Focus

Focus on traceability from question to fixed target, selected features, actual
model evaluation, interpretation and recommendation. Identify target mismatch,
missing predictors, failed stages and unsupported interpretation only when the
records show them. A missing audit artifact is a check not recorded, not proof
that a defect occurred or that the run passed.

Review recorded split strategy, leakage safeguards, class balance, threshold
metrics, baseline comparisons, refit verification and independent validation.
Separate reproducibility under the same conditions from sensitivity to different
splits. Explain precision N/A without treating it as zero. Preserve actual AUC
and report its evaluation scope; do not call an exploratory maximum a validated
performance ceiling.

In the limitations section, use Finding / Supporting record / Consequence / Next
check for the most material issues. Recommend the smallest concrete verification
that would settle each uncertainty. This is a research evidence review, not a
regulatory certification, clinical approval or a claim that new tests were run.

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
