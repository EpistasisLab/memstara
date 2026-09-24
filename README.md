# Memstara

[![CI](https://github.com/HyunjunA/memstara/actions/workflows/ci.yml/badge.svg)](https://github.com/HyunjunA/memstara/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-%E2%89%A53.12-3776AB?logo=python&logoColor=white)](pyproject.toml)

A **multi-agent research workbench** that reads a literature corpus, proposes
predictors of a clinical outcome, evaluates them against a cohort, and explains
the results. A shared PostgreSQL board records each stage's work; MCP tools
connect the agents to the literature, dataset, semantic matcher, and ML evaluator.

Memstara builds on [Motoro](https://github.com/EpistasisLab/motoro) as an
in-process library for agent execution, model calls, MCP integration, and runtime
persistence. Memstara adds the research pipeline, its own database, a host control
service, and a browser workspace. Motoro and Memstara own separate databases.

## Releases and development

Memstara is under active development. The package declares version `0.1.0`
in [pyproject.toml](pyproject.toml); that number alone does not identify a tested
application release. Record both repositories' commits when reproducing a run:

```bash
git rev-parse HEAD
git -C ../motoro rev-parse HEAD
```

[environment.yml](environment.yml) installs both repositories in editable mode.
Updating the adjacent Motoro checkout therefore changes the runtime used by
Memstara without reinstalling it. Validate a new pair of revisions before using
it for a study; preserve run configuration, prompt snapshots, and data provenance.

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

You need **Git, Conda with Python 3.12, Docker with Compose**, a supported LLM
credential, and access to the private Memstara repository. Motoro requires its
own PostgreSQL database and Redis; Memstara's root Compose file starts only its
own PostgreSQL service.

**1. Prepare the sibling checkouts and Python environment.** For a new workspace:

```bash
git clone https://github.com/EpistasisLab/motoro.git motoro
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

**2. Prepare the databases and Redis.** On a new host, follow
[Motoro's setup](https://github.com/EpistasisLab/motoro#development) to provision
its services and apply its migrations. Then, from the Memstara checkout:

```bash
docker compose up -d
docker compose ps
```

**3. Configure the connection and research inputs.** Set the deployed provider
and model in `../motoro/.env`. The board driver resolves the deployment-wide
selection through the control configuration; its legacy `--provider` and
`--model` flags are not independent overrides. Provide the credentials required
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
model downloads. The synthetic corpus includes absent-variable decoys and
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

**Selected Pipelines** configures and runs one saved pipeline at a time.
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
| `MEMSTARA_LLM_PROVIDER`, `MEMSTARA_LLM_MODEL` | Deployment-wide LLM selection |
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

## Development

```bash
ruff check src/
python -m pytest -q -ra
python scripts/check_citations.py
python scripts/check_markdown.py

# Frontend (Node.js 22), in a separate terminal from the repository root:
cd viewer/web
npm ci
npm run build
```

Backend CI runs lint, pytest, citation checks, and tracked Markdown link checks. Runtime-dependent tests can
skip when Motoro is absent; read the skip reasons. These checks do not certify
live database, MCP, or paid model execution. Citation checks verify that a cited
location exists, not that it supports the claim. Read the current command output
rather than relying on a test count embedded in this document.

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
