# HIV — Integrated Clinical and Knowledge Perspectives

Develop a coherent, testable hypothesis for the fixed HIV outcome by combining
outcome-focused clinical reasoning, the available predictor definitions and
documented evidence across the selected OKF. Consider complementary perspectives
before selecting a candidate; do not commit to a specialty in advance.

## Domain focus

Use general biomedical knowledge to identify plausible relationships and interpret
what the dataset actually measures. Seek a clear relationship to the configured
outcome, rather than selecting predictors solely because they are prominent in a
graph. Label general-knowledge reasoning explicitly and distinguish it from
retrieved evidence. Do not invent publications, effects, statistics or citations.

Explore the following perspectives when supported by the selected sources and
eligible measurements:

* Immune status and clinical measurements: distinguish direct laboratory measures,
  derived quantities, diagnosis records and uncertain measurement definitions.
* Medication and treatment context: examine documented treatment, drug-class,
  shared-pharmacology and adverse-effect relationships. A prescription indicator
  does not establish ingestion, adherence, concurrent treatment or treatment failure.
* Psychiatric conditions: distinguish symptoms, diagnoses, medication indications
  and severity. Consider healthcare contact and documentation as alternative explanations.
* Substance use: distinguish exposure, a recorded disorder and treatment. A drug
  prescription alone does not establish active substance use or disorder severity.
* Shared manifestations and complications: consider supported symptom, hematologic,
  organ-system or comorbidity relationships that provide a materially different
  explanation of the outcome. Do not assume a shared manifestation has a shared cause.

These are search perspectives, not required feature groups. A single perspective
may yield the best answerable question; combine perspectives only when each adds
a specific, defensible role to the same association. Do not require one predictor
from every domain, select the union of all candidates or presume that a larger
feature set is better. Social or other concepts require actual source and measurement
support; a domain name does not make a measurement available.

## Evidence and execution contract

Follow the driver, frozen study contract and active scientific policy. Preserve the
configured outcome, labels, exclusions and timing requirements. The prediction time
or horizon may be unspecified; report that limitation and do not infer that a
measurement predates ART initiation or that the study validates prospective prediction.

Use only the supplied feature definitions and the OKF sources selected for this
pipeline. This is an integrated knowledge condition. It does not inherit the
No Knowledge condition's prohibition on retrieval or its permission to submit empty
source references. General knowledge guides candidate generation and interpretation;
the active knowledge-grounding requirements still govern predictor inclusion.

Under the current OKF driver, every selected predictor needs a justified mapping
to an assigned concept and a selected source actually read. Look for relevant
evidence for a clinically motivated candidate, and revise the candidate if that
evidence is unavailable. Do not attach an unrelated source to retain a favored
feature, fabricate a missing relationship or silently fall back to an ungrounded
question. A general-knowledge candidate without the required support remains an
unresolved idea, not an executable grounded hypothesis.

Separate what the source states from the inferential step connecting its concept
to the fixed outcome. An HIV/AIDS graph endpoint is not itself evidence about HIV
detectability. Preserve edge direction and distinguish treatment, adverse effect,
association, co-occurrence and ISA. Identify observed, predicted, mixed or unknown
evidence as recorded. Path counts, hub frequency and graph scores are not effect
sizes, independent replications or causal validation.

## Search and mapping procedure

1. Identify the assigned question-writing or answering stage. Inspect the fixed
   contract and available-feature context; during answering, begin with the assigned
   question and dataset description. Preserve the controller's assigned work.
2. Inspect the permitted predictor catalog and OKF scope using the available tools.
   A preview is not the complete catalog. Use catalog lookup and concept matching
   where needed, checking exact names, codes, definitions and missingness information.
3. Form a small shortlist of materially different candidate relationships. Include
   an outcome-focused clinical candidate and examine complementary domain perspectives
   when supported. Candidates may originate from clinical reasoning or a retrieved
   path. Neither origin exempts them from the same grounding and feasibility checks.
4. Retrieve concrete source instances and their evidence. Check feature availability
   while searching, rather than committing to a graph concept with no eligible
   measurement. Use a question catalog, when available, only as the driver permits
   for duplicate avoidance; do not retrieve other pipelines' outcomes or rationales.
5. Compare candidates on outcome relevance, directness of measurement, source quality,
   timing, redundancy, leakage risk and scientific informativeness. Consider whether
   an additional domain offers complementary information or merely another label
   for the same concept. Do not rank by expected AUC or source volume alone.
6. Select one coherent association. Explain the role of every predictor: the measured
   concept, its proposed relationship to the outcome and its contribution to this
   particular question. A demographic or clinical adjustment variable must satisfy
   the configured source and comparison policy; do not add a fixed baseline yourself.
7. Verify all exact column mappings. Distinguish a direct measure, defensible proxy
   and unavailable concept. Do not treat a high semantic similarity score as clinical
   equivalence. If an essential concept remains unmeasurable, revise the question
   rather than silently substituting a different condition or an unrelated proxy.

Respect the active original-column count, including an exact count when supplied.
Do not hard-code a preferred laboratory test, medication, feature count, model,
probability cutoff or class weight. Exclude the target, direct outcome-derived
proxies, identifiers and known post-outcome information. Keep distinct recorded
columns distinct unless the driver explicitly permits a prespecified transformation.
Leave extraction, imputation, encoding, splitting and fitting to their responsible
stages. Do not change the CSV or relax any missing-value or evaluation checks.

## Selection, feedback and recovery

Select predictors from permitted source evidence and feature definitions without
inspecting target values, outcome cross-tabulations, model performance or reserved
validation data. Do not copy historically successful feature sets from other
pipelines. Use prior findings only when the driver explicitly supplies and permits
them; record the parent finding, proposed change and uncertainty being tested.
Preserve the study's declared exploratory or confirmatory status. A perspective
designed after reviewing prior performance requires fresh evaluation before its
performance can support an independent confirmation claim.

Inspect tool responses and repair rejected evidence or mappings within the same
Loop and the driver's recovery budget. A rejected, duplicate or empty proposal is
not completed work. Report a specific evidence or measurement gap for regeneration
when necessary. Do not bypass validation, claim exhaustion after a partial search
or silently mark a failed analysis complete.

## Output

Use the assigned stage's existing question or task schema, without adding unsupported
top-level fields. During question writing, provide the required predictor concepts,
actual source IDs and OKF tags, rationale and exact proposed mappings. During
answering, preserve the assigned question and required hypothesis, use exact matched
columns and return the task ID from a successful task-creation call.

Within the supported rationale and mapping fields, state:

* The fixed outcome, selected association and expected direction or explicit uncertainty.
* Perspectives examined, materially different alternatives and why this candidate was chosen.
* Each predictor's exact column, meaning, direct-measure or proxy status and specific role.
* General-knowledge reasoning, retrieved source claims and the remaining inferential gaps,
  clearly distinguished from one another.
* Sources and concrete paths actually used, with their recorded evidence status.
* Timing, missingness, redundancy, treatment-indication, documentation and other relevant
  limitations; plausible alternative explanations; and findings that would weaken the hypothesis.

For each metapath relied upon, copy the source and recorded path IDs into `path_uses`
with a rationale specific to its use, as the driver requires. Cover every metapath
source used; do not list unused paths or invent an ID or novelty score. General
clinical plausibility, graph connectivity and predictive importance do not establish
causation, treatment benefit or clinical readiness. Keep the rationale concise while
retaining enough evidence and mapping detail for review.
