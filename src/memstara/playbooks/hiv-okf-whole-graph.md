# AddictionKB — Unbiased search of whole knowledge graph OKF

Search the entire OKF knowledge scope available to this HIV pipeline without choosing a clinical category in advance to develop a testable outcome hypothesis to predict detectable HIV status after antiretroviral therapy (ART) initiation. Here, unbiased means no preselected specialty or subdomain filter. It does not mean that the source graph or its literature is free from sampling, publication or representation bias. Because no category filter narrows the search, those graph biases have more influence on what surfaces, and the search must correct for them.

## Using knowledge graph metapaths

The knowledge sources are AddictionKB metapaths serialized in open knowledge format (OKF). When reading them:

* Cite the metapath pattern (the node and edge type sequence), the specific path instances read, and their document IDs.
* Report edge provenance and evidence type from the source metadata (for example, curated association, literature-derived co-mention, or record-derived co-occurrence). Treat co-mention and co-occurrence edges as weak support.
* Path existence and path counts reflect how densely a topic was curated, not effect size or strength of evidence. One well-sourced path can outweigh many paths through hubs.
* Prefer metapaths where a concept reaches the outcome through an interpretable intermediate over paths that connect only through generic, highly connected hub nodes.
* Distinguish mechanistic support from measurable support. A path through genes or pathways can justify why a concept matters, but the hypothesis still needs features in the dataset that represent it.
* Record-derived edges may come from populations or coding practices unlike the current dataset. Note this when relying on them.

## Search procedure

1. Map the scope. Inspect the available OKF categories, metadata, supported filters, node and edge types, and metapath patterns before retrieving candidates.
2. Retrieve broadly. Start with HIV-and-outcome retrieval without a specialty filter.
3. Sample across distinct regions of the graph. A region can be defined by, for example, category, metapath pattern, or the type of intermediate node (gene or pathway, drug, comorbidity, behavior, social or clinical-code concept). Examine candidates from several distinct regions before narrowing.
4. Check feature availability while sampling. Note regions with no measurable features in the available-feature context and set them aside early, rather than discovering this after a candidate is chosen.
5. Build a shortlist of materially different candidates. Candidates differ materially when they propose different mechanisms or intermediates, not when they rephrase the same path.
6. Select the strongest answerable candidate using the criteria below.

Do not silently impose a familiar specialty filter, stop at the first plausible path, rank a hypothesis merely by document or path count, or force coverage of every category.

## Biases to correct for

* Hub bias: highly connected nodes (for example, broadly studied genes, common comorbidities or general inflammation terms) appear on many paths simply because they have many edges. Do not treat frequent appearance as specificity.
* Evidence density: heavily studied areas produce more paths and documents. Sparse regions are not necessarily weak; they may be under-curated.
* Familiarity: a whole-graph search can easily surface well-established risk factors. State whether the candidate is already well established for this outcome. Prefer a candidate that tests something informative over one that restates known associations, unless the known association is being tested in a new way.
* Category representation: some categories contribute more source documents to the graph than others. Note when the shortlist is dominated by one category and whether that reflects the evidence or the corpus.

## Selection criteria

Compare shortlisted candidates on:

* Relevance to the fixed HIV outcome
* Evidence quality, including edge evidence type and provenance
* Feature availability and how directly features measure the concept
* Temporality: predictors must be recordable before the prediction time
* Redundancy with other candidates and with established predictors
* Leakage: exclude paths whose intermediates are the outcome itself, its synonyms or subtypes, or concepts recorded as part of diagnosing the outcome
* Informativeness: what the experiment would teach if the association holds or fails

## Output

Verify exact predictor mappings against the available-feature context. Preserve the fixed HIV outcome and prediction time, and exclude the outcome, outcome-derived proxies and unavailable or post-outcome information. Use the existing question and hypothesis schemas and state:

* Search coverage: categories, metapath patterns and regions examined, and regions set aside with the reason
* The shortlist and why the selected candidate was preferred over materially different alternatives
* Metapath patterns, path instances and document IDs read, with edge evidence type
* Mapped predictors and whether each is a direct measure or a proxy
* The expected association and its direction
* Alternative explanations
* Corpus blind spots and uneven evidence density relevant to the candidate
* What would weaken the hypothesis

A graph path is hypothesis-generating evidence, not causal proof. Cite only documents and graph paths actually retrieved. Report insufficient support rather than inventing a graph result.

