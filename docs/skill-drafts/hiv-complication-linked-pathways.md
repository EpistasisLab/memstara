# HIV — Complication-Linked Pathways

Develop a hypothesis for the fixed HIV outcome from specific documented complication anchors and measurable clinical relationships.

## Domain focus

Start from a supported HIV-related complication anchor, rather than treating all
comorbidities as consequences of HIV. Relevant anchors may include anemia, cardiomyopathy
or seborrheic dermatitis when the selected sources contain them. Keep one coherent
complication-centered question and state what it adds beyond medication-led or anemia-led
questions; overlapping evidence alone does not create a distinct hypothesis.

## Domain-specific search strategy

* Identify the specific HIV-related anchor, any ISA generalization, intermediate entities
  and the terminal concept. Compare supported anchors or materially different relations.
  Explain which part of the path remains specific to HIV and where specificity is lost.
* Distinguish co-occurrence, association, treatment and adverse-effect relationships.
  A generic disease code does not establish HIV attribution, onset, severity or causation.
  Do not describe any available comorbidity as an HIV complication without source support.
* Verify measurable intermediate concepts as well as the anchor. A cardiomyopathy diagnosis
  does not make a missing drug exposure observable; do not silently discard an essential
  intermediate or substitute another medication to complete the path.
* Map diagnostic scope explicitly: a broad cardiomyopathy, dermatitis or pneumonia record
  may not identify the graph's specific subtype, etiology or HIV-associated condition.
  Name the recorded phenotype accurately and narrow the question accordingly. If this
  changes its essential premise, regenerate rather than relabel an unsupported mapping.
* Treat shared anatomy as localization context, not proof of a common mechanism. An immune
  or nervous-system node does not independently justify any laboratory or diagnosis column
  associated with that system.
* Prefer paths with a coherent measurable relationship over broad complication burden.
  Do not invent severity scores, condition counts or infection subtypes. Consider underlying
  illness, ascertainment, treatment indication and timing as alternatives, and distinguish
  an association with recorded diagnoses from progression or a complication's causal effect.

## Evidence and execution contract

Use only the AddictionKB-derived OKF sources selected for this pipeline and the supplied
dataset feature definitions. This skill defines a research perspective, not an enforced
corpus filter or permission to access another study. The driver, frozen study contract
and active scientific policy take precedence over this skill.

Preserve the configured outcome, labels, prediction time and exclusions. Graph endpoints
are evidence about candidate predictors; they must not replace the outcome. If the source
metadata does not establish timing, state that limitation. Do not assume measurements
precede ART initiation or describe a cross-sectional association as prospective prediction.

Read concrete instances and their evidence, including linked shards when needed. Record
the metapath's node and edge sequence, exact instances, source IDs and available provenance.
Preserve edge direction and distinguish treatment, adverse effect, association and ISA.
Prefer observed paths for primary hypotheses; identify predicted or mixed evidence explicitly
as unvalidated. An observed edge remains a source-graph assertion. Path counts, hub frequency
and DWPC scores are not effect sizes, independent replications or clinical validation.
Separate a documented path from the untested inference connecting it to the fixed outcome.
Do not invent a missing link, publication, filter, source ID or path ID.

## Search and mapping procedure

1. Identify the assigned stage from the driver and available tools. During question writing,
   inspect available domains, use the question catalog only to avoid duplicates, and retrieve
   relevant sources. During answering, begin with the dataset description and assigned
   question, then inspect the supporting sources. Do not create work for an unassigned question.
2. Follow the domain-specific search strategy. Compare materially different candidates
   when the evidence permits; changing wording around the same concepts is not a new candidate.
   Check feature feasibility while searching, before committing to a question.
3. Inspect the complete permitted predictor catalog as needed. A preview is not the full
   catalog. Use the provided catalog lookup or context tools for omitted entries and the
   available matching tools to verify concepts. Read all plausible matches; rank or semantic
   similarity alone does not establish clinical equivalence.
4. Match concrete entities, not relation names or broad path families. Preserve exact column
   spelling, codes and definitions. For every essential concept, explain its correspondence
   to a real eligible predictor and any definition mismatch. A defensible proxy must be
   named for what it measures; an unavailable concept cannot be silently replaced.
5. Respect the active original-column count and comparison policy, including an exact count
   when supplied. Do not hard-code a count, pad with unrelated predictors, invent a derived
   feature or add a fixed baseline yourself. Exclude identifiers, the outcome, direct
   outcome-derived proxies and known post-outcome information.
6. Leave extraction, imputation, encoding and modeling to their responsible stages under the
   configured policies. Do not edit the CSV or relax missing-value, splitting or evaluation
   checks. Existing columns may still have substantial missingness.

## Selection, feedback and recovery

Prefer answerable candidates with specific evidence, direct measurements and a clear reason
for considering the fixed outcome. Explain competing mechanisms, documentation effects and
temporal uncertainty. Choose for scientific informativeness, not a promised AUC. A result
can weaken a hypothesis without proving the source graph wrong.

Use prior results only when the driver explicitly supplies and permits them. Identify the
parent finding, proposed change and uncertainty being tested; retain supported concepts
unless there is a reasoned change. Negative SHAP or permutation importance alone does not
establish biological irrelevance. Do not seek other pipelines' memory, outcome cross-tabulations
or reserved validation results to select features.

Inspect tool responses. Repair a rejected mapping or propose a different supported candidate
within the same Loop and the driver's recovery budget. A duplicate, rejected or empty proposal
is not completed work. If an essential concept remains unmeasurable, report the attempted
mapping and specific obstacle for regeneration. Do not claim corpus exhaustion after a partial
search, bypass validation, or silently mark a failed Loop complete.

## Output

Use the stage's existing schema; do not add a new top-level report format. In question
writing, supply the required predictor concepts, actual OKF tags and rationale; add lineage
fields only as instructed. In answering, preserve the assigned question and required hypothesis,
copy exact matched columns, and return the task ID reported by a successful task-creation call.

Within the supported rationale and mapping fields, report:

* The domain-specific hypothesis, fixed outcome and expected direction, or explicit uncertainty.
* Search coverage, material alternatives and the reason for selecting this candidate.
* Sources and specific path instances actually read, their evidence status and the remaining
  inferential gap to the outcome.
* Exact predictor mappings, direct measures versus proxies, and essential unavailable concepts.
* Alternative explanations, timing and measurement limitations, and findings that would weaken
  the hypothesis.

When the driver exposes recorded path provenance and requests attribution, copy source and
path IDs into `path_uses` with a use-specific rationale. Include only paths actually used and
cover the metapath sources relied upon. Never manufacture an ID or novelty score. Graph
connectivity, predictive importance and statistical association do not establish causation,
a treatment effect or clinical readiness.
