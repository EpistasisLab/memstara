# Addiction KB — Substance use disorders

Explore knowledge-grounded substance-use phenotypes using the available predictors.

## Domain focus

Focus on substance use disorders and related exposures, treatment context and
comorbidities supported by the selected sources. Search relevant substance classes
and disorder concepts; distinguish a recorded diagnosis, an exposure and treatment.
Do not infer active use or disorder severity from a medication or diagnosis alone.
Compare complementary pathways when supported, such as substance-related conditions
and their clinical manifestations. Document possible treatment-indication, disease
severity and ascertainment confounding. Ask whether the supported predictor set is
associated with the fixed outcome in this dataset, not whether substance use causes it.

## Evidence and execution contract

Use the Addiction KB-derived OKF documents actually available through this pipeline's
selected knowledge sources. Inspect source metadata and cite the document IDs and
specific graph paths you read. Do not invent an Addiction KB provenance, edge,
meta-path, publication, source-filter value or column. A domain skill is a research
focus, not a replacement for the Knowledge sources selection or an enforced corpus filter.
If selected sources do not support this domain, explain the gap rather than silently
claiming support from Addiction KB or bypassing the configured source scope.

Before proposing a question, inspect the supplied available-feature context and use
the existing feature-mapping tools to confirm plausible predictor mappings. Preserve
the fixed outcome supplied by the pipeline in both question and hypothesis. Never
use that outcome or a direct outcome-derived proxy as a predictor. Do not change the
outcome to an easier target or request unavailable data as though it existed.

Start with a knowledge-grounded, testable association and a justified feature set.
Include complementary available predictors when they test the stated mechanism;
do not limit the hypothesis arbitrarily to two features or add unrelated variables
merely to increase the feature count. Distinguish measured concepts from imperfect
proxies, confounders, documentation patterns and missing concepts. The data agent
extracts columns; this MVP does not clean or impute the input dataset.

Follow the active pipeline's scientific policy. On the first Loop, use knowledge
and available feature definitions. On later Loops, when pipeline-local learning
context is provided, state the parent finding, what changes, and the uncertainty
this refinement tests. Label previous-result-informed refinements explicitly;
never call them independent knowledge-only discoveries. Do not silently discard a
biologically justified feature because one previous importance value was negative.
Do not access other pipelines' memory or reserved validation outcomes to tune a question.

Use the existing question/hypothesis output schema. Within its rationale or answer,
record the domain focus, source/path evidence, fixed outcome, mapped predictors,
expected association, alternative explanations and what would weaken the hypothesis.
A predictive association is not a causal effect. Prioritize an informative feasible
experiment, not a promised AUC or a claim of clinical readiness. If no supported,
answerable candidate exists, report that limitation through the existing workflow.
