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

For file/function review, use [REVIEW_GUIDE.md](REVIEW_GUIDE.md). Release content
and remaining approval gates are tracked in [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

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
New workspace designs use `shared-anil-addiction` for Explanation and
`shared-anil-shap` for Interpretation. Historical configurations remain readable;
disabled selections may require updating before a new execution.
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

Repository-local study inputs use the [resource layout](resources/README.md).
Agent instructions remain package resources; generated artifacts remain in `outputs/`.

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

This section contains the complete local setup: install Memstara and Motoro,
start two databases and Redis, configure your model, select data and knowledge,
register skills, run one pipeline, and open the browser workspace. Run commands
from the repository root unless a step says otherwise. Do not use the authors'
private folders or copy an existing database to complete this procedure.

**Included examples:** synthetic CSV/OKF under `examples/research-inputs/` and
supplied HeartFailure CSV/OKF under `examples/heart-failure/` are tracked and
arrive with a clone of this revision. Private HIV inputs and local research
materials under `resources/` remain excluded. See the HeartFailure
[provenance and preparation guide](examples/heart-failure/README.md).
Project licensing and third-party redistribution decisions remain separate from
installation acceptance; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### 1. Install a pinned checkout and Python environment

Prerequisites: Git, uv, Python 3.12 or 3.13, Docker with Compose, internet access
for dependency/model downloads, and credentials for your own LLM deployment.
Node.js 22 is needed only for the local browser setup below. The examples use a
POSIX shell on macOS/Linux. Keep the code, data and cache on a local writable disk.

```bash
git clone --branch experiment/agent-combinations-pilot https://github.com/HyunjunA/memstara.git
cd memstara
git rev-parse HEAD
uv sync --frozen --extra dev --extra runtime --python 3.12
source .venv/bin/activate
python -c "from importlib.metadata import version; print('Memstara:', version('memstara')); print('Motoro:', version('motoro'))"
```

If you already cloned the intended branch, enter that checkout and start at
`git rev-parse HEAD`; do not clone a second nested copy. Before continuing, confirm
that the installed revision includes the files used by this walkthrough:

```bash
python - <<'PYCODE'
from pathlib import Path
required = [
    'scripts/prepare_research_tutorial.py',
    'scripts/prepare_heart_failure_demo.py',
    'examples/research-inputs/research.json',
    'examples/research-inputs/skills/hypothesis.md',
    'examples/research-inputs/skills/explanation.md',
    'src/memstara/resources/contributed/anil',
]
missing = [name for name in required if not Path(name).exists()]
if missing:
    raise SystemExit('Incomplete installation revision: ' + ', '.join(missing))
print('Walkthrough files present')
PYCODE
```

If this fails, stop and obtain the complete reviewed revision. Copying only this
README into an older checkout does not supply the required code or skills.

Record the printed commit. For a released version, select its reviewed tag instead
of the development branch. `uv sync` installs Motoro **v0.10.0**, pinned to commit
`bd0b461c3b2eaef1b1f5c54cc18027647d01cb58`, and LiteLLM **1.97.0**.
No sibling Motoro source checkout is needed. Keep the same extras if using `uv run`;
otherwise synchronization can remove runtime dependencies. Do not run `uv sync` in
an existing environment that you intend to preserve.

### 2. Configure this installation in one project `.env`

In a fresh checkout, run `cp .env.example .env` and edit that file. If `.env` already
exists, preserve it and edit the existing assignments. Do not source the file or
edit `.zshrc`. No sibling project's `.env` or separate model JSON is required.
The file accepts literal values; shell `${...}` interpolation is not supported.

| Settings | Required action |
|---|---|
| `MEMSTARA_LLM_PROVIDER`, `MEMSTARA_LLM_MODEL` | Choose the provider and your actual deployed model |
| `ANTHROPIC_FOUNDRY_RESOURCE`, `ANTHROPIC_FOUNDRY_API_KEY` | Obtain your resource name and authorized key for Foundry |
| `MEMSTARA_LLM_API_BASE` | Optional Foundry resource-root URL; it can replace the resource name, and both must agree if set |
| `MEMSTARA_DATABASE_URL`, `MOTORO_DATABASE_URL`, `MOTORO_REDIS_URL` | Select independent service destinations; preserve existing values when migrating |
| `MEMSTARA_COMPOSE_PROJECT` | Choose a unique name for a new Docker installation |
| `MEMSTARA_WEB_PORT`, `MEMSTARA_API_PORT`, `MEMSTARA_CONTROL_PORT` | Choose free ports; launcher and web proxy use these same values |
| `MEMSTARA_VIEWER_DSN`, `CORE_VIEWER_DSN` | Read-only database accounts for the observation API |
| `MEMSTARA_OUTPUT_DIR`, `HF_HOME` | Tool output and model-cache directories |

One default model serves all stages. For example:

```dotenv
MEMSTARA_LLM_PROVIDER=azure_foundry
MEMSTARA_LLM_MODEL=YOUR_DEPLOYMENT_NAME
ANTHROPIC_FOUNDRY_RESOURCE=YOUR_RESOURCE_NAME
ANTHROPIC_FOUNDRY_API_KEY=YOUR_API_KEY
```

To use another model for Explanation, set `MEMSTARA_EXPLANATION_MODEL` in the same
file. Optional `MEMSTARA_EXPLANATION_PROVIDER` and `MEMSTARA_EXPLANATION_API_BASE`
select its provider/endpoint. `MEMSTARA_NON_EXPLANATION_*` overrides the other group
(Question, Hypothesis, Data, ML, Interpretation). Credentials remain provider
settings; selecting an endpoint does not grant access to it. See `.env.example`
for optional generation limits. Internal profiles are built in memory.

```bash
python -m memstara.local_setup check
```

This is a **static configuration check**, not a database connection or paid model
call. It reports source, model identities, ports and missing requirements without
credential values. `model_call: not_tested` must not be interpreted as connected.
Designs can be saved before model setup is complete; execution requires model
configuration and credentials. Local file settings override managed shell values;
omissions are not silently filled from shell or sibling files. Relative paths
resolve from the `.env` location, not from the launching terminal directory.

Use **relative filesystem paths** in `.env` so moving or cloning the installation
does not retain another computer's home directory. For example:

```dotenv
MEMSTARA_OUTPUT_DIR=outputs
HF_HOME=outputs/huggingface
# Optional deployment inputs, if not using a saved research profile:
# MEMSTARA_DATASET_PATH=outputs/heart-failure-demo/dataset.csv
# AGENTIC_OKF_BUNDLE_DIR=examples/heart-failure/okf
# MEMSTARA_OUTCOME_COLUMN=chronic_heart_failure
```

Create the HeartFailure analysis CSV with the preparation command in step 4 before
enabling its dataset default; the supplied raw CSV is not the prepared analysis
CSV. Custom input and skill paths follow the same rule. Keep those files inside
the checkout when portability is required. Do not copy private HIV data or API
credentials into Git. A fresh clone includes the tracked examples and packaged
skills, but not your ignored files, saved research registrations, or execution
history; prepare/register the chosen study again on the new installation.

API endpoints and database/Redis connection strings are **URLs**, not filesystem
paths; retain their full scheme and address and configure them for the new machine.
The application resolves filesystem paths to absolute paths internally for child
processes and execution records. That does not require absolute paths in `.env`.

The default file is this checkout's `.env`. `MEMSTARA_ENV_FILE=/absolute/path/.env`
explicitly selects another installation file. For CI or supervised deployment,
`MEMSTARA_CONFIG_MODE=environment` explicitly selects injected environment values
instead of reading any file. Do not use that mode to bypass a missing local setting.
Restart services after changing settings; active runs keep process/frozen settings.

### 3. Start independent databases and initialize schemas

After choosing free database/Redis ports and a unique project name in `.env`:

```bash
python -m memstara.local_setup services
```

This provisions two PostgreSQL services (Motoro uses pgvector) and Redis. It binds
only loopback, generates a restricted local Compose definition under the configured
output directory, and refuses occupied ports or an existing project's containers
or volumes. It does not stop another installation or adopt its data automatically.
Do not use the repository's legacy bare `docker compose up -d` for this workflow.

Inspect health using the generated file (adjust `outputs` if you changed it):

```bash
docker compose -f outputs/local-runtime/compose.json ps
```

Wait for both PostgreSQL services to be healthy, then initialize:

```bash
python -m memstara.local_setup init
```

For a previously created installation, inspect its existing Compose definition
and use it to start/stop its services; `services` is a guarded **new provisioning**
command. Changing a password in `.env` does not rotate an existing PostgreSQL role.
Deleting the checkout does not delete Docker volumes. Do not use `down -v` unless
you intend to delete those databases.

#### Migrate an existing model JSON

Preserve your existing DB/Redis/data/output locations. Import model assignments
explicitly (the command creates a restricted backup under `outputs/`):

```bash
python -m memstara.operational migrate-models --from-json config/stage-models.local.json
python -m memstara.local_setup check
```

The importer does not copy shell credentials. Transfer your authorized provider
credentials to project `.env` after checking that they belong to the configured
resource. Remove `MEMSTARA_STAGE_MODELS_PATH` from the selected configuration and
restart the affected services. Do not delete shell settings used by other projects
until those projects have their own configuration. Roll back using the restricted
backup and the preceding code revision; never replace historical run artifacts.
A saved design with explicit models differing from the project is rejected on a
new start: explicitly clear its `stage_models` to adopt project settings. Historical
resume retains its frozen models and uses current credentials for that target.

### 4. Choose and prepare one research input

Choose **A or B** for the first execution. Registration does not call the model.
Do not combine one dataset with an unrelated corpus by accident.

**A. Included synthetic example — no separately supplied dataset needed**

```bash
python -m memstara.research_inputs inspect examples/research-inputs/research.json
python scripts/prepare_research_tutorial.py examples/research-inputs/research.json > outputs/launch.json
```

This contains 120 generated rows, four predictors and the binary `simulated_event`
outcome. Its OKF is invented educational material, not clinical evidence.

**B. Included HeartFailure demonstration — no separate input download**

The clone contains the original supplied CSV and complete OKF hierarchy:

| Material | Included location |
|---|---|
| Supplied HeartFailure CSV | `examples/heart-failure/dataset.csv` |
| Complete HeartFailure OKF | `examples/heart-failure/okf/` |
| OKF entry point | `examples/heart-failure/okf/index.md` |
| Integrity inventory | `examples/heart-failure/manifest.json` |

The target is `chronic_heart_failure`, with positive label `1` and negative label
`0`. The command below generates `research.json` with the target description,
labels and dataset/corpus paths, together with the separate analysis CSV.
Do not use the raw CSV directly: it contains missing values. The original tracked
inputs remain unchanged. No private HIV input or adjacent contributor folder is needed.

```bash
python scripts/prepare_heart_failure_demo.py \
  --source examples/heart-failure/dataset.csv \
  --corpus examples/heart-failure/okf \
  --destination outputs/heart-failure-demo
python -m memstara.research_inputs inspect outputs/heart-failure-demo/research.json
python scripts/prepare_research_tutorial.py outputs/heart-failure-demo/research.json > outputs/launch.json
```

The script selects eight fixed predictors: age, sex, prior myocardial infarctions,
hypertension stage, diabetes history, obesity history, chronic bronchitis history,
and asthma history. It retains rows with complete values on those predictors;
it does **not** impute or modify the original. For the inspected supplied file,
1,671 of 1,700 rows remained, with 29 excluded. `preparation.json` records both
hashes, the selection and counts. Existing destination directories are rejected;
choose another destination for a new preparation rather than overwrite evidence.

The target is the supplied `chronic_heart_failure` indicator (1 positive, 0 negative).
The generated contract explicitly labels endpoint timing and horizon as unverified.
This is a software demonstration with possible complete-case selection bias, not
validated prospective clinical prediction. The raw CSV cannot pass the current
reject-missing-values policy unchanged.

**C. Your own CSV / OKF / target**

Use this route to replace the example with your study. Your model connection and
DB/Redis services are configured in steps 2–3; the research JSON below selects
scientific inputs, not cloud credentials. You do not need to edit Python source
or contributor skill files to change the dataset, corpus or target.

#### Choose an included example or a personal study

| Choice | CSV and knowledge | What you configure |
|---|---|---|
| Synthetic tutorial (A) | Included under `examples/research-inputs/` | Use its existing JSON and preparation command |
| HeartFailure (B) | Included under `examples/heart-failure/` | Run the documented preprocessing; it generates the analysis CSV and target JSON |
| Personal study (C) | Your analysis-ready CSV and your OKF directory | Create a research JSON with your paths, labels, timing and exclusions |

Both included examples arrive with the repository. API credentials are always
provided by the user. Keep the supplied examples unchanged so they remain useful
for checking an installation; work on a personal copy for modifications.

#### Prepare a local study directory

The following creates a working copy of the **synthetic** example so the commands
can be tried before supplying any personal data. It does not make it clinical data.
Use a new directory name if this one already exists; do not overwrite a prior study.

```bash
mkdir outputs/my-study
cp examples/research-inputs/dataset.csv outputs/my-study/dataset.csv
cp -R examples/research-inputs/okf outputs/my-study/okf
cp examples/research-inputs/research.json outputs/my-study/research.json
```

The intended layout is:

```text
outputs/my-study/
├── dataset.csv
├── research.json
└── okf/
    ├── index.md
    └── observations/
        └── simulated-risk.md
```

`outputs/` is ignored by Git. You can instead use a directory outside the repository
if the host process and its child processes can read it. In the browser, paths refer
to the machine running Memstara's control service, not an arbitrary file on a remote
browser user's computer. Entering a path does not upload the file.

#### Prepare the CSV and define the prediction target

Provide one header row, one observation per subsequent row, and distinct column
names. Current dataset mode supports a binary outcome and at least four eligible
predictors, with a 100 MiB CSV limit. Use a target name beginning with a letter or
underscore and containing only letters, digits and underscores (maximum 64 characters).

| Check | What the user must decide |
|---|---|
| Outcome column | The exact CSV header to predict, not a feature |
| Positive/negative labels | The two exact observed values; for example `event`/`no_event` or `1`/`0` |
| Prediction time | When a prediction would be made and which predictors are already available |
| Horizon | How far after prediction the outcome is measured; describe uncertainty explicitly |
| Exclusions | Record identifiers and variables that reveal the outcome or are measured too late |
| Missing values | Explicitly clean a separate analysis copy before registration; generic input mode rejects missing values |
| Data types and class sizes | Supply analysis-ready predictors and enough observations in each class for the selected split/evaluation |

Keep the original dataset. Do not rename missing targets into the negative class,
infer labels from their order, or include the target among predictors. Inspection
checks input structure and some feasibility conditions; passing it does not establish
clinical validity, absence of leakage or suitability of every evaluation setting.
The HeartFailure preprocessing rule is specific to that demonstration and is not an
automatic cleaning policy for personal datasets.

#### Create or supply the OKF corpus

Select the directory that directly contains `index.md`, not its parent. A minimal
working bundle needs the root index and at least one usable evidence document
inside a non-hidden domain subdirectory. For example:

```text
okf/
├── index.md                       # describes corpus scope
├── observations/                 # one searchable domain
│   ├── index.md                   # optional domain description
│   └── baseline-measurements.md   # evidence document
└── mechanisms/                   # another optional domain
    └── mechanism-example.md
```

The directory names become domain names. Documents can be nested further inside
a domain. The loader skips `index.md` as evidence and does not load evidence placed
only at the bundle root. Top-level directories starting with `.` or `_` are skipped.
Copying only `index.md` therefore does not provide a usable corpus.

A minimal evidence document uses YAML front matter with a non-empty `title` and a
Markdown body. This example is intentionally invented educational content:

```markdown
---
id: simulated-baseline
title: Simulated baseline predictors
tags: [synthetic, tutorial]
---

# Simulated baseline predictors

This is invented software-testing material, not medical evidence.
The generated systolic_pressure, resting_pulse, activity_score and
synthetic_marker values are available at simulated baseline. Investigate
their association with the later simulated_event; do not infer clinical
causation or real-world measurement units.
```

`id` and `tags` provide useful metadata; `title` is required by the loader. For a
real study, replace the invented body with authorized, source-grounded material:
cite the publication or source, describe the population and outcome, state the
finding and limitations, and identify concepts that can map to available CSV columns.
A variable mentioned in a paper is not automatically available in your dataset.
Do not rename an unsupported filter category to a topic word; searchable domains
and available metadata values come from the actual supplied corpus.

A folder of PDFs, an arbitrary website URL, or CSV alone is not an OKF bundle. This
path does not automatically extract papers into OKF. Prepare readable Markdown
before inspection. Keep relative links and supporting corpus files together; paths
and symlinks must not escape the selected knowledge root. For an existing exported
OKF such as HeartFailure, preserve its complete directory structure.

#### Write the research configuration

Replace the contents of `outputs/my-study/research.json` with the following complete
configuration for the copied synthetic example. When using real materials, change
all applicable paths and target semantics, not just the study name:

```json
{
  "name": "My synthetic installation check",
  "knowledge_mode": "okf",
  "data_mode": "dataset",
  "dataset_path": "outputs/my-study/dataset.csv",
  "knowledge_path": "outputs/my-study/okf",
  "target": {
    "column": "simulated_event",
    "description": "Predict the generated toy event. This is not a clinical endpoint.",
    "positive_label": "event",
    "negative_label": "no_event",
    "prediction_time": "All four generated predictors are available at simulated baseline",
    "horizon": "One simulated follow-up interval; no real-world duration"
  },
  "excluded_columns": ["record_id"],
  "missing_policy": "reject"
}
```

| Setting | Meaning |
|---|---|
| `name` | Human-readable study name |
| `dataset_path` | Selected CSV, not its directory |
| `knowledge_path` | OKF root containing `index.md` and domain directories |
| `target` | Outcome definition, exact labels and predictor/outcome timing |
| `excluded_columns` | CSV columns that must not be offered as predictors |
| `missing_policy` | Currently `reject`; it does not request automatic imputation |
| `knowledge_mode`, `data_mode` | Explicit choices described in the next table |

Relative paths resolve from the process working directory, **not the JSON file's
directory**. Run these commands from the repository root. Absolute paths are
recommended for personal data or when starting services from different directories.
The examples above deliberately use root-relative paths. Keep deployment credentials and model assignments in `.env`; neither belongs
in the research JSON. Select the saved research profile when running: changing only
legacy dataset environment variables does not replace an already registered profile.

#### Inspect, register and execute your selected inputs

```bash
python -m memstara.research_inputs inspect outputs/my-study/research.json
python scripts/prepare_research_tutorial.py outputs/my-study/research.json > outputs/launch.json
```

Check `input_checks_passed: true`, an empty `issues` list, expected row/class counts,
and a nonzero number of knowledge documents for OKF mode. If inspection fails,
correct the source or configuration and inspect again; do not launch despite errors.
The preparation command saves the research version and separate tutorial user skills.
It prints their IDs and `next_command` into `outputs/launch.json`; it does not execute
that command. `execution_ready: false` means model/runtime readiness has not been
certified by registration, not that a successful input inspection failed.

Continue with steps 5 and 6 using that launch file. Step 6 makes real model calls.
Use a new run directory and log filename for each new attempt. For a new research
domain, review the tutorial Hypothesis/Explanation instructions and create reviewed
user skills if needed; do not modify the supplied Anil/Phil originals. Do not select
unrelated Addiction/HIV specialists for a generic profile.

Alternatively, after step 7 has started the UI, use **Floor plan → Prepare research
inputs**, enter the corresponding paths and target details, inspect and save a
version. Select that version when adding a pipeline and choose compatible skills.
Review existing source filters and feature/baseline settings after changing studies.
Saving an input version or pipeline configuration does not start the experiment.

Changes to CSV/OKF contents or target meaning require inspection and a new saved
version; do not silently reuse an old registration or overwrite its generated
analysis copy. Historical executions retain their frozen input and configuration
records. A changed live model configuration similarly applies to newly started
processes, not to an existing execution.

#### Run with only some of the inputs

| Available sources | `data_mode` | `knowledge_mode` | Output |
|---|---|---|---|
| CSV + OKF | `dataset` | `okf` | Models, measured results and source-grounded explanation |
| CSV only | `dataset` | `llm_only` | Models and measured results without external grounding |
| OKF only | `proposal` | `okf` | Research/data/analysis proposal, no fitted model or measured metrics |
| Neither | `proposal` | `llm_only` | Proposal based on unverified model knowledge |

For proposal mode, a target description is still required. Select modes explicitly;
a missing selected source does not silently switch modes. To inspect/register any
of these modes, use `python -m memstara.research_inputs inspect CONFIG.json` and the
same tutorial preparation command. Changed source contents require a new registration.

### 5. Understand the skills used by this execution

The original specialty experiment uses 12 choices (4 × 2 × 2 × 2 × 2 = 64
combinations). Two additional general-research skills support other domains. A
registered research profile cannot silently use an unrelated
Addiction/HIV specialty. The tutorial registers separate, versioned user skills
for Hypothesis and Explanation. It does not enable retired skills or edit originals.

| Role | Normal catalogue | First-run tutorial selection |
|---|---|---|
| Hypothesis | Psychiatric, social determinants, substance use, random features | User research tutorial, from `examples/research-inputs/skills/hypothesis.md` |
| Data | Training-heavy or balanced stratified | `data_training_heavy` |
| ML | LR or XGBoost | `ml_logistic_regression` |
| Interpretation | Anil SHAP or LIME | `shared-anil-shap` |
| Explanation | Anil Addiction or HIV | User research tutorial, from `examples/research-inputs/skills/explanation.md` |

Project skills are under `src/memstara/playbooks/`; common system prompts are under
`src/memstara/prompts/`. The four Anil originals and two Phil documents have internal
copies under `src/memstara/resources/contributed/`. Phil's ML Knowledge is additive
background; the legacy ML Skill report selection remains disabled. No adjacent
contributor folders are discovered automatically. Explicit skill-path overrides
remain supported. If a required packaged document is missing, install a complete
candidate revision; do not silently fall back to an unrelated archived skill.

`outputs/launch.json` contains the saved research ID, tutorial skill IDs and a
one-Loop command. `execution_ready: false` at this preparation stage means that
runtime/model execution has not yet been validated; it is not an execution failure.

### 6. Execute one Loop and check completion

This step makes real provider calls and can incur charges. Do not also press Start
in the UI for the same intended test. The commands below run the saved launch
configuration with a bounded evaluation and preserve the log and exit status:

```bash
python - <<'PY'
import json, shlex, subprocess, sys
from pathlib import Path
run = Path('outputs/runs/first-demo').resolve()
if run.exists():
    raise SystemExit('Use a new run path; do not overwrite an earlier execution')
launch = json.loads(Path('outputs/launch.json').read_text())
argv = shlex.split(launch['next_command'])
argv[0] = sys.executable
argv += ['--run-dir', str(run), '--max-attempts', '5', '--baseline-columns', '[]',
         '--evaluation', json.dumps({'engine': 'xgboost', 'seed': 42,
             'test_size': .25, 'folds': 0, 'replicates': 1, 'search_trials': 1})]
with Path('outputs/first-demo-driver.log').open('w') as log:
    result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT)
print('Exit code:', result.returncode)
raise SystemExit(result.returncode)
PY
```

In another terminal, follow `tail -f outputs/first-demo-driver.log` or, once it
exists, `tail -f outputs/runs/first-demo/console.log`. Initial model downloads and
matcher preparation can precede stage messages. Do not start a second execution
merely because the first is preparing its inputs.

After the process exits:

```bash
python - <<'PY'
import json
from pathlib import Path
run = Path('outputs/runs/first-demo')
status = json.loads((run / 'pipeline_status.json').read_text())
assert status['status'] == 'completed', status
assert status['report_completed'] and not status['unfinished_task_ids'] and not status['missing_trials']
assert (run / 'report.md').stat().st_size > 0
print('Completed; report saved at', run / 'report.md')
PY
```

| Saved artifact | What to check |
|---|---|
| `config.json` | Frozen inputs, selected skills, model profiles and settings |
| `execution.json` | Stage status and durations |
| `iteration_outcomes.json`, `pipeline_status.json` | Actual Loop and final completion |
| `report.md`, `report_status.json` | Persisted Explanation |
| `trace/`, `console.log` | Agent/tool evidence and errors |
| `cost_ledger.jsonl`, `model_retries.jsonl` | Provider usage and retries, when present |
| `registry_status.json` | Synchronization into the experiment registry |

Saved token-price estimates are not actual Azure billing. No billing response or
no run-level attribution means actual execution cost is unconfirmed, not zero.
A completed Loop does not prove that every combination or future provider call
will succeed. Retry recovery must not be reported as error-free execution.

### 7. Open the browser workspace (optional after CLI acceptance)

For the custom ports above, use the local viewer path below. The existing
`viewer/docker-compose.yml` has literal default database ports (5463/5453) and
container names; do not start it against this stack without adjusting those values.
The API must use read-only accounts, while the host control retains write access.

Create a viewer role on **each** new database server (once per server). Enter
`viewer` at the password prompt for these loopback-only development examples:

```bash
docker compose -f outputs/local-runtime/compose.json exec board psql -U memstara -d memstara
```

Inside psql:

```sql
CREATE ROLE memstara_viewer LOGIN;
\password memstara_viewer
GRANT CONNECT ON DATABASE memstara TO memstara_viewer;
GRANT USAGE ON SCHEMA public TO memstara_viewer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO memstara_viewer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO memstara_viewer;
\q
```

Repeat using `exec runtime psql -U motoro -d motoro` and replace the database
name in `GRANT CONNECT` with `motoro`. Keep the grants as the respective database table
owner so future tables are readable too. Do not use the owner account for the viewer.

Install the separate observation API environment and frontend:

```bash
python -m venv viewer/.venv
uv pip install --python viewer/.venv/bin/python -r viewer/requirements.txt
npm --prefix viewer/web ci
```

Use the DB users/databases from your `.env` when executing these commands; the
examples use `.env.example` defaults. The viewer password must match both configured
read-only DSNs. Services refuse occupied ports rather than silently selecting another.

Check real database/Redis connectivity and the viewer accounts before launch:

```bash
python -m memstara.local_setup connections
```

This sends database read probes and Redis PING; it makes no model call. The API
launcher rejects viewer accounts with detected table-write or administrator
privileges. A static `check` pass alone does not prove service connectivity.

Start three terminals from the repository root, with `.venv` activated:

```bash
python -m memstara.local_setup control
```

```bash
python -m memstara.local_setup api
```

```bash
python -m memstara.local_setup web
```

Open `http://localhost:<MEMSTARA_WEB_PORT>` (5173 by default). The launcher forwards
only ports to Vite and only read-only database settings to the API. Web proxy targets
and the control service's local origin allowance follow the selected ports. You do
not edit Vite config or export separate DSNs. An occupied port stops startup; choose
a free port in `.env` and restart the relevant services.

In Floor plan, choose **Add pipeline**, select the research version saved in step 4,
select the tutorial Hypothesis/Explanation skill IDs printed in `outputs/launch.json`,
and use the remaining choices from step 5. Set one Loop initially. Creating a
pipeline saves settings; Start executes it. Do not replay the already completed CLI
run merely to view its results. Restart the control process between executions after
changing environment settings; a running worker retains its frozen configuration.

The CLI pipeline acceptance and the frontend build/unit checks were verified
separately. This README does not claim a fresh interactive browser acceptance of
the custom-port stack. The workspace has no production login/authentication layer;
these instructions bind development services to loopback.

### Select HIV or HeartFailure from Knowledge sources

In Add pipeline, the **Knowledge sources · research study** selector lists saved
research versions. In an existing Selected Pipeline, open its Knowledge sources card;
in All Combinations, use the Knowledge sources button. Select a study and save.
Its corpus, dataset, outcome column and label mapping move together. Corpus scope
is a separate optional filter within the deployment default corpus.

The included HeartFailure files become a selectable study after the documented
preparation and registration commands above. HIV files remain local/private; their
study must be registered on the machine that has them. A private study registration
is not distributed by Git. Input checks do not certify clinical timing or target
semantics. Retain explicit unknowns and review them for a clinical experiment.

Changing the study does not alter historical execution results. Compatible Data,
ML and Interpretation choices remain in a combination design; unsupported domain
Hypothesis/Explanation choices are replaced with general research choices. Review
the resulting combination count before the next execution.

### Research changes and ML settings in Add pipeline

Register CSV, OKF and the target definition together, then select that saved version
in Add pipeline. HIV studies must explicitly provide their actual label mapping and
prediction timing; the column name alone does not establish those semantics.
HeartFailure uses the prepared demonstration contract described above. There is no
automatic inference of a study from a disease name or folder name.

Open **Selected CSV and OKF files** in the research selector to inspect this
server's registered source paths. The pipeline list also displays the configured
corpus profile and target; a pipeline name does not select either. Returning to
Deployment inputs restores the deployment target instead of a placeholder target.
Choose the Data agent on the floor plan to edit its allocation skill; Knowledge
sources and the dataset resource open the separate CSV/corpus/target contract.

The selected corpus determines the available Hypothesis skills in both Selected
Pipelines and All Combinations, including the agent settings editor:

| Corpus | Hypothesis skills |
|---|---|
| Supplied HIV / Addiction corpus | Substance use disorders; Social determinants of health; Psychiatric disorders; Random features |
| Supplied HeartFailure corpus | Cardiovascular disease and cardiac function; Metabolic, renal and other comorbidities; Lifestyle and social-psychological factors; Random features |
| Other corpus or LLM knowledge only | General research hypothesis; Random features; supplied custom hypothesis skills |

HeartFailure's three project-owned skills are separate files named
`heart-failure-cardiovascular.md`, `heart-failure-metabolic-renal.md` and
`heart-failure-lifestyle-social.md` in `src/memstara/playbooks/`. They preserve the
existing hypothesis output and feature-selection contracts, use only available
predictors and retrieved evidence, and retain the study's fixed target. The original
HIV and Anil/Phil skill files are unchanged. HIV offers Anil's Addiction and HIV
Explanation skills; HeartFailure uses General research explanation.

Source-to-skill bindings live in `src/memstara/corpus_skills.py`. They match the
supplied corpus index SHA-256, including copies in independent installations,
rather than guessing from a research name, target or folder. A changed or new corpus
uses the general profile until its explicit binding is added. The index identifies
the supplied corpus; registered research inputs still verify all frozen knowledge
files. A matching profile does not establish clinical validation.

Switching research inputs clears source filters and baseline columns, maps
incompatible Hypothesis/Explanation selections to the destination corpus profile,
and retains compatible choices such as Random and the technical Data, ML and
Interpretation combinations. Review the new skill schedule before execution.
Source selection does not rewrite previous execution records or reports. General
skills in existing saved runs remain executable for compatibility.

For LR/XGBoost skills, both models are trained and the skill selects the primary
model. The ML Agent chooses supported parameters, scaling, threshold and training
CV within server limits. Random Forest and preset candidate-search controls belong
to the legacy evaluation mode and are not shown for this paired mode. Data skills
choose the split policy and seed; split evaluations add fits within a Loop. Review
actual applied values in saved results, not just the initial defaults.

Open **Advanced model settings** below ML evaluation to fix individual parameters.
Blank inputs and **Auto — ML Agent** leave that setting automatic. Selecting LR
shows its C, solver, penalty, weighting, iteration and tolerance settings. Selecting
XGBoost shows its tree, learning-rate, sampling, regularization and histogram settings.
Each model also has separate numeric scaling and prediction-threshold controls.
Training CV folds are shared to preserve the paired comparison. With both ML skills
selected in All Combinations, both model panels appear; a model's overrides apply
consistently to that model in every Loop, including when it is the comparator.
Deselecting a model removes its hidden overrides. Reset returns all settings to Auto.

Existing designs can be edited through **Settings and more → ML evaluation and
advanced settings**, including All Combinations. The active execution must end before
settings can change. Edits affect future executions; they never rewrite old results.
The normal ML agent settings editor also exposes the selected model's advanced panel.
The UI reads parameter ranges from the same backend contract that validates saves
and launches. CPU-only execution, bounded memory/time, parallelism limits and split
seeds remain server/Data-owned and cannot be overridden here. Unsupported values,
LR l1 with lbfgs, and an excessive minimum fit count are rejected. Further checks use
the actual dataset, class counts and comparison workload before fitting.

The optional pipeline field `ml_overrides` is versioned JSON, for example:

```json
{
  "version": 1,
  "models": {
    "logistic_regression": {"parameters": {"C": 0.25}, "threshold": 0.6},
    "xgboost": {"parameters": {"n_estimators": 100, "learning_rate": 0.05}}
  },
  "folds": 3
}
```

This example requires both ML skills to be selected. The CLI equivalent is
`--ml-overrides '<JSON>'`. Empty `{}` preserves automatic configuration. Controlled
comparison experiments cannot combine their frozen ML plan with user overrides.
Proposal mode records these as planned settings without fitting a model.

Run configuration and ML reproduction receipts retain user overrides, the original
agent proposal, the effective complete model settings and parameter-level sources
(`user`, `agent`, or `server`). Reproduction bundles retain these receipts alongside
input data, exact splits, models, predictions, software environment and code hashes.
The saved `bundle_path` can be replayed with
`python -m memstara.reproducibility <bundle_path>` without a model API call.


Creating a design is not execution readiness. With no deployment input paths, select
a registered research version before Run. Missing inputs produce an actionable
message rather than implying that a corpus exists. No source mode is silently changed.

### 8. Troubleshooting and verification boundaries

| Symptom | Check / action |
|---|---|
| Foundry credentials missing | Set the API key and resource name/root URL in project `.env`, then restart services |
| Missing SHAP or other skill | Check the internal contributed files exist in the installed revision |
| HeartFailure missing-values rejection | Prepare the separate demo CSV in step 4; never relabel the raw CSV as validated |
| Database connection refused | Check Compose health, port/URL agreement, migration and role permissions |
| UI cannot connect / port 8070 unavailable | This walkthrough's development UI uses 5173; keep API 8071 and control 8072 running |
| Slow first execution | Inspect download/cache preparation and stage logs; a fresh embedding cache is intentionally empty |
| Provider timeout / HTTP 429 | Inspect saved retry and request events; preserve the failed run, resolve provider capacity/connection before retrying |
| Changed data rejected on resume | Keep historical snapshots; register changed input as a new version and start a new run |

Focused offline checks (no provider calls):

```bash
python -m pytest -q tests/test_heart_failure_demo.py tests/test_preflight_modes.py tests/test_packaged_skills.py tests/test_research_tutorial.py
python scripts/check_release_readiness.py
npm --prefix viewer/web test
npm --prefix viewer/web run build
```

The release check without `--publication` validates contents only. A successful
local run, an ignored resource folder, and a passing test suite do not establish
that the same files are already published or approved for redistribution.

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

The distribution checker creates a temporary virtual environment, installs the wheel
with `--no-index --no-deps`, and verifies installed metadata and every packaged file.
It does not use the editable checkout to satisfy imports. Use `--dist-dir <directory>`
to inspect a downloaded CI artifact. To additionally install the locked runtime dependencies in a fresh environment and
check dependency compatibility and backend imports, run
`uv run --frozen python scripts/check_runtime_distribution.py`. This second check
may download dependencies and the pinned Motoro revision; it does not call a model
provider or start a database. Both checks run in distribution CI. Neither verifies
an end-to-end live pipeline or a fully cold dependency cache.

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

The project `.env` owns model selection. Set `MEMSTARA_LLM_PROVIDER`,
`MEMSTARA_LLM_MODEL` and the provider credentials. For optional role overrides,
use `MEMSTARA_NON_EXPLANATION_*` and `MEMSTARA_EXPLANATION_*`; supported suffixes
are `PROVIDER`, `MODEL`, `API_BASE`, `TEMPERATURE`, `MAX_TOKENS` and `EFFORT`.
See [.env.example](.env.example) and installation step 2.

The non-explanation group serves question generation, Hypothesis, Data, ML and
Interpretation. The explanation group serves both Explanation experts. LR and
XGBoost are predictive learners, separate from these LLM assignments.

Saved designs keep research choices. New runs resolve project model settings and
freeze them in their execution snapshot. An old design with different explicit
`stage_models` is rejected: review it and explicitly clear that field through the
configuration API to adopt project defaults. Resume and report recovery retain
frozen historical assignments. Do not edit historical run files.

Legacy model JSON is not loaded automatically. Use the explicit migration command
in installation step 2, which makes a restricted backup first. Restart services
after changing `.env`. Model identities and token estimates are not Azure billing
receipts; unavailable billing remains unconfirmed.
