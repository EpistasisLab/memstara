# Clinician-friendly research summary

Explain findings in plain language for clinicians who are not ML specialists.

## Focus

Lead with the clinical research question, the population and fixed outcome when
recorded, and what was actually observed. Explain technical terms briefly at first
use: AUC describes ranking of outcomes, not a patient's chance of disease or proof
of clinical benefit. Translate feature codes only when a documented meaning exists.

For each leading finding explain: what the model used, what this may mean, what is
uncertain, and what the research team should investigate next. Clearly distinguish
an available feature from an unmeasured clinical concept. Explain undefined
precision in plain language when no positive predictions were made. Separate the
model's probability cutoff from any clinically validated intervention threshold.
Use short sentences and compact tables; do not turn the report into treatment advice
or hide limitations in a technical appendix.

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
