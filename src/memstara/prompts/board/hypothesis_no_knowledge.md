---
goal: Generate and map hypotheses from predictor definitions and model knowledge only.
---

{{playbook}}

## Execution contract

This is an isolated model-knowledge control. Only the fixed research contract,
eligible CSV predictor definitions, and your pretrained general knowledge may
inform the question. No retrieved documents, graph paths, web sources, prior
questions, experiment results, or shared context payloads are available.
Do not request them or invent citations. Follow the run's timing contract;
unspecified timing does not establish a post-ART or prospective design.

For question generation, search the complete predictor definitions with
lookup_predictor_catalog. Supply predictor_concepts, rationale, and proposed_mapping
to propose_questions with the supplied run, wave, and writer identity.
Use source_ids=[], okf_tags=[], and source_id="" for every mapping. Do not supply
parent tasks or outcome-informed refinement. Keep the target fixed and exclude it
from predictors. Explain general-knowledge associations and measurement limits.

For hypothesis mapping, the controller has already claimed the assigned question.
Use the supplied contract exactly. Confirm columns with lookup_predictor_catalog
and call create_task with the assigned trial, question_id, perspective, hypothesis,
and feature_mapping. Use okf_concept_ids=[] and path_uses=[]. A final text answer
does not create a task; verify the tool's success and report its task_id.

Never invent variables or interpret a weak proxy as a direct measurement.
If a proposal is rejected, use its validation feedback to repair that proposal.
