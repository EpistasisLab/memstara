# AddictionKB — Clinical frailty

Generate a testable outcome hypothesis to predict detectable HIV status after antiretroviral therapy (ART) initiation focused on clinical frailty, physiologic vulnerability or diminished reserve.

Frailty is a multidimensional clinical construct, not a synonym for age, disability, comorbidity count or any single laboratory abnormality. Validated frailty scores and phenotype assessments are rare or absent in the knowledge sources, so do not rely on finding one. Instead, look for the component features that frailty measures are usually built from, and assemble a defensible proxy from what is actually available.

## Finding frailty components

Search the available-feature context by domain, not by the word "frailty". The domains and examples below are illustrative, not exhaustive and not a checklist:

* Nutrition and body composition: for example, unintentional weight loss, low body mass, low serum protein markers, malnutrition or wasting diagnoses
* Physical function and mobility: for example, falls, gait or mobility diagnoses, use of mobility aids, rehabilitation referrals
* Physiologic reserve from routine labs and vitals: for example, anemia, reduced kidney function, liver injury or fibrosis markers, inflammatory markers, abnormal vital signs
* Cognition and mood: for example, cognitive impairment, delirium, depression
* Accumulated chronic disease burden: for example, multimorbidity, polypharmacy
* Dependency and social vulnerability: for example, care-dependency codes, home health services, unstable housing
* HIV-related contributors to reserve: for example, immune status, viral control, coinfections, duration of infection or treatment

Map each candidate feature to a domain and record its exact name and definition. Treat a recorded code or abnormal value as evidence of a deficit. Treat the absence of a record as missing, not as absence of the deficit, unless the feature definition supports that interpretation.

If a validated frailty measure does exist, use the components to suggest features/hypotheses.

## Using knowledge graph metapaths

The knowledge sources are AddictionKB metapaths serialized in open knowledge format (OKF). Frailty itself may be absent from the graph or present only as a sparse phenotype node. Expect most support to come through component concepts (for example, wasting, anemia, kidney or liver disease, falls, cognitive impairment) rather than through frailty directly. Before building a hypothesis:

* Search the selected metapaths for nodes that represent frailty components, not only nodes labeled as frailty, and map each to the domains above.
* Prefer metapaths where a component reaches the HIV outcome through an interpretable intermediate (for example, a component condition, then a shared pathway, drug or comorbidity, then the outcome) over paths that connect only through generic, highly connected hub nodes such as broad aging or inflammation terms.
* Distinguish mechanistic support from measurable support. A path through genes or pathways can justify why a component matters, but the hypothesis still needs features in the dataset that represent the component itself.
* Check drug-related paths for treatment exposure (for example, antiretroviral toxicity or polypharmacy), which may explain a component-outcome link better than frailty does.
* Cite the metapath pattern (the node and edge type sequence), the specific path instances read, and their document IDs.
* Report edge provenance and evidence type from the source metadata (for example, curated association, literature-derived co-mention, or record-derived co-occurrence). Treat co-mention and co-occurrence edges as weak support.
* Path existence and path counts reflect how densely a topic was curated, not effect size or strength of evidence. One well-sourced path can outweigh many paths through hubs.
* If the graph supports only one or two components, state that. Do not present component-level support as evidence for frailty as a whole.
* Record-derived edges may come from populations or coding practices unlike the current dataset. Note this when relying on them.

## Evidence and alternative explanations

Inspect the selected knowledge sources for HIV-relevant frailty evidence, including evidence on individual components, and cite only documents and graph paths actually read. Consider these alternative explanations:

* Reverse causation and underlying disease severity
* Treatment exposure
* Age: frailty proxies track age closely, so state what the proxy adds beyond age
* Healthcare utilization: patients seen more often accumulate more codes and labs, which inflates deficit counts independent of true frailty
* Missingness, including differential testing across patient groups

## Output

Verify exact predictor mappings against the available-feature context before proposing the question. If the dataset cannot support either a multi-domain proxy or a defensible component-level hypothesis, report insufficient measurement rather than fabricating one. Use the existing question and hypothesis schemas and state:

* The proposed association
* Each component feature and the domain it represents
* Domains that could not be covered
* Supporting evidence: metapath patterns, path instances and document IDs read, with edge evidence type
* Measurement limitations
* Plausible confounding
* What would weaken the hypothesis
