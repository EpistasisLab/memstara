# Psychiatric or substance use disorders

Generate an HIV outcome hypothesis from either the psychiatric-disorder domain or
the substance-use-disorder domain.

## Scope is OR, not required co-occurrence

Treat psychiatric disorders and substance use disorders as a union of two eligible
domains. A candidate may be grounded in a psychiatric disorder, a substance use
disorder, or a supported relationship between them. Do not require both to be present
in the same person, do not construct a combined patient-level indicator unless the
available data explicitly provides one, and do not describe every candidate as
comorbidity or dual diagnosis. Search both domains before choosing so that one is not
silently ignored merely because it appears first or has more documents.

Within the psychiatric domain, distinguish symptoms, diagnoses, treatment indications
and medication exposures. Within the substance-use domain, distinguish substance
exposure, diagnosed disorder, severity, treatment and remission. Do not infer an active
disorder from a medication, diagnosis code or shared symptom alone. Account for
temporality, healthcare-contact patterns, treatment indication, severity and
ascertainment as plausible alternative explanations.

## Evidence and execution contract

Use only the selected knowledge sources and cite the OKF documents and graph paths
actually inspected. A graph connection is hypothesis-generating evidence, not proof of
causality. If neither domain has adequate evidence or a defensible mapping to available
predictors, report that limitation instead of inventing support.

Inspect the available-feature context before proposing a question and verify exact
predictor mappings with the provided tools. Preserve the pipeline's fixed HIV outcome;
never substitute a psychiatric or substance-use endpoint for it. Exclude the outcome,
outcome-derived proxies and information unavailable at prediction time. State whether
the selected candidate came from the psychiatric domain, the substance-use domain, or
a genuinely supported cross-domain relationship.

Use the existing question and hypothesis schemas. Record the mapped predictors,
expected association, evidence, proxy limitations, alternative explanations and what
would weaken the hypothesis. Frame the result as a testable predictive association, not
a causal claim or a promise of clinical utility.
