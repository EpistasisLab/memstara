# Whole-graph question regeneration: diagnosis and correction

## Observed failure

The resumed `test-hiv-rep-2` execution remained in Loop 129 (Pipeline 65,
Replicate 1). At the 23:28 UTC observation on November 6, 2026, it had reached
regeneration round 16, with 30 completed question-agent invocations and one active
invocation. These are agent invocations, not individual LLM request counts.
The experiment was subsequently stopped at the user's request. Existing results
and failed-attempt evidence were retained; the experiment has not been restarted
as part of this correction.

The recorded agent called `propose_questions` with `questions: []`. The response
contained empty added/duplicate/skipped/rejected lists. There was no candidate for
the scientific or mapping validator to reject. The writer itself refused to propose
a candidate, repeatedly claiming that an exact edge to `HIV_DETECTABLE` was required
and that HIV complication or medication predictors would necessarily leak the target.

Those categorical claims are not established by the variable names. Leakage depends
on the actual feature's derivation, availability and prediction-time contract.
Unknown timing is not proof of leakage, and also is not proof of valid prospective
prediction. The absence of a direct graph edge does not by itself preclude a grounded,
explicitly labeled hypothesis connecting a retrieved mechanism to the fixed target.
It remains possible that a particular candidate has insufficient support.

## Why the skill-only revision was insufficient

The Motoro `config_snapshot` of invocation
`1dc16f3b-7821-4eec-80aa-7dc563662d66` contains the V2 statements permitting an
explicit inferential gap and rejecting a topic-only leakage judgment. The V2 skill
was actually delivered, not merely selected in the UI.

The same invocation's recorded input also contained:

- The common knowledge-only question-generation rules and the instruction to
  propose no questions if the knowledge cannot support the target.
- A large available-predictor catalog.
- The previous writer's own refusal, including its claim that complication and
  antiretroviral-class predictors would be leakage, appended as regeneration context.

The source code confirms that `remember_writer` saved the response and
`writer_feedback` copied up to 6,000 characters back into the next request. Labeling
that response as data did not prevent the observed writer from repeating its claim.
This is evidence of a self-reinforcing refusal pattern; it does not prove which
individual prompt sentence caused the model's decision.

The new incremental mirror was functioning during this incident: sampled normal
mirror times were 0.28–0.30 seconds, with one new Motoro evidence retrieval each.
The observed delay was repeated question generation, not the previous full-history
synchronization bottleneck.

## Implementation

| Location | Correction |
| --- | --- |
| `prompts/board/_knowledge_reasoning.md` | Defines retrieved facts versus hypothesis inference, measurement-specific leakage review, and strict versus exploratory timing requirements. No invented paths or automatically accepted predictors. |
| `prompts/board/hypothesis.md` | Includes that common definition in the KG hypothesis system prompt. The separate No Knowledge prompt/skill is unchanged. |
| `pipeline/question_contract.py`; `pipeline/board.py` | Clarifies the fixed-target generation instructions and appends the same common rules at the actual model-call boundary after the long catalog and repair context. No Knowledge and hybrid baseline source restrictions remain separate. |
| `pipeline/question_regeneration.py` | Retains the writer response in its audit record, but sends only its audit hash and attempt identity, not the refusal narrative. Rotates diagnostic focus while preserving actual validator feedback and same-Loop regeneration. |
| `mcp_servers/blackboard.py::propose_questions` | Returns and saves `empty_question_batch` for an empty submission, explicitly stating that no candidate was validated. Avoids opening a DB transaction for that empty batch. |
| `control/retry.py` | Allows ordinary retry from a verified stopped durable pause, without requiring a changed skill or rewriting the old execution. The workspace still checks that no execution is running. |

Target binding, source verification, mapping validation, No Knowledge isolation,
missing-value handling, train/test splitting, seeds, and existing results were not
relaxed or rewritten. An unsupported candidate must still be rejected. This change
does not create a valid hypothesis by fiat or claim that every corpus/target pair
has one. The user-requested same-Loop regeneration policy remains in place; there is
no new automatic skip or silent fallback to unrelated predictors.

## Validation and deployment status

98 focused tests passed, covering the actual model-call boundary after a large
catalog, No Knowledge isolation, shared prompt assembly, refusal removal across
restart, actionable empty-batch feedback, unchanged mapping/target checks, and
ordinary retry from a stopped pause. Another 51 prompt-loader, hybrid-isolation and
selective-retry compatibility tests passed. Ruff F821/F823 and `git diff --check` passed.

These are deterministic tests with mocked model execution. They establish the
changed software behavior, not a guarantee that the next LLM generation will produce
a valid hypothesis. No new paid experiment was launched to claim such a guarantee.
The correction is local and requires deployment before it affects the runtime.
Deployment/retry should create a new linked attempt, preserving the prior execution's
recorded prompts and outcomes. Keep the experiment stopped until that deployment.
