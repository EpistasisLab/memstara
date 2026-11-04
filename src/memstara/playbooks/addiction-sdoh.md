# HIV knowledge sources — Social determinants of health

Generate a testable hypothesis linking social determinants of health to predict detectable HIV status after antiretroviral therapy (ART) initiation. Make missing measurements and proxies explicit.

## Domain focus

Focus on social determinants of health (SDOH) supported by the selected sources, such as housing, economic circumstances, social support or access to care. SDOH are rarely recorded as direct, validated measures in clinical data, and they may be sparsely represented in the knowledge graph. Do not assume either source covers them. Check the graph evidence and the feature context before committing to a concept. If no defensible mapping exists, choose another supported SDOH concept or report insufficient data rather than inventing social measurements. Frame results as contextual associations with the fixed outcome, not individual blame.

## Choosing evidence from the selected sources

The selected bundle may contain AddictionKB graph evidence, HIV suppression literature, or both. Discover the actual domains with the knowledge tools. In a combined bundle, `addiction-kb` contains graph documents and `hiv-suppression` contains literature. Search the latter for social-structural determinants and care-engagement evidence without graph-only filters. Absence of an SDOH graph branch does not establish absence of SDOH literature.

For a literature-supported hypothesis, cite the full document ID and its PMID, study design, measured exposure, outcome and limitations. A paper-based association does not require a graph path. Never describe a paper as an AddictionKB metapath or invent nodes and edges. Graph and literature can complement each other, but distinguish their provenance and do not count the same underlying evidence twice. The feature-mapping and fixed-outcome requirements below still apply; a paper cannot supply missing CSV measurements.

## Using knowledge graph metapaths (when relying on graph evidence)

The knowledge sources are Addiction KB metapaths serialized in open knowledge format (OKF). The graph is built mainly around biomedical entities, so social concepts may appear as only a few node types, as node attributes, or not at all. Before building a hypothesis:

* Identify which node types in the selected metapaths can represent a social concept (for example, an exposure, behavior, environmental or clinical-code node) and which cannot.
* Prefer metapaths where the social concept reaches the outcome through an interpretable intermediate (for example, social exposure, then a behavior or condition, then the outcome) over paths that connect only through generic, highly connected hub nodes.
* Cite the metapath pattern (the node and edge type sequence), the specific path instances read, and their document IDs.
* Report edge provenance and evidence type from the source metadata (for example, curated association, literature-derived co-mention, or record-derived co-occurrence). Treat co-mention and co-occurrence edges as weak support.
* Path existence and path counts reflect how densely a topic was curated, not effect size or strength of evidence. One well-sourced path can outweigh many paths through hubs.
* If the only paths linking a social concept to the outcome run through entities that do not represent the proposed social mechanism, state that the graph does not support the mechanism. Do not repurpose those paths as support.
* Record-derived edges may come from populations or coding practices unlike the current dataset. Note this when relying on them.

## Finding SDOH features

Search the available-feature context by domain, not by the phrase "social determinants". The domains and examples below are illustrative, not exhaustive and not a checklist:

* Housing: for example, homelessness or housing-instability codes, shelter or temporary addresses
* Economic circumstances: for example, insurance or payer type and changes, employment or financial-hardship codes
* Social support: for example, documented living situation, social isolation codes, caregiver presence
* Access to care: for example, travel distance, interpreter need, missed appointments, gaps in care, primary care attachment
* Education and literacy: for example, educational attainment or health literacy flags
* Legal and justice involvement: for example, incarceration-related codes
* Neighborhood and environment: for example, area-level indices linked by geography

For each candidate, state what it actually measures and where it falls short. An administrative code, service utilization pattern or diagnosis is not automatically a valid measure of deprivation, adherence or access. Common limitations include:

* Social-need codes are documented inconsistently, usually only when someone screens for them. Their presence reflects screening and documentation practice as much as need. Treat absence as missing, not as absence of the need.
* Area-level measures describe a place, not the person. Do not interpret them as an individual's circumstances.
* Utilization-based proxies (for example, missed visits or care gaps) are entangled with illness severity, substance use itself and health-system factors.
* Payer type mixes income, age, disability and employment. It is not a clean economic measure.
* Do not use race, ethnicity or language as stand-ins for social disadvantage. If they are included, treat them as distinct variables and justify their role.

## Timing and reverse causation

Several social circumstances can be consequences of substance use as well as causes (for example, housing loss, job loss or justice involvement). Use only features recorded before the prediction time, and state whether the proposed direction is plausible given the timing. If a social feature could be downstream of the outcome process, name that explicitly as an alternative explanation.

## Evidence and execution contract

Use only the OKF documents actually available through this pipeline's selected knowledge sources. Inspect source metadata and cite the document IDs, with specific paths for graph evidence or PMIDs and study details for literature evidence. Do not invent an Addiction KB provenance, node, edge, metapath, publication, source-filter value or column. A domain skill is a research focus, not a replacement for the knowledge source selection or an enforced corpus filter. If selected sources do not support this domain, explain the gap rather than silently claiming support or bypassing the configured source scope.

Before proposing a question, inspect the supplied available-feature context and use the existing feature-mapping tools to confirm plausible predictor mappings. Preserve the fixed outcome supplied by the pipeline in both question and hypothesis. Never use that outcome or a direct outcome-derived proxy as a predictor. Do not change the outcome to an easier target or request unavailable data as though it existed.

Start with a knowledge-grounded, testable association and a justified feature set. Include complementary available predictors when they test the stated mechanism; do not limit the hypothesis arbitrarily to two features or add unrelated variables merely to increase the feature count. Distinguish measured concepts from imperfect proxies, confounders, documentation patterns and missing concepts. The data agent extracts columns; this MVP does not clean or impute the input dataset.

Follow the active pipeline's scientific policy. On the first Loop, use knowledge and available feature definitions. On later Loops, when pipeline-local learning context is provided, state the parent finding, what changes, and the uncertainty this refinement tests. Label previous-result-informed refinements explicitly; never call them independent knowledge-only discoveries. Do not silently discard a justified feature because one previous importance value was negative. Do not access other pipelines' memory or reserved validation outcomes to tune a question.

## Output

Use the existing question/hypothesis output schema. Within its rationale or answer, record:

* The domain focus and the social concept targeted
* Document IDs and source type; for graph evidence, metapath patterns, path instances and edge evidence type; for literature, PMIDs, study design and measured exposures
* The fixed outcome
* Each mapped predictor, the concept it stands for, and whether it is a direct measure or a proxy
* Documentation, selection and area-level biases that apply
* Expected association and its direction
* Alternative explanations, including reverse causation
* What would weaken the hypothesis

A predictive association is not a causal effect. Prioritize an informative feasible experiment, not a promised AUC or a claim of clinical readiness. If no supported, answerable candidate exists, report that limitation through the existing workflow.
