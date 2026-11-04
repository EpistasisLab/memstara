# AddictionKB — Psychiatric or substance use disorders

Generate a testable outcome hypothesis to predict detectable HIV status after antiretroviral therapy (ART) initiation from either the psychiatric-disorder domain or the substance-use-disorder domain.

## Scope: either domain, or both together

Three kinds of candidate are eligible:

* A psychiatric disorder alone
* A substance use disorder alone
* A co-occurrence or interaction between a psychiatric disorder and a substance use disorder, when the selected sources support it

Do not require both domains to be present, and do not default to describing every candidate as comorbidity or dual diagnosis. Equally, do not rule out a co-occurrence hypothesis when the evidence supports one. Search both domains, and the paths connecting them, before choosing, so that no option is silently ignored because it appears first or has more documents.

For co-occurrence candidates:

* Distinguish evidence that the disorders co-occur from evidence that their co-occurrence changes the outcome. A paper reporting that two disorders often appear together supports including both, but does not by itself show a joint effect on the HIV outcome.
* State the expected form of the joint relationship: each disorder contributing independently, or the combination carrying more (or less) risk than the parts would suggest.
* Map each disorder to its own features. Express the co-occurrence as both mapped features plus the expected joint relationship, rather than constructing a new combined indicator, unless the available data already provides one or the pipeline supports derived features.
* Require both components to be recorded within the same lookback window before the prediction time.

## Using knowledge graph metapaths

The knowledge sources are AddictionKB metapaths serialized in open knowledge format (OKF). AddictionKB is built around addiction, so expect substance-use concepts to be more densely connected than psychiatric concepts. Higher density there reflects how the graph was built, not stronger evidence. When reading paths:

* Search both domains explicitly and record which metapath patterns were examined in each, including patterns that link psychiatric and substance-use concepts to each other.
* Watch for drug nodes with more than one role. The same compound can be a substance of misuse, a treatment for a substance use disorder, a psychiatric medication or a pain medication. State which role a path relies on.
* Check drug paths for interactions with HIV treatment (for example, metabolic interactions or overlapping side effects), which may explain a link better than the disorder itself.
* Prefer metapaths where a disorder reaches the outcome through an interpretable intermediate (for example, a behavior, a treatment exposure or a comorbidity) over paths that connect only through generic, highly connected hub nodes such as broadly studied neurotransmitter genes.
* Distinguish mechanistic support from measurable support. A path through genes or pathways can justify why a disorder matters, but the hypothesis still needs features in the dataset that represent it.
* Cite the metapath pattern (the node and edge type sequence), the specific path instances read, and their document IDs.
* Report edge provenance and evidence type from the source metadata (for example, curated association, literature-derived co-mention, or record-derived co-occurrence). Treat co-mention and co-occurrence edges as weak support.
* Path existence and path counts reflect how densely a topic was curated, not effect size or strength of evidence.
* Record-derived edges may come from populations or coding practices unlike the current dataset. Note this when relying on them.

## Finding features

Search the available-feature context by concept, not only by diagnosis name. The examples below are illustrative, not exhaustive and not a checklist.

Within the psychiatric domain, distinguish:

* Symptoms: for example, screening scores, symptom codes, documented mood or sleep complaints
* Diagnoses: for example, diagnosis codes from outpatient, inpatient or emergency encounters
* Treatment indications and medication exposures: for example, psychiatric medication orders or fills
* Care contact: for example, psychiatric admissions or behavioral health visits

Within the substance-use domain, distinguish:

* Exposure: for example, toxicology results or documented use in social history
* Diagnosed disorder: for example, substance use disorder codes
* Severity: for example, overdose or withdrawal events, or severity specifiers
* Treatment: for example, medications for a substance use disorder or treatment program enrollment
* Remission: for example, remission specifiers or sustained negative toxicology

Do not infer an active disorder from a medication, diagnosis code or shared symptom alone. Common limitations include:

* Many psychiatric and pain medications are used for several indications, so an exposure does not identify the disorder.
* Diagnosis codes often carry forward from problem lists. A recorded code may describe a past disorder rather than a current one.
* Toxicology tests are usually ordered selectively, so results reflect who was tested. Treat an untested patient as missing, not negative.
* Social history fields are often templated or outdated.
* Some symptoms overlap with HIV disease or its treatment (for example, fatigue, cognitive changes or sleep disturbance, or neuropsychiatric side effects of some antiretrovirals). Consider these before attributing a symptom to a psychiatric disorder.
* Substance use can produce psychiatric symptoms, and psychiatric symptoms can be coded during intoxication or withdrawal. This matters most for co-occurrence candidates.

Use only features recorded before the prediction time.

## Alternative explanations

Account for these as plausible alternative explanations:

* Temporality, including reverse causation from HIV diagnosis or progression to psychiatric symptoms or substance use
* Healthcare-contact patterns: patients seen more often are more likely to be screened, tested and coded, which also inflates apparent co-occurrence
* Treatment indication: a treated disorder may differ from an untreated one in severity and care engagement
* Severity
* Ascertainment, including differential screening across patient groups

Frame results as associations with the fixed outcome, not as blame directed at patients with these disorders.

## Evidence and execution contract

Use only the selected knowledge sources and cite the OKF documents and graph paths actually inspected. A graph connection is hypothesis-generating evidence, not proof of causality. If neither domain has adequate evidence or a defensible mapping to available predictors, report that limitation instead of inventing support.

Inspect the available-feature context before proposing a question and verify exact predictor mappings with the provided tools. Preserve the pipeline's fixed HIV outcome; never substitute a psychiatric or substance-use endpoint for it. Exclude the outcome, outcome-derived proxies and information unavailable at prediction time. State whether the selected candidate came from the psychiatric domain, the substance-use domain, or a supported co-occurrence of the two.

## Output

Use the existing question and hypothesis schemas and record:

* The candidate type (psychiatric, substance use, or co-occurrence), and the patterns examined for the types not chosen
* Metapath patterns, path instances and document IDs read, with edge evidence type
* Mapped predictors, and whether each represents a symptom, diagnosis, exposure, severity, treatment or remission
* For co-occurrence candidates, whether the evidence shows co-occurrence only or a joint effect on the outcome, and the expected form of the joint relationship
* The expected association and its direction
* Proxy limitations
* Alternative explanations
* What would weaken the hypothesis

Frame the result as a testable predictive association, not a causal claim or a promise of clinical utility.
