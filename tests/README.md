# Pipeline regression tests

The suite verifies contracts across the pipeline, persistence and UI. It is not
a guarantee that every possible dataset, provider response or release scenario
will succeed. The tracking issue is [#183](https://github.com/HyunjunA/memstara/issues/183).

## Run the checks

From the repository root, use a separate test environment and install the locked
runtime extra as well as development tools:

```sh
UV_PROJECT_ENVIRONMENT=.venv-test uv sync --frozen --extra dev --extra runtime
```

The runtime extra pins Motoro v0.10.0 by commit and LiteLLM 1.97.0, matching the
provider-adapter acceptance baseline. Linux uv installations select CPU Torch.
CI installs this extra so runtime-dependent input/contract tests do not silently
skip for a missing Motoro dependency. It does not modify a sibling checkout.
Then run:

```sh
UV_PROJECT_ENVIRONMENT=.venv-test uv run --frozen --extra dev --extra runtime pytest -q --junitxml=test-results/python.xml
UV_PROJECT_ENVIRONMENT=.venv-test uv run --frozen --extra dev --extra runtime ruff check tests/test_research_input_matrix.py tests/integration
UV_PROJECT_ENVIRONMENT=.venv-test uv run --frozen --extra dev --extra runtime lint-imports
```

The default pytest suite excludes PostgreSQL integration and paid live tests. Some component tests run
real ML workers and MCP subprocesses against synthetic inputs; they need local
process inspection permissions. Model responses and remote-provider failures
are simulated. No paid inference batch is required.

For PostgreSQL, supply `MEMSTARA_TEST_DATABASE_URL` pointing to a **dedicated,
disposable database whose name ends in `_test`**, then run:

```sh
UV_PROJECT_ENVIRONMENT=.venv-test uv run --frozen --extra dev --extra runtime pytest tests/integration --run-integration -q --junitxml=test-results/postgres.xml
```

The fixture creates a unique schema per test, uses real independent connections,
and drops only that schema. Do not point it at a production/experiment database.
The saved-model evidence fixture explicitly selects XGBoost so a developer's
local default engine cannot change the assertion under test.

From `viewer/web`:

```sh
npm ci
npm test
npm run typecheck
npm run lint
npm run build
npx playwright install chromium
npm run test:browser
```

Browser tests require the build first. Playwright starts isolated servers on
4175 (built application) and 4177 (source component fixtures), with strict port
ownership. The source fixture server has no live backend proxy. Browser scripts
mock API/control responses and exercise actual rendered React components,
keyboard input, confirmation, status projections and responsive layouts.
They do not start real experiments. Do not stop a user's server to free these
ports; use a separate test environment if the ports are occupied.

Three deployment diagnostics are deliberately excluded from this fixture suite:
`app-ux-audit.browser.mjs`, `telemetry-live.browser.mjs` and
`experiment-registry.browser.mjs`. They depend on a real deployment or private
historical evidence and must be run explicitly in an appropriate environment.
Their exclusion is not a passed acceptance result.

## Automated acceptance with real Haiku 5.5

`tests/live/test_haiku_pipeline.py` calls the real configured Azure deployment
through the normal pipeline/provider adapter. Each of the four OKF/CSV modes
runs one Loop, sequentially, using the public synthetic example and all six
LLM roles. Both configured stage profiles must be `claude-haiku-5-5`; the test
rejects a different model before making requests.

```sh
UV_PROJECT_ENVIRONMENT=.venv-test uv run --frozen --extra dev --extra runtime pytest tests/live -q -s -x --run-live --junitxml=test-results/haiku-live.xml
```

This command incurs model charges and requires configured credentials, both
databases, local MCP/process permissions and the matcher model cache. The
explicit `--run-live` flag enables these tests. Ordinary pytest/CI collection
deselects them; there are no hidden paid calls in a normal CI invocation.
`-x` stops after the first failure. Each case has a 40-minute safety ceiling and
uses one local numerical thread. All provider requests use Haiku; synthetic
names used by deterministic routing tests remain internal fixture values.

The tests verify stage/report persistence, actual response-model receipts,
registry synchronization, source preservation and measured-versus-proposal
semantics. Evidence is retained under `outputs/verification/haiku_live_*/`, with
one subfolder per input mode, `driver.log`, full run artifacts and
`acceptance.json`. Unique Memstara database schemas remain available for audit;
existing experiment schemas are not cleared. Normal Motoro run records are
created through its public API. No Motoro source or supplied skills are edited.
Token receipts and any recorded estimates do not prove an Azure invoice amount.

To continue a batch without rebilling completed executions, pass
`--live-batch outputs/verification/haiku_live_<batch>`. Completed cases are audited
against their frozen Haiku profiles, source hashes, materialized files, receipts
and DB records. An investigated failed case requires `--live-retry-failed`; its
fresh attempt uses a nested folder and a new unique schema. Prior failed evidence
stays in place. This option never silently retries a failed live execution.

## Coverage map

The table names representative tests, not every test in the directory.
The deterministic tests below simulate remote responses. The separate live
suite above verifies real Haiku responses and persistence in all four modes.

| Area | Representative automated checks | Evidence boundary |
|---|---|---|
| Four input modes | `test_research_input_matrix.py`, `test_optional_inputs.py`, `test_research_inputs.py`; `research-input-modes.browser.mjs` | Real CSV/corpus parsing and profile registration; launch manager and browser backend mocked |
| Target and study isolation | `test_research_input_matrix.py`, `test_input_preflight.py`, `test_question_isolation.py` | Positive/negative mapping, target exclusion, timing, malformed CSV, drift, immutable previous study |
| Model/skill routing | `test_stage_model_defaults.py`, `test_saved_skill_compatibility.py`, `test_anil_current_skills.py`, `test_llm_environment.py`; `stage-models.browser.mjs` | Configuration and frozen model contracts; no provider deployment certification |
| Question/hypothesis/knowledge | `test_question_contract.py`, `test_question_repair.py`, `test_question_discovery.py`, `test_question_feedback_guard.py`, `test_tool_argument_repair.py`, `test_okf_fields.py`, `test_okf_bundle_surface.py`, `test_matcher.py` | Synthetic knowledge and responses; matcher encoder stubs do not validate learned embedding quality |
| Features and reproduction | `test_feature_selection.py`, `test_feature_reproduction.py`, `test_paired_feature_eligibility.py`, `test_leakage_rules.py` | Guided/random bounds, seeds, eligible universe, source columns and leakage guards |
| Data and ML | `test_data_allocation.py`, `test_ml_reproducibility.py`, `test_ml_engines.py`, `test_paired_ml.py` | Real bounded local fitting/replay and worker watchdogs; no clinical performance claim |
| Interpretation and Explanation | `test_specialist_xai.py`, `test_interpretation_fanout.py`, `test_specialist_explanation.py`, `test_explanation_resilience.py`, `test_report_completion.py` | Real saved LR/XGBoost and local SHAP/LIME evidence; generated narrative/remote calls simulated |
| No-CSV proposals | `test_optional_inputs.py` | Both knowledge modes pass six sequential handoffs; no fitted metrics; fabricated source IDs/empirical output rejected |
| Preparation, transport and recovery | `test_execution_preparation.py`, `test_completion_repair.py`, `test_model_transport_retries.py`, `test_failure_diagnostics.py`, `test_request_diagnosis.py`, `test_iteration_recovery.py`, `test_durable_checkpoint.py` | Fault injection verifies bounded recovery and retained evidence; request diagnosis covers pending/terminal correlation, cancellation, concurrent isolation, failed writes and missing/corrupt evidence. Real outage behavior remains provider dependent |
| Lifecycle and ownership | `test_control_request.py`, `test_control_recovery.py`, `test_run_ownership.py`, `test_pipeline_workspace.py`, integration lease tests | Default suite includes a real isolated HTTP/process restart; integration tests combine it with real DB ownership and post-commit crash blocking |
| Persistence and artifacts | `test_experiment_registry.py`, `test_run_artifacts.py`, `test_request_trace_isolation.py`, `test_mcp_protocol.py`, `integration/` | File/index contracts, real synthetic MCP subprocess transport and real PostgreSQL persistence |
| Cost and time | `test_cost_accounting.py`, `test_workspace_cost.py`, `test_telemetry_totals.py`, `test_loop_telemetry.py`; `cost-display.test.mjs`, `cost-evidence.browser.mjs` | Receipt/provenance and missing/aggregate/cached cost states; no live Azure invoice audit |
| All combinations | `test_combinations.py`, `test_all64_runner.py`, `test_specialist_pilot.py`; combination browser scripts | Enumeration, routing, guards and UI; not 64 paid executions |
| Floor plan, logs and results | frontend `floor-*.test.mjs`, `clinical-log.test.mjs`, `results-status.test.mjs`; layout/log/status browser scripts | Rendered mock executions and pure projection functions |
| Universe and memory | `test_question_memory.py`, integration memory tests; `question-memory.browser.mjs`, `universe-reliability.browser.mjs`, `universe-rendering.browser.mjs` | DB scoping plus browser synthetic stress; not production-scale load testing |
| Developer views and UI controls | `test_agent_explorer.py`, `test_code_atlas.py`; atlas/explorer, delete, minimized panels, skill wizard and research browser scripts | Rendered responsive controls and injected API failure handling |

## Release acceptance mapping

AC identifiers refer to the release plan; having tests does **not** mark a
release gate passed. Full candidate acceptance requires the prescribed setup,
execution and evidence, in addition to these regressions.

| Release scenarios | Regression support | Acceptance still needed |
|---|---|---|
| AC01 | CI dependency/build jobs, infra tests | Isolated cold installation of the selected release candidate |
| AC02 | Input matrix and profile tests | Independent reviewer registration of the public example |
| AC03–AC06 | Four profiles/control launches; both proposal handoff chains; component empirical tests | Local four-mode Haiku end-to-end checks passed; repeat on the independently installed release candidate |
| AC07–AC09 | Feature reproduction, allocations, paired ML, specialist XAI | Candidate execution evidence of selected routes |
| AC10 | Stage routing unit tests and browser settings | UI/API/request/response identity on a live candidate |
| AC11–AC14 | Input rejection, tool correction, output repair and transport fault injection | Candidate-level fault checks; supported real-provider request behavior |
| AC15–AC19 | Recovery/checkpoint/control/ownership/artifact tests, DB integration and real HTTP controller restart with synthetic workers, DB ownership and post-commit crash blocking | Live lifecycle timing, worker loss, partial storage and command race exercises |
| AC20–AC24 | Universe/memory/scope/ranking/cost/layout/browser regressions | Candidate stress/accessibility and actual billing evidence, where applicable |
| AC25 | Supplied skill compatibility checks and public-tree CI inspection | Protected-original hash/license and complete artifact publication inspection |
| AC26 | Distribution build, offline wheel install/byte checks, and separate locked-runtime installation with dependency/import checks | Live pipeline and static artifact acceptance on the selected release candidate |
| AC27 | PostgreSQL dump/restore of application schema and Motoro agent/run/step/memory models with vector distance checks; artifacts, sequences, constraints and reader ACLs | Quiescent two-DB/file bundle restore also covered; selected legacy schema/rollback/lock tests also covered; deployed writer shutdown, extension upgrades, authentication, cross-host ownership and named-release upgrades remain outstanding |
| AC28 | No publication in this task | Published release download and independent smoke check |

## Local verification: 2026-10-09

The final full default backend run passed **1,104 tests**, with **16 deselected**
(12 PostgreSQL and 4 live tests), 7 warnings and 4 passing subtests. Real
PostgreSQL integration passed **12 tests** against a newly created temporary
test database, which was removed afterward.

Real Azure Haiku acceptance passed **all four input modes** on the public
synthetic example. All six LLM roles were verified from actual response-model
receipts. CSV modes saved measured ML/interpretation results; no-CSV modes saved
proposals without invented fitted metrics. A final read-only rerun audited all
four successful executions and their DB records without additional inference.
Evidence: `outputs/verification/haiku_live_20261009t173929_b01028f0/summary.json`
and `RESULTS.txt`; failed attempts remain preserved alongside successful retries.

The live checks exposed two application defects, now fixed and covered by tests:
no-OKF MCP registration used an incompatible API and mismatched persisted server
IDs; proposal reconciliation looked up adapter-only run IDs as Motoro agent runs.
Memstara now uses the public server service API for only selected servers and
validates saved proposal input/output evidence before registry synchronization.

Frontend unit tests: **45 passed**. Typecheck/build and lint exited successfully;
existing lint and bundle warnings remain. Three import boundaries and targeted
Python lint checks passed. All **32 browser fixture files** passed across full
and targeted reruns, rather than one uninterrupted clean browser invocation.
No Azure billing query, fresh install, backup/restore or 64-condition experiment
was performed. Default CI checks deterministic regressions; real Haiku checks
require the explicit `--run-live` command above. These figures describe the original working-copy verification. Subsequent
committed-candidate and GitHub Actions evidence is tracked in issue #183.

New input regressions add 35 cases. The initial browser run found a genuine
research-list response bug: a successful response without an `inputs` array
could crash the creation screen. Both research components now reject that
response with an error message; the selector supports retry. Browser regression
checks cover the malformed response and subsequent valid recovery. Other
initial browser failures included stale accessible-name assumptions and a
compact-layout initialization race in test clicks; these were corrected without
bypassing confirmation or forcing clicks on hidden controls.

A full rerun also exposed a timing race in the AI skill assistant: the default
model could arrive while a model name was being entered. The assistant now
locks inputs while loading the connection. The all-agent wizard test holds the
model response until it has asserted the locked state, then checks the exact
chosen model in generation requests for every agent in both creation modes.

Local evidence files are under `/private/tmp/memstara-pipeline-*` (pytest XML,
logs, process rerun and DB integration logs). Playwright writes its standard
HTML/attachments under `viewer/web/playwright-report/` and `test-results/`.
These are local, disposable diagnostics, not public experiment data. CI uploads
its own reports from the existing workflow. Counts in this dated record describe the tested working copy. Consult #183
for the corresponding committed-candidate and GitHub Actions results.

Actual provider validation in this workstream uses `claude-haiku-5-5` for both
`non_explanation_agents` and `explanation_agent`. Synthetic model names in unit
and browser fixtures test routing without contacting any deployment.

## Integrated checkout verification: 2026-10-09

A clean checkout of `9235268` passed **1,105 default backend tests**, with
16 explicitly deselected PostgreSQL/live tests and 4 passing subtests. The Python
runtime was the existing verified environment; this was not an isolated new Python
installation. The historical 1,104-case working-copy count included 17 local-only
study checks excluded from the public tree. The committed suite adds 18 publication
and mode-preflight checks: 1,104 - 17 + 18 = 1,105. These excluded study checks are
not public CI acceptance and no supported public regression was dropped.

A fresh `npm ci` in the clean checkout passed **45 frontend unit tests**, typecheck,
lint and build, followed by **all 32 browser fixture files in one clean run**.
Existing lint/bundle warnings remain. The installed Node lockfile also reports
8 existing dependency advisories (6 high, 2 moderate); dependency-security review
is tracked as a release gate in #175, not declared resolved by passing UI tests.
The published candidate contains only the generated synthetic example. Its CLI
inspection passed: 120 rows, 4 eligible predictors, 1 usable OKF document.

The subsequent CI runtime-extra change keeps Motoro present throughout backend
and PostgreSQL checks; candidate-specific Actions evidence is recorded in #183.
The paid four-mode Haiku evidence above remains preserved; these checkout checks
made no new inference requests. Fresh installed-package, security, contributed
rights and independent release acceptance remain separate gates.
