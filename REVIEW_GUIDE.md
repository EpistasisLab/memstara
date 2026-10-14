# Reviewing Memstara

Use this guide for file/function review with or without an AI coding assistant.
A human reviewer owns technical findings and approval. AI explanations are aids,
not evidence that source behavior is correct. Read the called functions and tests.

## Select the source

Use one source branch for the public example and research experiments. For the
current candidate, use `experiment/agent-combinations-pilot`. Pin a commit before
review, record `git rev-parse HEAD`, and record uncommitted changes separately.
Do not confuse a branch URL with an immutable reviewed revision.

```bash
git fetch origin
git switch experiment/agent-combinations-pilot
git rev-parse HEAD
```

Local editable-package metadata may lag the checkout. Record source SHA, installed
versions, input/skill hashes, model deployment IDs, seeds and effective settings.
Private research inputs and outputs stay outside the published source tree.

## Reading map

Paths are relative to the repository root. Follow caller -> validation -> frozen
configuration -> tool/model operation -> persistence -> API/display.

| Slice | Start reading | Review question |
|---|---|---|
| Inputs and configuration | `src/memstara/research_inputs.py`, `stage_models.py` in that package, `src/memstara/control/request.py` | Are target semantics, modes, model precedence and immutable inputs explicit? |
| Skills and launch | `src/memstara/control/catalog.py`, `src/memstara/control/service.py` (`Handler._launch`) | Do valid selections reach execution and invalid ones stop before side effects? |
| Orchestration | `src/memstara/pipeline/board.py` (`run`), `preparation.py`, `scheduler.py`, `snapshot.py` in that directory | Are responsibilities, dependencies and completion criteria clear? |
| Questions and features | `src/memstara/pipeline/question_contract.py`, `feature_selection.py` in that directory, `src/memstara/mcp_servers/okf.py` | Are questions executable, sources scoped and predictors free of target leakage? |
| Data and evaluation | `src/memstara/data_allocation.py`, `paired_ml.py`, `evaluation.py` in that package | Are split identities, preprocessing, both models and metrics correct? |
| Interpretation and explanation | `src/memstara/specialist_xai.py`, `src/memstara/specialist_explanation.py` | Do both models reach the selected specialist and do explanations match evidence? |
| Recovery and persistence | `src/memstara/pipeline/checkpoint.py`, `run_ownership.py` in that directory, `src/memstara/experiment_registry.py` | Can failures, competing workers and resume lose or duplicate work? |
| API, evidence and cost | `viewer/api/`, `src/memstara/pipeline/request_evidence.py`, `src/memstara/cost_accounting.py` | Are identities isolated, errors observable and billing claims supported? |

The [function ledger](review/backend-functions.csv) lists current source locations;
its rows are NOT_REVIEWED, and line numbers must be regenerated or checked after
changes. Use [findings](review/findings.csv) and [decisions](review/decisions.csv)
to connect source review to evidence. A blank reviewer field is not acceptance.

## First reproducible checks

Install the locked environment following [README.md](README.md#get-started).
These tests use synthetic inputs; they do not call a model or prove a full pipeline.

```bash
uv run --frozen --extra dev --extra runtime pytest -q tests/test_user_skill_persistence.py tests/test_skill_catalog_errors.py tests/test_research_input_matrix.py tests/test_packaged_skills.py
```

For a normal/failure pair read and run:

```bash
uv run --frozen --extra dev --extra runtime pytest -q tests/test_research_inputs.py::test_valid_inputs_are_not_falsely_marked_pipeline_ready tests/test_research_inputs.py::test_missing_cells_block_without_rewriting_source
```

## AI-assisted reading

An editor such as Cursor is optional; no particular vendor is required. Ask the
assistant to identify exact files/functions, trace a normal and failure path,
state invariants and point to assertions that test them. Inspect those references
rather than accepting generated explanations. Do not supply credentials, private
cohort rows or private run traces to an external tool without authorization.
Do not let a review assistant edit Motoro or contributed skill originals.

Suggested prompt: "Explain this function's callers, inputs, side effects, failure
handling and persistence. Cite exact functions and tests. Separate observed source
behavior from assumptions. Do not edit files or run paid calls."

## Findings and approval

Use a draft PR for the integration delta; review in bounded slices, not one huge
approval. Also inspect unchanged dependencies. Use pinned commit permalinks for
findings outside the diff. Record:

```text
Severity: Blocker / Major / Minor / Question
Candidate SHA and file/function:
Trigger and expected behavior:
Observed code or reproduction evidence:
Impact and requested action:
Test command/result or not-yet-reproduced limitation:
Fix SHA and non-author verification:
```

Fixes use scoped commits and meaningful regression tests. Reply to each finding;
a non-author rechecks before resolution. Record excluded files and residual risks.
New commits require impact review. CI success and completed checkboxes do not
replace source review. Approval refers to a specific SHA and scope, not permission
to publish. Use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for release gates.
