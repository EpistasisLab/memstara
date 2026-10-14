# Heart failure — Metabolic, renal and other comorbidities

Explore knowledge-grounded, feasible associations with the fixed heart-failure study target.

## Domain focus

Focus on diabetes, obesity, metabolic abnormalities and renal comorbidities
supported by the selected corpus and predictor definitions. Inspect the
metabolic-renal-comorbidity topic when the knowledge tools confirm it exists.
Distinguish measured conditions from proxies, disease severity and treatment
indications. Do not invent eGFR, laboratory values or renal diagnoses if the CSV
only provides histories of diabetes or obesity. Consider relevant cardiovascular
confounders only where measured and scientifically justified. Do not substitute
unavailable comorbidities with unrelated variables just to meet the feature budget.
Separate evidence of association from mechanisms and causal effects. Check whether
conditions preceded the target; unknown timing limits prospective interpretation.

## Evidence and execution contract

Use only the HeartFailure OKF documents available through the selected knowledge
sources. Inspect source metadata and cite the document IDs and specific predictor
rows or graph paths actually read. Do not invent papers, effect sizes, graph paths,
source-filter values or columns. This skill defines a research focus; the active
pipeline source selection remains authoritative. If the sources do not support a
candidate, explain the gap through the existing workflow.

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
