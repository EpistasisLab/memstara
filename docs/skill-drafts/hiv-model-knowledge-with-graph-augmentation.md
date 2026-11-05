# HIV — Model Knowledge with Graph Augmentation

Develop a testable hypothesis for the fixed HIV outcome in two phases: first form
a coherent predictor set using general biomedical knowledge and CSV definitions;
then search the entire selected OKF for complementary, measurable information.
Preserve the original candidate as a comparison and justify each proposed addition.

## Fixed outcome and label meanings

Read the registered study contract before selecting predictors. For the current
HIV study, the configured target column is `HIV_DETECTABLE`, with positive label
`1` and negative label `0`. The research objective is to classify HIV detectability
as encoded in that column. Confirm the labels against the supplied contract;
this example must not override a different registered target or encoding.

Use the target definition and general clinical reasoning to judge which measurements
could be relevant. Knowing the outcome's definition and label meanings is permitted;
inspecting subjects' actual target values to choose predictors is not. The target
must remain unchanged through candidate generation, graph augmentation and evaluation.

Do not infer an assay threshold, observation window or treatment-response definition
from the column name alone. Preserve the registered prediction time and horizon.
If they are unspecified, report that limitation rather than assuming the CSV
establishes a prospective outcome after ART initiation.

## Execution contract

This skill uses the versioned `model_knowledge_graph_augmentation_v1` driver.
Select it as a separate Hypothesis condition in All Combinations with one hypothesis,
one task and one held-out split per Loop. The normal CSV and selected OKF scopes
remain authoritative. The driver rejects conflicting fixed baselines or zero-fold
ML overrides before execution; training selection requires at least two CV folds.

The driver runs an isolated baseline agent with only catalog lookup and
`freeze_hybrid_candidate`, saves the immutable candidate and checksum, and then
opens the graph-enabled proposal phase. The server derives baseline/addition
provenance from that record and validates mappings at proposal and task creation.
Use the driver-provided phase and schema; do not bypass validation or label this
condition as No Knowledge. A historical execution without this protocol requires
a new execution rather than a change to its recorded instructions.

## Domain focus

Keep the configured outcome central. General biomedical knowledge can motivate
predictors directly from their available definitions; graph evidence can propose
additional concepts, clarify mechanisms or expose limitations. Consider all
permitted graph regions without requiring a psychiatric, substance-use, medication
or other specialty in advance.

Select one coherent association. Complementary concepts must add a specific role
to it, not merely increase the feature count. Do not presume that graph augmentation
improves performance, that familiar variables must be selected or that every
graph-supported candidate contributes new information.

## Phase 1: General-knowledge candidate

This phase must run before the agent receives any retrieved OKF content. If graph
excerpts or graph-informed prior rationales are already in the context, report that
the initial candidate is not isolated and request a fresh phase from the driver.

### Using your own knowledge

Follow the original No Knowledge perspective when interpreting CSV definitions:

* Use general biomedical and clinical knowledge to assess relevance and propose
  a plausible mechanism, and label that reasoning as general knowledge.
* Do not cite specific papers, authors, DOIs, datasets or statistics in this phase.
* Distinguish what the feature definition states from what you infer it represents
  clinically. State uncertainty rather than treating an inference as a measurement.
* State whether the association is generally well established for the fixed outcome
  or tests something less established; disclose uncertainty about that distinction.

### Selecting predictors

Select an eligible, pre-outcome predictor set that tests one stated association.
Consider outcome and mechanism relevance, timing, definition clarity, direct
measurement versus proxy status, likely recording limitations and non-redundancy.
Include the features that association needs within the driver's active limits;
do not impose an arbitrary small set or add unrelated variables to increase its size.
If metadata cannot establish temporal eligibility, disclose that uncertainty and
follow the driver's timing policy instead of certifying the feature as pre-outcome.

1. Read the fixed study contract and supplied CSV predictor definitions. Use only
   the driver-permitted catalog tools; a preview is not the full catalog.
2. Identify an eligible predictor set for one outcome-relevant association. Explain
   the meaning, role, definition uncertainty and direct-measure or proxy status of
   every predictor. Include the predictors needed for that association within the
   active feature-count and comparison policy.
3. Label clinical reasoning as general model knowledge. State the expected direction
   or uncertainty, plausible alternatives and what would weaken the association.
   Do not invent citations, measurements, statistics or established effects.
4. Submit the candidate for the driver to freeze, including its exact columns,
   concept mappings and rationale. Wait for confirmation before graph retrieval.

Do not read documents, search the web, retrieve graph paths, inspect actual target
values, outcome cross-tabulations, model performance or reserved validation data,
or consult other pipelines' results in this phase. Do not copy feature sets from
historically high-scoring runs. If pipeline-local learning context is explicitly
supplied and permitted, identify the parent finding, proposed change and uncertainty
tested, and label the candidate as a result-informed follow-up. Graph-informed
feedback cannot be used while claiming an isolated model-knowledge candidate.

Exclude the target, direct outcome-derived proxies, identifiers, known post-outcome
information and unavailable measurements. If the definitions do not permit a valid
candidate, report the limitation. A basic candidate created here does not reproduce
the earlier No Knowledge model's measured score.

## Phase 2: Whole-graph augmentation

Begin with the frozen candidate supplied by the driver. Preserve its identity,
columns and original rationale. A later source that mentions an initial concept
does not retrospectively turn its original selection into graph-grounded discovery.

