# Memstara

[![CI](https://github.com/HyunjunA/memstara/actions/workflows/ci.yml/badge.svg)](https://github.com/HyunjunA/memstara/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](pyproject.toml)

A **multi-agent research workbench** that reads a literature corpus, proposes
predictors of a clinical outcome, evaluates them against a cohort, and explains
the results. A shared PostgreSQL board records each stage's work; MCP tools
connect the agents to the literature, dataset, semantic matcher, and ML evaluator.

Memstara builds on [Motoro](https://github.com/EpistasisLab/motoro) as an
in-process library for agent execution, model calls, MCP integration, and runtime
persistence. Memstara adds the research pipeline, its own database, a host control
service, and a browser workspace. Motoro and Memstara own separate databases.

## Releases and development

Memstara uses semantic release tags (`vMAJOR.MINOR.PATCH`). The Git tag is the
source of the Python package version: `hatch-vcs` generates package metadata and
`memstara.__version__` during installation or build. Commits between tags produce
a development version. An unbuilt source checkout reports `0.0.0+unknown`.

The `main` branch contains ongoing development. For a reproducible installation,
choose a published tag from the [tags page](https://github.com/HyunjunA/memstara/tags)
when available, and record the Motoro revision and run configuration as well.
Reinstall editable packages after changing revisions to refresh version metadata.

```bash
python -c "import memstara; print(memstara.__version__)"
git rev-parse HEAD
git -C ../motoro rev-parse HEAD
```

To prepare a release, merge and validate the intended revision on `main`, then
create and push an annotated tag. Replace `vX.Y.Z` with the next version; do not
move an already published release tag.

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Build from a Git checkout with tags available, or from a generated source
distribution. A plain source archive without version metadata is not a release
build input. The viewer is part of the same release; its private npm package
version is not an independent application release number.

[environment.yml](environment.yml) installs Memstara and Motoro in editable mode.
Validate the pair of revisions before using it for a study, and preserve prompt
snapshots and data provenance alongside each run.

## Features

| Area | What Memstara provides |
|---|---|
| **Literature-grounded hypotheses** | Separate question-writing and feature-mapping calls over an OKF corpus |
| **Semantic matching** | Maps literature concepts to exact cohort columns using a cached catalogue |
| **Agent pipeline** | Hypothesis, Data, ML, Interpretation, and Explanation roles |
| **Coordination** | Durable task claims, retries, results, and execution records on a shared board |
| **Evaluation** | Model scores, feature contributions, configured comparisons, and evidence views |
| **Agent skills** | Role-specific instructions, Markdown upload, custom writing, and Hypothesis-only assisted drafting |
| **Pipeline design** | Selected Pipelines and bounded All Combinations skill schedules |
| **Browser workspace** | Live execution, clinician-facing findings, run controls, and saved configurations |
| **Traceability** | Frozen settings and prompts, per-Loop skill provenance, and recorded actual calls |

**The five roles**

| Role | Responsibility | Internal stage |
|---|---|---|
| Hypothesis | Writes questions, maps concepts to predictors, and creates board tasks | `hypothesis` |
| Data | Extracts the requested columns under the fixed-target contract | `data` |
| ML | Trains and evaluates the selected predictors | `ml` |
| Interpretation | Describes measured findings, uncertainty, and limitations | `interpreter` |
| Explanation | Synthesizes findings with literature and labels proposed next steps | `report` |

The Explanation Agent retains `report` identifiers for saved-run compatibility.
Its default skill is `report_clinical_explanations`; Interpretation defaults to
`interpreter_factual_observations`. Existing saved selections are retained.
Instructions guide model behavior and do not guarantee compliant output.

The agent-configured paired workflow adds Data allocation skills (training-heavy
or balanced, both stratified), an LLM-proposed LR/XGBoost plan within server-enforced
resource limits, and SHAP or LIME specialists that each receive both models.
Explanation specialists consume Interpretation output and scoped knowledge.
These contracts apply when the corresponding policies and skills are selected;
legacy single-model runs remain supported. See the
[agent contracts](DEVELOPER_GUIDE.md#agent-contracts-and-skills) before comparing routes.

**Coordination and tools**

```text
Literature (OKF) → Hypothesis → Data → ML → Interpretation → Explanation
                      ↕          ↕      ↕          ↕              ↑
                      └──────────┴──────┴──────────┴── shared board ┘
                                 ↑
                         Cohort CSV + matcher
```

The board pipeline coordinates stages through durable rows. Only Hypothesis
creates tasks; downstream workers claim tasks and submit results. Question
writing and feature mapping have separate tool grants. The current primary
question policy excludes direct result-reading tools from both calls. Iterative
evidence is frozen and supplied by the driver rather than fetched freely by agents.
See [scientific_policy.py](src/memstara/pipeline/scientific_policy.py) and
[core.py](src/memstara/pipeline/core.py) for the enforced grants.

The five MCP servers are `okf`, `memstara-data`, `memstara-ml`,
`memstara-blackboard`, and `semantic-matcher`. Their launch definitions live in
[servers.py](src/memstara/servers.py); each runs under the same Python interpreter
as the pipeline. `BOARD_SERVERS` and `BOARD_TOOLS` restrict each role's access.
Knowledge search publishes structured `filters` with category choices derived from
its configured corpus and run confinement. `okf_list_domains` also returns these
choices. Topic words belong in `queries`; they do not imply a category exists.
The model-facing legacy `fields` argument accepts only an empty string, so an old
non-empty request is rejected rather than silently ignored. Internal Python callers
retain validated `fields=` compatibility. Invalid filters are rejected before
scoring; successful responses include requested and applied filters. Model/tool
I/O records preserve requests, validation responses and subsequent corrections.
No automatic fallback changes the selected scope and no new retry loop is added.
Tool schemas refresh when a new pipeline process connects its knowledge server;
existing experiments and their archived outputs are not rewritten.

The alternative `mvp` entry point runs Hypothesis, Data, ML, and Interpretation
under a supervisor instead of the board scheduler.

## Layout

```text
src/memstara/
  config.py, env.py, paths.py   Settings, environment loading, repository paths
  servers.py                   MCP server launch definitions
  blackboard.py                Memstara's board schema
  pipeline/                    Board and supervisor drivers, policy, snapshots
  prompts/                     Versioned agent system prompts
  playbooks/                   Role-specific instruction skills
  mcp_servers/                 Knowledge, data, ML, board, and matcher tools
  matcher/                     Catalogue, embeddings, and exact-column mapping
  control/                     Host service for pipeline configuration and execution
  trace/                       Saved-run inspection and replay
  prep/                        Synthetic and cohort preparation utilities
viewer/                        Browser workspace and read-only observation API
scripts/                       Cache building, audits, and operational checks
tests/                         Backend tests
outputs/                       Local datasets, caches, and run artifacts (ignored)
```

## Get started

See [third-party notices](THIRD_PARTY_NOTICES.md) for incorporated code and example
material scope. A project-wide release license and redistribution review remain
pending; the example-data declaration is not a license for the whole application.

You need **Git, Python 3.12 or 3.13, Docker with Compose**, a supported LLM
credential, and a checkout of the selected Memstara revision. Motoro requires its
own PostgreSQL database and Redis; Memstara's root Compose file starts only its
own PostgreSQL service.

**1. Install the Python runtime.** For a reproducible, locked installation, use uv:

```bash
git clone https://github.com/HyunjunA/memstara.git
cd memstara
# Select the reviewed tag or commit before installing.
cp .env.example .env
uv sync --frozen --extra dev --extra runtime --python 3.12
source .venv/bin/activate
```

The `runtime` extra installs Motoro v0.10.0 from its immutable release commit and
LiteLLM 1.97.0. No sibling Motoro checkout is required for this path. Configure
runtime/provider settings in Memstara's local `.env` or export them separately.
The existing application environment is not changed when this is run in a new
checkout. Use the same `--extra dev --extra runtime` flags with subsequent
`uv run` commands so synchronization retains the runtime.

For editable sibling development with Conda, use this alternative:

```bash
git clone --branch v0.10.0 https://github.com/EpistasisLab/motoro.git motoro
git clone https://github.com/HyunjunA/memstara.git
cd memstara
cp .env.example .env
conda env create -f environment.yml
conda activate memstara
```

On an existing workspace, use its checkouts and environment; keep the existing
`.env`. Set product paths in Memstara's `.env` and runtime/provider settings in
`../motoro/.env`, using the corresponding `.env.example` files as templates.
Pipeline environment loading reads both files and preserves exported values.
Use absolute paths for datasets and bundles so subprocesses resolve them consistently.

To use your own corpus, dataset and prediction target, open **Floor plan → Prepare
research inputs**, inspect and save a version, then select it when creating a
pipeline or in **Data & target** settings. See the
[synthetic research walkthrough](examples/research-inputs/README.md) for supported
input formats, label mapping, versioning and CLI usage. Registration does not
start an experiment; execution uses a separate analysis copy and preserves sources.

Research profiles support four combinations: OKF + CSV, CSV without OKF,
OKF without CSV, or neither source. With a CSV, the pipeline can train and evaluate
models. Without a CSV, it produces a research proposal and future analysis plan;
it does not produce fitted models, measured scores, confusion matrices or computed
SHAP/LIME results. A research objective is still required. See the walkthrough's
[input-mode guide](examples/research-inputs/README.md#choose-the-input-mode) for
the exact configuration fields and expected outputs.

**2. Prepare the databases and Redis.** On a new host, follow
[Motoro's setup](https://github.com/EpistasisLab/motoro#development) to provision
its services and apply its migrations. Its database needs the **pgvector**
extension: plain PostgreSQL alone cannot apply the current Motoro migrations.
Point `MOTORO_DATABASE_URL` and `MOTORO_REDIS_URL` at those services; do not rely
on default ports when using an isolated workspace. A package-only installation
can apply its schema with `python -m motoro.migrations upgrade --url "$MOTORO_DATABASE_URL"`.
Then, from the Memstara checkout:

```bash
docker compose up -d
docker compose ps
```

**3. Configure the connection and research inputs.** Set the deployed provider
and model in the local runtime environment (Memstara `.env`, exported values,
or `../motoro/.env` when using sibling development). The board driver resolves the deployment-wide
selection through the control configuration; its legacy `--provider` and
`--model` flags are not independent overrides. Explicit `stage_models` profiles
override the agent model assignments; see the [developer guide](DEVELOPER_GUIDE.md#model-profiles-and-their-limits).
Keep deployment defaults configured for control validation. Provide the credentials required
by that connection: `ANTHROPIC_API_KEY`, both `ANTHROPIC_FOUNDRY_API_KEY` and
`ANTHROPIC_FOUNDRY_RESOURCE`, or `OPENAI_API_KEY`.

For a synthetic example in a fresh checkout, the following creates
`outputs/dataset.csv` and `outputs/okf_synthetic_sample`. It overwrites those
sample paths, so use it only when they are not holding data you need to retain.

```bash
python -m memstara.prep.sample
export AGENTIC_OKF_BUNDLE_DIR="$PWD/outputs/okf_synthetic_sample"
export MEMSTARA_DATASET_PATH="$PWD/outputs/dataset.csv"
export MEMSTARA_OUTPUT_DIR="$PWD/outputs"
export MEMSTARA_OUTCOME_COLUMN=outcome
python scripts/build_matcher_cache.py
```

The matcher needs its catalogue and embeddings built for the selected cohort
and outcome. Rebuild when the cohort header, matching configuration, or embedding model changes. The first build may need embedding
model downloads. Set `HF_HOME` to an empty dedicated cache when verifying a cold
installation; Memstara forwards explicit cache paths to its tool subprocesses.
The synthetic corpus includes absent-variable decoys and
planted predictive signal for checking the literature-to-column mapping.

**4. Run a pipeline.** With the runtime services and credentials ready:

```bash
python -m memstara.pipeline.board --trials 3 --waves 1 --y-column outcome
# Alternative supervisor-driven example:
python -m memstara.pipeline.mvp --trials 3 --y-column outcome --trace
```

These execute real model calls. For a real cohort, set its dataset, knowledge
bundle, and outcome instead, rebuild its matcher, and pass the outcome explicitly
with `--y-column`. The board CLI defaults to `outcome`.

**5. Open the browser workspace.** Configure the viewer's read-only database
accounts and connection settings as described in [viewer/README.md](viewer/README.md).
From the Memstara checkout:

```bash
docker compose -f viewer/docker-compose.yml up -d --build
python -m memstara.control
```

Open <http://localhost:8070>. The observation API uses port 8071; the separate
host control service uses 8072 and runs in the foreground. Keep it running in
its own terminal when using browser execution controls. The viewer's database
connections remain read-only; pipeline actions go through the control service.

## Using the workspace

**Selected Pipelines** configures and starts individual saved pipelines.
Different saved pipelines can execute concurrently.
**All Combinations** selects skill variants across all five roles. Two Hypothesis,
three Data, two ML, two Interpretation, and one Explanation variant produce
24 combinations, displayed in three design rows. A row is not an extra agent.

Each combination executes one Loop with one hypothesis. New designs have a
reviewed limit of 1–10,000 Loops, defaulting to 10. Random Start chooses the
initial combination and then follows a fixed cycle. A limit below the combination
count covers only part of the set; a larger limit repeats it. Resume retains
the frozen schedule and budget. Legacy repetition schedules remain readable.
One path runs at a time within a design; different saved pipelines can run
concurrently. These schedules are not independently randomized skill trials.

Create or select a skill for each role, upload Markdown, or write a custom skill.
AI-assisted drafting is available for the Hypothesis Agent and produces editable
instructions. Other roles support manual writing and Markdown upload. Review and save
the result before applying the surrounding pipeline settings; drafting does not
start a pipeline. Data instructions must preserve fixed-target, exact-column
extraction. Creating a pipeline and starting it remain separate actions.

## Measurements and Results

The workspace presents model evaluation, feature contributions, measured
observations, and the final explanation. Interpretation keeps observed findings
separate from speculation; Explanation distinguishes observations from proposed
clinical or biological meaning and next steps requiring validation.

`config.json` freezes settings and selected prompts. Per-Loop
`loop_N_flavors.json` records planned skills and their content hashes;
`execution.json` records actual calls and their order. The Loop selector
separates planned combinations from calls that ran. Missing or blocked stages
must not be interpreted as completed work.

The configured outcome column is a label and never a predictor. Keep the target consistent between dataset,
matcher, and evaluation. Scores and feature importance describe the configured
experiment; they are not evidence of a causal effect.

In the paired workflow, an independent validation reserve is set aside before
Data divides the exploration population into training and evaluation partitions.
Saved evaluation metrics and confusion matrices describe their recorded partition;
a reserve marked `reserved_not_evaluated` has no independent-validation results.
Check the split indices and evaluation provenance before comparing runs. See the
[artifact audit](DEVELOPER_GUIDE.md#read-and-verify-an-execution).

## Everyday commands

Run these from the Memstara checkout with the `memstara` environment active:

```bash
python -m memstara.trace.board --last 3 --summary   # inspect recent runs
docker compose -f viewer/docker-compose.yml logs -f api
docker compose -f viewer/docker-compose.yml up -d --build web
```

Use the workspace's pause/resume and end controls to manage executions. Stop
and rebuild services separately from pipeline execution; the driver may outlive
its control-service process. Back up both databases before infrastructure or
schema upgrades. A viewer rebuild does not apply Motoro database migrations.

## Requirements and configuration

| Setting | Purpose |
|---|---|
| `MOTORO_DATABASE_URL` | Motoro's agent and run database |
| `MEMSTARA_DATABASE_URL` | Memstara's board and results database |
| `AGENTIC_OKF_BUNDLE_DIR` | OKF corpus; the legacy prefix is required |
| `MEMSTARA_DATASET_PATH` | Cohort CSV |
| `MEMSTARA_OUTPUT_DIR` | Generated subsets and matcher artifacts |
| `MEMSTARA_OUTCOME_COLUMN` | Target excluded from matcher and data feature lists |
| `MEMSTARA_LLM_PROVIDER`, `MEMSTARA_LLM_MODEL` | Deployment default; explicit stage profiles override agent assignments |
| `MEMSTARA_LLM_API_BASE` | Optional configured provider endpoint |

See [.env.example](.env.example), [config.py](src/memstara/config.py), and
[request.py](src/memstara/control/request.py) for the configuration contract.
The example service ports are 5463 (Memstara PostgreSQL), 5453 (Motoro PostgreSQL),
6381 (Redis), and 8070–8072 (workspace, observation API, control).

The board CLI supports `--trials` (default 3), `--waves`, `--continuous`,
`--y-column`, `--run-tag`, worker counts, `--max-attempts`, `--stale-after`,
`--resume`, and `--report-only`. Use `python -m memstara.pipeline.board --help`
for the complete interface. `--skill` filters the knowledge corpus;
`--playbook-<stage>` selects instruction text. `--playbook-explanation` and
`--playbook-report` address the same compatibility stage.

## Developer operations

See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for stage-model profiles, configuration
precedence, control API examples, restart/recovery procedures, agent contracts,
artifact verification, and troubleshooting. It documents current routing limits
and distinguishes exploration evaluation from independent validation.

## Development

Use Python 3.12 or 3.13 and a separate test environment so synchronizing test
dependencies does not replace the application runtime. First check that dependency
metadata and the lockfile agree:

```bash
uv lock --check
```

If dependency declarations changed, regenerate with `uv lock`, review the resulting
lockfile diff, and include it with the dependency change before using `--frozen`.
A frozen install uses the existing lockfile; it does not incorporate new declarations.
Then run:

```bash
export UV_PROJECT_ENVIRONMENT=.venv-test
uv sync --frozen --extra dev --extra runtime
uv run --frozen --extra dev --extra runtime ruff check src/
uv run --frozen --extra dev --extra runtime lint-imports
uv run --frozen --extra dev --extra runtime pytest -q --cov --cov-report=term --cov-report=xml
uv run --frozen --extra dev --extra runtime python scripts/check_public_tree.py
uv run --frozen --extra dev --extra runtime python scripts/check_markdown.py
```

CI runs the following checks on every push and pull request:

| Check | Scope |
|---|---|
| Python unit and component tests | Configuration, model evaluation, pipeline logic, API helpers and regression contracts |
| MCP protocol test | Real subprocess startup, handshake and synthetic data tool calls |
| PostgreSQL integration | Schema reapplication, concurrent claims, run locks and measured-result persistence |
| Python import boundaries | Dependency direction between foundational, matching and orchestration modules |
| Python type and format diagnostics | Mypy must pass; Ruff formatting remains advisory while existing formatting findings are addressed |
| Frontend unit tests | Evaluation settings, metrics, loop labels, routing, start behavior and geometry |
| Frontend type, lint and build | TypeScript project references, Oxlint and production assets |
| Browser regression tests | Isolated fixtures for pipeline configuration, combinations, navigation and responsive layouts |
| Distribution checks | Source/wheel builds, packaged prompts and installed version metadata |
| Publication checks | Tracked-file hygiene and Markdown links |

Coverage and JUnit reports, browser reports and distributions are saved as CI
artifacts. Coverage is measured without excluding untested application modules;
there is no claim of full coverage or validated clinical performance.

For the database tests, start the dedicated disposable service and supply its
URL explicitly. Tests refuse a database whose name does not end in `_test` and
create a fresh schema for each test.

```bash
docker compose -f compose.test.yml up -d --wait
MEMSTARA_TEST_DATABASE_URL=postgresql://memstara_test:memstara_test@127.0.0.1:55473/memstara_test \
  uv run --frozen pytest tests/integration --run-integration -q
docker compose -f compose.test.yml down
```

Frontend checks require Node.js 22.18 or newer:

```bash
cd viewer/web
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:browser
```

The browser suite starts its own static server on port 4175 with no backend
proxy. Fixtures supply API responses; these tests do not start real research
pipelines or make paid model calls. The deployment diagnostics
`app-ux-audit.browser.mjs` and `telemetry-live.browser.mjs` require an existing
running application and are excluded from automated fixture tests. Live provider,
external dataset and embedding-model validation remain deployment checks.

Build and verify distributions from a clean checkout:

```bash
uv run --frozen python -m build
uv run --frozen python scripts/check_distribution.py
```

Run Python entry points as `python -m memstara.<module>`. Load configuration
before runtime use, following the existing entry points. Agent prompts live in
`src/memstara/prompts/`; prompt changes are experimental conditions and should
be reviewed separately from code changes. Track development through
[GitHub issues](https://github.com/HyunjunA/memstara/issues).

## Resetting your dev environment

Stop only the viewer while keeping data:

```bash
docker compose -f viewer/docker-compose.yml down
```

Memstara and Motoro use separate databases and volumes. Removing a database
volume deletes its stored work; resetting Motoro can also affect other products
using that runtime. Back up both databases and verify which volumes belong to
the deployment before resetting them.

## Stage-specific model configuration

Use [config/stage-models.example.json](config/stage-models.example.json) as a
credential-free template. Copy it to `config/stage-models.local.json` (gitignored),
or set `MEMSTARA_STAGE_MODELS_PATH` to your deployment profile file. Replace the
placeholder deployment names and endpoints before starting a run.

The `non_explanation_agents` profile serves question generation, Hypothesis, Data, ML and both
Interpretation specialists. The `explanation_agent` profile serves both Explanation experts.
For Claude on Foundry use `azure_foundry` and the resource base URL. Credentials
remain in Motoro's runtime credential resolver; never include keys in profile JSON.
Connection preflight checks both profiles without sending inference.

A pipeline's nonempty `configuration.stage_models` overrides deployment defaults.
Update saved pipeline definitions through `/control/pipelines`; changing defaults
does not replace an already saved assignment. New executions freeze profiles before
provisioning. Resume and report recovery preserve the original assignment or reject
an incompatible request; neither silently selects a different model. Transport
retries retain the same stage model. Historical run files must not be edited.

Settings → Model connection shows defaults, saved next-execution assignments and
frozen active assignments separately. These are deployment identities; actual call
traces establish which model was invoked. Missing pricing remains unavailable.
LR and XGBoost are predictive learners, distinct from these LLM agents.
