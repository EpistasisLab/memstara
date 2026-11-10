# HIV — Medication and Treatment Pathways

Generate a testable, medication-centered outcome hypothesis to predict detectable HIV status after antiretroviral therapy (ART) initiation using the fixed study contract, the selected AddictionKB-derived OKF and the supplied dataset feature definitions.

Start from a documented drug relationship and keep at least one directly mapped, path-supported medication predictor central to the hypothesis. Complementary diagnoses, symptoms or laboratory measurements should test the same association. Follow the driver's permitted sources, fixed outcome and scientific policy.

## OKF-only evidence boundary

Use only the selected OKF actually retrieved in this execution as biomedical knowledge for question generation and hypothesis mapping. Do not use pre-trained or general biomedical knowledge, remembered literature, web sources or other agents’ unsupported claims to introduce predictor concepts, relationships, mechanisms, covariates or explanations. This restriction also applies to familiar HIV markers, medications and demographic predictors.

Before including a concept in a question, identify its explicit supporting passage, named entity or concrete path instance in the retrieved OKF. Record the exact source ID and the relevant evidence in the existing rationale and mapping fields.
Use CSV definitions and the semantic matcher only to map OKF-supported concepts to eligible original columns.
Apply this boundary to every predictor. Familiarity, a feature-count minimum or prior predictive performance cannot replace OKF support. For example, do not add predictors from domain context or knowledge alone. All predictors require explicit support in the retrieved OKF.

The fixed study contract still defines the target, eligibility and evaluation rules. It does not supply missing biomedical evidence. This boundary governs all domain examples and selection advice below; none grants an exception.

## Using knowledge graph metapaths

The knowledge sources are AddictionKB metapaths serialized in open knowledge format (OKF). A metapath describes a sequence of node and edge types; a path instance names the specific entities following that pattern. When reading them:

* Inspect available categories and supported filters. Prioritize the `treatment-toxicity` and `drug-class-effect` mechanism families; use `shared-pharmacology` as secondary context. These are path families, not edge types. Open schema documents and follow links to concrete instances, including child evidence documents.
* Preserve relation types and directions, such as `DRUGTREATSDISEASE`, `DRUGCAUSESEFFECT`, `DRUGINCLASS` and `ISA`. Traversing an edge backwards does not reverse its meaning. Treatment, adverse-effect annotation, class membership and subtype relationships are different claims.
* Cite the metapath pattern, specific instances read and document IDs. Consult both schema and evidence documents where needed. A summary count or shared class does not establish a drug-specific relationship, interaction or effect across every class member.
* Prefer observed paths. `observed` means edges occur in the source graph, not that an adverse reaction occurred in this cohort or was clinically validated. Label predicted or mixed paths as unvalidated. Report only recorded provenance; do not invent publications or evidence types.
* Check `knowledge_provenance.status` and `diagnostics`. If metadata and text conflict, report `unknown` and the conflict; do not choose the more favorable label or infer status from a folder name. Seek consistent evidence before making a stronger claim.
* Distinguish the graph's HIV-related and psychiatric or substance-use anchors from the fixed detectable-HIV outcome. Explain the remaining inference to that outcome. Do not invent adherence, treatment-failure or temporal links.
* Path counts, repeated instances through one drug, hub frequency and DWPC scores are not effect sizes, independent replications or clinical validation. Compare materially different drugs or relationships when supported.

## Selecting predictors

Select eligible predictors that test one stated association. Check feature availability while exploring paths, before committing to a candidate. Consider:

* Relevance: map concrete drug or clinical entities, not relation names or path families. Check the permitted feature catalog and matching tools, inspect plausible matches and preserve exact column names. A preview or similarity ranking does not establish a valid mapping.
* Identity: distinguish ingredient, salt, formulation, brand and combination product. Verify equivalence before substitution. Overlapping indicators are not automatically independent exposures. For class hypotheses, identify measurable member drugs without generalizing their coverage or effects to the whole class.
* Measurement: a medication indicator records a drug, not necessarily ingestion, current use, dose, duration, adherence or indication. Multiple indicators do not establish a simultaneous regimen. Explain direct measurements, defensible proxies and definition mismatches.
* Timing: require predictors to be available by the configured prediction time. If timing cannot be established, disclose the limitation and follow eligibility rules; do not assume observations precede ART initiation or claim prospective prediction.
* Alternatives: consider indication, disease severity, treatment era, healthcare contact and recording practices. Separate adverse-effect plausibility from a documented adverse reaction in this cohort.

Choose an informative, feasible candidate rather than a promised AUC. Respect the driver's feature count and comparison policy; do not pad with unrelated variables or add a baseline yourself. Report unmeasurable essential concepts for regeneration through the existing workflow.

## Exclusions

Do not use the target, direct outcome-derived proxies, identifiers, post-outcome information or unavailable measurements. Do not inspect outcome values, reserved validation data or other pipelines' results to select predictors. Do not edit the CSV, invent derived features or change missing-value, splitting or evaluation policies.

On later Loops, use prior results only when supplied and permitted by the driver. State the parent finding, proposed change and uncertainty being tested. Label the refinement as informed by previous results. Negative SHAP or permutation importance alone does not establish biological irrelevance.

## Output

Use the existing question and hypothesis schemas for the assigned stage and state:

* The fixed outcome and proposed association, including expected direction or explicit uncertainty
* Each predictor, its exact column, what it records and whether it is a direct measure or a proxy
* Metapath patterns, specific instances and document IDs actually read
* Evidence status, provenance limitations and the inferential gap to the outcome
* Material alternatives considered and the reason for selecting this candidate
* Measurement and timing limitations, alternative explanations and what would weaken the hypothesis

When submitting the hypothesis through `create_task`, attribute used paths in `path_uses`: supply `source_id` (the document ID), the exact `path_id` returned in `okf_read`'s `knowledge_provenance.paths`, and a use-specific `rationale`. Cover the metapath sources relied upon. Schema IDs, concept IDs and manually inferred row numbers cannot substitute for returned path IDs.

If a cited document exposes no path IDs, cite its actual instance in the rationale and report unavailable structured attribution. Follow the driver's validation and recovery policy; do not fabricate IDs, claim complete attribution or invent a novelty score. An empty path-ID list alone does not mean the document contains no graph paths.

A graph-supported predictive association is not a causal effect, treatment recommendation or claim of clinical readiness. Report unsupported candidates through the existing regeneration workflow; a rejected or empty proposal is not completed work.
