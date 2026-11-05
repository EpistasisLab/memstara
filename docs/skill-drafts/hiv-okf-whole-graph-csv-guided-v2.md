# HIV — Whole Knowledge Graph: CSV-Guided Discovery (V2)

Develop a testable hypothesis for the fixed HIV outcome using the supplied CSV
predictor definitions, general biomedical reasoning and evidence from the entire
selected OKF scope. Begin candidate discovery by understanding the available
measurements. Search across the graph without choosing a clinical specialty in
advance, and verify evidence before committing to a predictor set.

## Domain focus

Let the configured outcome and the meaning of available measurements guide the
initial candidate search. Use general biomedical knowledge to interpret feature
definitions, identify plausible relationships and anticipate measurement limitations.
Label this reasoning as general knowledge; do not present it as retrieved evidence
or invent citations, statistics or effects.

Preserve broad graph exploration. Consider materially different clinical concepts,
intermediates and metapath patterns supported by the selected sources. No laboratory
test, diagnosis, medication, specialty or graph category is mandatory. Do not assume
that familiar clinical predictors, the most densely connected concepts or a larger
feature set will produce the best hypothesis.

Here, whole-graph search means that no specialty filter is imposed in advance. It
does not imply exhaustive reading or freedom from publication, curation or population
bias. Report the actual scope examined and important remaining gaps.

## Study and evidence contract

The driver, frozen study contract and scientific policy take precedence. Preserve
the configured target, labels, prediction time and exclusions. If timing or horizon
is unspecified, state that limitation; do not assume measurements precede ART
initiation or describe a cross-sectional association as prospective prediction.

Use the permitted predictor context and selected OKF sources. This is a retrieved
knowledge condition. General knowledge can motivate a candidate, but does not waive
the active grounding requirements. Under the current OKF driver, each selected
predictor must map to an assigned concept and an actual selected source read.
Do not retain a favored feature by attaching an unrelated source, fabricating a
missing path or silently switching to an ungrounded question.

Distinguish three kinds of information throughout the rationale:

* Dataset definition: what the column is explicitly documented to measure.
* General-knowledge inference: what that measurement may represent or predict.
* Retrieved evidence: what the cited document and specific graph path actually state.

An HIV/AIDS endpoint in a graph does not automatically establish an association
with detectable HIV status. Explain the remaining inferential gap to the fixed
outcome instead of inventing an edge that closes it.

## Search procedure

1. Read the fixed contract and available predictor definitions. During question
   writing, use the supplied context and permitted catalog tools; during answering,
   begin with the assigned question and dataset description. Do not request tools
   or study data outside the assigned stage.
2. Inspect the complete permitted predictor catalog as needed. A preview is not the
   full catalog. Check exact names, codes, units where stated, exclusions and
   missingness metadata. Distinguish measurements, diagnosis records, medication
   indicators and proxies; do not infer unavailable timing, severity or adherence.
3. Form a small provisional shortlist of outcome-relevant concepts represented by
   eligible columns. State why each candidate could test one coherent association.
   Do not inspect outcome values, outcome cross-tabulations or model performance
   to discover promising variables.
4. Map the selected OKF scope: available categories, metadata, node and edge types,
   and metapath patterns. Search broadly around the outcome and shortlisted concepts
   without imposing a specialty filter. Check multiple relevant formulations.
5. Read concrete instances and evidence from distinct graph regions when available.
   Allow graph evidence to introduce a materially different candidate, and check
   its CSV representation immediately. Use both CSV-to-graph and graph-to-CSV
   exploration; neither a familiar measurement nor the first plausible path is a
   sufficient stopping rule.
6. Revise the shortlist when evidence is missing, the measurement is unsuitable or
   a competing explanation is stronger. Report unsupported candidates and the
   specific gap. Do not claim that a concept is absent from the whole corpus after
   a partial search or force coverage of every category.
7. Select the most informative answerable candidate using the criteria below.
   Verify exact mappings before proposal or task creation, as the stage requires.

## Reading graph evidence

Copy actual document IDs, metapath patterns and path instances. Preserve edge
direction and distinguish treatment, adverse effect, ISA, association, co-mention
and co-occurrence. Report observed, predicted, mixed or unknown evidence as recorded;
predicted links are unvalidated, and an observed edge remains a source assertion.

Consider hub bias, evidence density and source-population differences. Path counts
and graph scores are not effect sizes or independent replication. A mechanistic
path may motivate a concept without supplying a direct measurement in this dataset.
Prefer interpretable relationships and explicit limitations over unsupported
clinical equivalence or long chains through generic hubs.

## Selecting and mapping predictors

Compare candidates on relevance to the fixed outcome, evidence quality, measurement
directness, temporal eligibility, redundancy, leakage risk and what the experiment
would teach if the association holds or fails. State whether the reasoning concerns
an established association or a less established relationship.

Choose the predictors needed for one coherent hypothesis. Explain the role and
source support of each selected column. Complementary predictors may span domains,
but do not collect unrelated variables, impose a specialty quota, copy a historical
winning set or add a baseline outside the configured comparison policy. Respect the
active original-column count and any exact count supplied by the driver.

Use the matcher to verify concepts against exact columns. Review all plausible
matches; semantic rank alone is not clinical equivalence. Name proxies for what
they measure and disclose definition mismatches. If an essential concept remains
unavailable, revise the question rather than silently substituting another condition.

Exclude identifiers, the target, direct outcome-derived proxies and known
post-outcome information. Do not create derived features without explicit driver
support. Leave extraction, imputation, encoding, splitting and fitting to their
responsible stages. Do not change the CSV or relax missing-value or evaluation checks.

## Feedback and recovery

Use prior results only when explicitly supplied and permitted by the driver. Record
the parent finding, proposed change and uncertainty being tested. Do not access
other pipelines' memory or reserved validation outcomes, and do not treat a negative
importance value as proof that a feature is irrelevant. Preserve the study's declared
exploratory status; a skill designed after inspecting prior results needs fresh
evaluation before supporting an independent confirmation claim.

Inspect tool responses. Repair rejected mappings or propose a different supported
candidate within the same Loop and the driver's recovery budget. A duplicate,
rejected or empty proposal is not completed work. Report specific obstacles for
regeneration; do not bypass validation or silently mark a failed analysis complete.

## Output

Use the assigned stage's existing question or task schema without adding unsupported
top-level fields. During question writing, supply the required predictor concepts,
source IDs, actual OKF tags, rationale and exact proposed mappings. During answering,
preserve the assigned question and required hypothesis, copy exact matched column
names and return the task ID from a successful task-creation call.

Within supported rationale and mapping fields, state:

* The fixed outcome, selected association and expected direction or explicit uncertainty.
* CSV definitions used to motivate the candidate and each predictor's direct-measure
  or proxy status, measurement limitations and role in the hypothesis.
* General-knowledge reasoning, retrieved support and remaining inferential gaps,
  clearly distinguished from one another.
* Graph regions and alternatives examined, candidates set aside with reasons, and
  why this candidate was preferred.
* Source IDs, metapath patterns, concrete path instances and recorded evidence types.
* Timing uncertainty, alternative explanations, corpus blind spots and findings
  that would weaken the hypothesis.

For every metapath relied upon, copy the recorded source and path IDs into
`path_uses` with a use-specific rationale, as required by the driver. Cover the
metapath sources actually used. Do not list unused paths or invent an ID or novelty
score. Keep the rationale concise while preserving reviewable evidence and mappings.
Clinical plausibility, graph connectivity and predictive performance do not establish
causation, treatment benefit or clinical readiness.
