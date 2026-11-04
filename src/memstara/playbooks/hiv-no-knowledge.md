# Hypothesis Generation

Generate a testable outcome hypothesis to predict detectable HIV status after antiretroviral therapy (ART) initiation using the fixed study contract, the supplied dataset feature definitions and your own general knowledge. Do not look for, request or use any other source of information, such as documents, literature, databases or web search.

## Using your own knowledge

You may use your general biomedical and clinical knowledge to interpret feature descriptions, judge which features are relevant to the fixed outcome, and propose a plausible mechanism. When doing so:

* Present knowledge-based reasoning as general knowledge, not as cited evidence.
* Do not cite specific papers, authors, DOIs, datasets or statistics. They cannot be verified in this setting.
* Distinguish what a feature definition states from what you infer it represents clinically. If the inference is uncertain, say so.
* State whether the proposed association is already well established for this outcome, or whether it tests something less established.

## Selecting predictors

Select an eligible, pre-outcome predictor set that tests one stated association. Consider, for example:

* Relevance to the fixed outcome and the proposed mechanism
* Timing: the feature is recorded before the prediction time
* Definition clarity: what the feature records is stated unambiguously
* Measurement limitations: whether the feature is a direct measure or a proxy, and how it is likely to be recorded
* Non-redundancy: the features do not restate one another

Include as many features as the stated association needs. Do not limit the set arbitrarily or add unrelated features to increase the count.

## Exclusions

Do not use the target, direct outcome-derived proxies, identifiers, post-outcome information or unavailable measurements. Do not inspect outcome values, model performance, reserved validation data or results from other pipelines when forming the initial hypothesis.

On later Loops, if pipeline-local learning context is provided, you may use it. State the parent finding, what changes, and the uncertainty the refinement tests. Label the refinement as informed by previous results. Still use no other source of information.

## Output

Use the existing question and hypothesis schemas and state:

* The fixed outcome
* Each predictor, what the dataset records for it, and what it is taken to represent
* Whether each predictor is a direct measure or a proxy
* The rationale, marked as based on general knowledge
* Whether the association is well established or less established
* The expected association and its direction
* Alternative explanations
* What empirical result would weaken the proposed association

Label the result as a model-knowledge hypothesis with no retrieved evidence. If the schema has a field for run or arm metadata, put the label there rather than in the question or hypothesis text. Avoid causal language. If the feature definitions do not permit a valid candidate, report that limitation.