1. Inspect the selected OKF scope and search broadly for relationships relevant to
   the fixed outcome and the frozen concepts. Examine materially different graph
   regions when available; do not stop at the first familiar connection.
2. Read concrete instances and evidence. Seek a complementary measurement, treatment
   context, comorbidity, manifestation or other concept represented in the permitted
   CSV catalog. Explain what it could contribute beyond the frozen candidate.
3. Check exact mappings while searching. Distinguish an existing measurement from a
   weak proxy or unavailable concept. A semantic match is not clinical equivalence;
   do not complete an unsupported path with an invented measurement or relationship.
4. Propose one coherent augmentation set within the driver's search and total-feature
   budgets. It can contain complementary concepts, but distinguish genuinely
   additional information from redundant names, codes or duplicate representations.
5. Keep the frozen candidate alone as a valid comparison. If no defensible addition
   is available, report that outcome. Do not force an addition or rewrite the initial
   set to make the graph appear beneficial.

Only the driver may authorize a separate replacement or simplification candidate.
Do not silently remove a frozen predictor, broaden the outcome or exceed the
permitted feature budget. If additions would exceed that budget, report the constraint
and seek a driver-defined comparison rather than changing the baseline.

## Evidence and measurement rules

Keep provenance explicit for every predictor:

* General-knowledge predictors retain their original CSV definitions and clinical
  rationale without a fabricated graph source. Empty source references are allowed
  only when the hybrid driver explicitly permits them for this predictor group.
* Graph additions cite the actual selected sources and concrete paths read, and
  explain their mapping and incremental scientific rationale.
* General reasoning about a retrieved path remains an inference. Separate the source
  assertion from the untested step connecting it to the fixed HIV outcome.

Preserve edge direction and distinguish treatment, adverse effect, ISA, association,
co-mention and co-occurrence. Report evidence status as recorded. Predicted links are
unvalidated; observed edges, hub frequency and path counts are not causal evidence
or effect sizes. An HIV/AIDS endpoint does not establish an association with viral
detectability. Prescription indicators do not establish ingestion or adherence.

Preserve the configured target, labels, exclusions and timing requirements. If
prediction time or horizon is unspecified, state that limitation. Do not assume
measurements precede ART initiation. Exclude identifiers, the target, direct
outcome-derived proxies and known post-outcome information. Leave missing-value
handling, transformations, splitting, fitting and threshold selection to their
responsible stages under the study's policies.

## Comparison and selection

The hypothesis agent proposes candidates; the ML and evaluation stages measure
performance. Never claim that an addition helped before a valid comparison exists.

The driver evaluates the frozen candidate alone and that candidate plus the proposed
augmentation, using the same recorded split, training CV folds, model settings and
threshold. Training CV mean AUROC selects the expanded candidate only for a strict
improvement beyond 1e-12; otherwise it selects the baseline. Keep preprocessing within each training fold.
Separate the effect of additional predictors from other changes in the modeling
procedure. When the protocol includes a feature-count control, preserve that control
so improvement cannot be attributed to graph grounding merely because more variables
were supplied.

Choose using only the frozen training-partition validation rule. The original
candidate remains eligible when additions do not help. The chosen candidate is
refitted and explained, and its actual predictor list and both comparison results
are recorded with the selection receipt and reproducibility bundle.
The final test set must not select additions, parameters or thresholds. Prespecify
the main metric and report complementary discrimination, precision-recall,
threshold-dependent and calibration results when measured. A threshold adjustment
does not itself improve probability ranking. Selection within training does not
guarantee improvement on new data.

Treat follow-up design informed by prior exploratory results as exploratory. New
random splits of previously studied subjects do not by themselves establish an
independent replication. Do not promise superiority to No Knowledge or describe
predictive associations as clinical benefit.

## Output and recovery

Use only the phase-specific schema actually provided by the driver. Do not invent
new tool arguments or top-level fields. Within the supported fields, preserve:

* The fixed outcome and frozen candidate identity, exact predictors and rationale.
* The target column, positive and negative label meanings, and configured prediction
  time and horizon or their explicit absence.
* Each predictor, what the CSV records for it, what it is taken to represent,
  its direct-measure or proxy status, provenance class and role in the association.
* The Phase 1 rationale labeled as general knowledge, whether the association is
  well established or less established, its expected direction or uncertainty,
  alternative explanations and the empirical result that would weaken it.
* The proposed addition set, its real source/path evidence, exact CSV mappings,
  expected complementary contribution, redundancy risks and inferential limitations.
* Search coverage, alternatives examined and specific reasons to reject candidates.
* The unchanged initial candidate as a comparison, and the protocol-defined candidates
  passed to the downstream evaluation stage.

Where phase or arm metadata is supported, identify the frozen Phase 1 candidate as
a model-knowledge hypothesis with no retrieved evidence. Keep that label in the
supported metadata rather than rewriting the assigned question or hypothesis.
Identify Phase 2 additions separately as graph-grounded. Do not label the complete
hybrid execution as a No Knowledge control or retrospectively change Phase 1 provenance.

For graph paths actually relied upon, copy recorded source and path IDs into
`path_uses` where the hybrid schema requires them. Do not invent an ID, citation,
novelty score or evidence source for an initial general-knowledge predictor.

Inspect tool responses. Repair rejected mappings within the driver's same-Loop
recovery budget; a duplicate, empty or rejected proposal is not completed work.
Report an unsupported hybrid schema as a prerequisite failure, and a source or
measurement gap as such. Neither is permission to weaken validation. Keep explanations
concise while retaining the details needed to review the proposed comparison.
