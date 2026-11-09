# HIV — Whole Knowledge Graph: Integrated Predictors (V3)

Develop a testable, integrated predictor hypothesis for the fixed HIV outcome under the supplied study contract. Search across the selected AddictionKB-derived OKF and combine complementary, measurable information from different relevant graph regions into one predictor set. Use the supplied CSV feature definitions to establish what can actually be measured.

The objective is joint prediction of the same outcome using multiple supported clinical dimensions. A single question can encompass several mechanisms; it need not be restricted to one specialty, one metapath or one narrow association. Select **4–20 distinct original CSV predictor columns**, excluding the target, under the existing driver policy. The range is a constraint, not a request to select either endpoint.

## Using knowledge graph metapaths

The knowledge sources are AddictionKB metapaths serialized in open knowledge format (OKF). A metapath describes a sequence of node and edge types; a path instance names the entities following that pattern. When reading them:

* Cite the metapath pattern, specific instances actually read and source document IDs. Preserve relation types and directions; traversing an edge backwards does not reverse its meaning.
* Distinguish treatment, adverse-effect annotation, class membership and subtype relationships. Read concrete instances and evidence rather than relying on titles, schema patterns or summary counts alone.
* Report recorded provenance and evidence type. Treat co-mention and co-occurrence as weak support. An observed graph edge is not proof of a relationship in this cohort; label predicted or mixed paths as unvalidated. Report conflicting or absent provenance as uncertain.
* Separate the retrieved relationship from the reasoning connecting a predictor to the fixed HIV outcome. A path need not terminate at the exact dataset target, but the inferential gap must be explicit. Never invent an adherence, temporal or causal edge.
* Different predictor groups may be supported by different paths. They do not need to lie on one connected path or have documented edges between every pair. Explain each group's relevance to the shared outcome; do not claim an interaction or synergy merely because the groups are combined.
* Path counts, hub frequency and repeated instances are not effect sizes or independent replications. A gene or pathway can support a mechanism without being a measurable CSV predictor.

## Search procedure

1. Inspect the supplied target contract, eligible feature catalog and available OKF scope. Retrieve omitted catalog sections when needed; a preview is not the full catalog. Do not infer unprovided prediction timing or change the target.
2. Explore distinct graph regions without a preselected specialty filter. Medication and treatment, psychiatric conditions, substance use, immune measures and comorbidities are possible directions, not mandatory categories or claims that the source contains them.
3. Check CSV availability during exploration. Use both graph-to-feature mapping and searches for graph support for eligible CSV concepts. Feature availability alone does not establish relevance or OKF support.
4. Build a shared candidate pool across the regions examined. Retain complementary, supported predictors from multiple regions instead of choosing one region and discarding the others. Verify exact column meanings, clinical synonyms, measurement limitations and supporting instances.
5. Assemble one integrated set using the criteria below. Compare the information contributed by candidate groups and retain useful breadth within the 4–20-column budget. Do not stop because four acceptable columns have been found or because the first coherent mechanism has been mapped.
6. Before proposing the question, ensure that its predictor concepts cover the intended integrated set. Describe the joint prediction question across those concepts, using the existing schema. The later mapping stage must not have to add unassigned concepts to achieve the intended breadth.

Inspect several distinct regions when available, but do not require every category to contribute a predictor. Keep retrieval focused on unresolved evidence or mappings and respect the driver's tool and recovery budgets. Report the scope actually inspected rather than claiming an exhaustive review of every graph document or CSV column.

## Biases to correct for

* Hub and evidence-density bias: a richly documented region should not crowd out other supported clinical dimensions solely because it has more paths.
* Familiarity bias: do not stop with familiar predictors when other relevant, measurable regions remain to be considered. Established predictors remain eligible when justified; novelty alone is not a selection criterion.
* Narrow-question bias: write the integrated question during question generation. Selecting one narrow question first and expanding only during mapping conflicts with the assigned-question contract.
* Minimum-count bias: interpret a preference for high-confidence mappings as a quality requirement, not a preference for the smallest possible model. Keep additional well-supported, complementary predictors when space permits.
* Coverage bias: do not add weak proxies or unrelated columns merely to represent another category or reach 20 features. If only one region is defensible, explain the limitation rather than inventing breadth.

## Selection criteria

Choose the set by weighing:

* **Outcome relevance and support:** every selected predictor has a defensible mapping to retrieved OKF evidence and an explicit rationale connecting it to the fixed outcome. General knowledge may explain that reasoning but must not be presented as retrieved evidence.
* **Complementarity:** include different clinically relevant dimensions when they plausibly contribute distinct information. Multiple mechanisms can support one integrated predictive hypothesis. Expected incremental value is a hypothesis, not an established performance gain.
* **Measurement and redundancy:** preserve exact original column names. Distinguish direct measurements from proxies, and ingredient, brand and combination-product indicators from independent exposures. Avoid redundant representations unless their separate information is justified.
* **Eligibility and timing:** follow the study contract. Exclude the target, target-derived proxies, identifiers, unavailable measurements and known post-outcome information. An HIV-related graph node or a medication/comorbidity label alone does not establish leakage. If timing is unspecified and exploratory classification is permitted, disclose the uncertainty rather than claiming prospective prediction or automatically excluding those categories.
* **Count and data quality:** retain 4–20 distinct original predictors before encoding. If more than 20 qualify, prioritize evidence quality, measurement clarity and complementary coverage. If fewer than four qualify, seek additional supported concepts through the existing regeneration workflow. Preserve the approved missing-value policy; do not fill values yourself, remove rows or change the eligibility pool.

Use a smaller set when additional candidates are unsupported, redundant or ineligible, not merely because a compact hypothesis is easier to explain. State why the final count was chosen. Do not add an automatic baseline, engineer new columns or ask the ML agent to select additional features.

Do not inspect outcome associations, held-out results or other pipelines' performance to select predictors. Use earlier results only when explicitly supplied and permitted by the driver, and label any resulting refinement. Preserve splitting, seeds, evaluation and recovery policies. This skill does not promise better performance than No Knowledge or any other skill.

## Output

Use the existing question and hypothesis schemas and state:

* The fixed outcome and integrated joint prediction hypothesis
* The graph regions examined, their candidate groups and any coverage limitations
* Each selected column, its assigned predictor concept, what it measures and whether it is a direct measure or proxy
* The supporting source, metapath instance and the remaining inference to the outcome for each predictor or group
* How the groups complement one another, plausible association directions and material alternative explanations
* The final original-column count, why it is appropriate and why major alternatives were excluded
* What would weaken the integrated hypothesis, including measurement, provenance and timing uncertainties

At question generation, include all intended concepts in `predictor_concepts` and cite the sources used. At hypothesis mapping, preserve the assigned question and cover every assigned concept and selected column in `feature_mapping`. If an essential mapping fails, report it for same-Loop regeneration; do not silently substitute a narrower question or unrelated variables.

When calling `create_task`, attribute metapaths in `path_uses` with the document `source_id`, the exact `path_id` returned in `okf_read`'s `knowledge_provenance.paths`, and a use-specific `rationale`. Do not substitute inferred row numbers, schema IDs or invented paths. If structured path IDs are unavailable, report that limitation and follow the driver's validation requirements.

A combined predictor set is a hypothesis for empirical evaluation, not causal proof or a clinical recommendation. Report uncertainty honestly and preserve the driver's validation checks.
