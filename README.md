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

## Docker quick start

You need **Git**, **Docker Desktop running** (or Docker Engine with Compose v2),
and access to a supported model deployment. Docker installs Python, Node,
PostgreSQL, Redis and the pinned **Motoro 0.10.0** dependency for you.

**1. Download this branch and create your settings file.**

```bash
git clone --branch feature/question-universe-ui https://github.com/HyunjunA/memstara.git
cd memstara
cp .env.example .env
```

Already have this checkout? Use its existing `.env`; do not overwrite it.

**2. Edit `.env`.** For the Azure Foundry example, replace these values with your
own deployment details. The model name must be available in your resource.

```dotenv
MEMSTARA_AZURE_FOUNDRY_API_KEY='YOUR_API_KEY'
MEMSTARA_QUESTION_PROVIDER=azure_foundry
MEMSTARA_QUESTION_MODEL=YOUR_DEPLOYMENT_NAME
MEMSTARA_QUESTION_API_BASE=https://YOUR_RESOURCE.services.ai.azure.com
```

Fill in the same three fields for `HYPOTHESIS`, `DATA`, `ML`, `INTERPRETATION` and
`EXPLANATION` in the template. Every agent needs its own assignment, even when all
six use the same deployment. There is no common model fallback.
For other providers and multiple installations, see [configuration details](#one-configuration-source).
Keep `.env` private. The remaining template defaults are suitable for a first local installation.

**3. Start the app from the same terminal.**

```bash
./start.sh
```

Open **http://127.0.0.1:5173/**, or the URL printed by the script if you changed
`MEMSTARA_WEB_PORT`. The first build may take several minutes. You can close the
terminal after the ready message. No separate backend/frontend commands are needed.

The bundled **Heart failure complete-case software demonstration** is registered
automatically, including CSV, OKF and target settings. Select it in the app to
create a pipeline. Private HIV data is not included. Starting the app does not
start an experiment or make a paid model request.

| Action | Command |
|---|---|
| Start again / apply `.env` changes | `./start.sh` |
| Stop the app, keeping saved data | `docker compose stop` |
| Inspect startup errors | `docker compose logs --tail=80 configure initialize control api web` |

Finish active experiments before rerunning `./start.sh`: it recreates services.
The app is local-only. A successful startup verifies service connectivity, not
model credentials or a complete research run.

For your own CSV/OKF, see [research folders](#add-your-own-research-folder).
For Docker troubleshooting, see [deployment guidance](deployment/README.md).
Native installation is optional and intended for developers.

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
python -c "from importlib.metadata import version; print(version('motoro'))"
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

The agent-configured workflow adds Data allocation skills (training-heavy or balanced,
both stratified), an LLM-proposed plan for the single user-selected LR or XGBoost model
with validated settings, and SHAP or LIME specialists that receive that
model's saved artifact and results. Selecting both ML skills creates separate model
combinations; they are not paired fits on identical splits.
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

## Docker configuration and research inputs

### Add your own research folder

Put each study under `user-inputs/` (or the host folder set by
`MEMSTARA_INPUTS_DIR` in `.env`):

```text
user-inputs/
└── my-study/
    ├── research.json
    ├── dataset.csv
    └── okf/
        └── index.md
```

Create `research.json` with your actual target definition; the following values
are placeholders to replace, not inferred clinical labels:

```json
{
  "name": "My study",
  "dataset_path": "dataset.csv",
  "knowledge_path": "okf",
  "target": {
    "column": "outcome",
    "positive_label": "1",
    "negative_label": "0",
    "description": "Describe the outcome and what each label means",
    "prediction_time": "Describe when predictor values are available",
    "horizon": "Describe the outcome observation period"
  },
  "excluded_columns": ["record_id"],
  "missing_policy": "reject"
}
```

Use your CSV's exact column names and labels. Paths in these startup manifests
are relative to the folder containing `research.json`; no absolute host path is
needed. CSV and OKF files must be visible inside the Docker mounts. Private HIV
inputs are not included in GitHub: provide your authorized files in a study folder.
For research without an OKF, set `knowledge_mode` to `llm_only` and omit
`knowledge_path`; for proposal-only research without a CSV, set `data_mode` to
`proposal` and omit `dataset_path`. No training metrics are fabricated in that mode.

Run `./start.sh` after adding or editing a study (finish active experiments first).
Initialization scans `user-inputs/*/research.json`, validates the data and target,
and registers valid studies. Unchanged registrations are reused; changed content
or target definitions produce new versions and do not overwrite old registrations.
An invalid custom study is skipped, while other studies and the app remain available.
Read `outputs/bundled-research/registration.json` for per-manifest registration status;
use **Prepare research inputs** to inspect and correct a rejected study. Custom CSVs
are never automatically cleaned or imputed. Known corpora use their existing skill
profiles; unknown corpora use the general profile, not an inferred specialty.

Derived bundled data and preparation evidence are stored under
`outputs/bundled-research/`. Registered inputs are persisted under
`outputs/research_inputs/` by default. Startup neither copies old experiments from
another installation nor sends data to an LLM. `.env` remains the operational
configuration; each study's manifest describes its research inputs.

### If startup reports invalid paths

Start from this branch's `.env.example` and edit your provider settings; do not copy
a complete `.env` from an older checkout. A path in `.env` does not download a file
or expose an arbitrary host directory to Docker. The preflight lists every invalid
input path by variable name before application services are restarted.

- For bundled skills, leave custom skill-path variables unset.
- To choose research inputs in the UI, leave `MEMSTARA_DATASET_PATH` and
  `AGENTIC_OKF_BUNDLE_DIR` unset.
- For bundled HeartFailure, leave these overrides unset and select the automatically
  registered demonstration. Do not use its raw CSV as the analysis CSV.
- For private CSV/OKF inputs, put the files under the configured `MEMSTARA_INPUTS_DIR`
  and reference `user-inputs/...` in `.env`. Private datasets are not downloaded by cloning.

Explicit invalid inputs are never silently substituted with a different dataset.
After correcting the named settings, rerun `./start.sh`.

### One configuration source

Choose the dataset and target in **Data & target** or the research input editor.
For an existing pipeline, open **Settings and more → Data & target → Edit prediction target**.
The editor loads the selected research settings. Save a new preparation record,
then click **Save settings** to attach it to the pipeline. Earlier execution records
and resumed executions retain their frozen target; the change applies to new executions.
Target editing is disabled while an execution is active.
Choose LR/XGBoost through ML agent skills. Installation `.env` target/ML-engine
defaults are ignored; each execution records its own selected research settings.

For a second installation, choose an unused `MEMSTARA_WEB_PORT` and use a fresh
checkout with its own input/output/cache directories. `./start.sh` generates a
unique Docker project and private database credentials automatically. Do not copy
another installation's `.memstara/` or `compose.override.yaml`.

Provider credentials are separate from model assignments. Use
`MEMSTARA_AZURE_FOUNDRY_API_KEY`, `MEMSTARA_OPENAI_API_KEY`,
`MEMSTARA_ANTHROPIC_API_KEY` or `MEMSTARA_OPENROUTER_API_KEY` for the providers
selected by your agents. Each agent specifies its own provider, model and endpoint.
A provider's credential is shared by agents using that provider; it does not choose
a model. The [model configuration guide](DEVELOPER_GUIDE.md) explains the contract.

See [the deployment configuration contract](deployment/README.md) for ownership,
path mapping, credential separation and maintenance details.

`.env` supplies model profiles/credentials, the public web port and input/output/cache
locations. Database owner credentials and the stable Docker identity are generated
in private `.memstara/installation.json`; `compose.override.yaml` is generated for
Compose. Read-only accounts are provisioned automatically in Docker settings volumes.
These are internal installation state, not files users need to edit. Both generated
paths are excluded from Git and Docker build contexts. Keep them when restarting
or updating, and back them up securely with the database volumes. Missing or invalid
state is an error, not permission to silently create replacement databases.

Legacy explicit DB/project/volume settings are preserved during preparation; remove
those `.env` entries only after verifying that the generated state retains them.
Custom Compose overrides require migration review. Do not edit Compose, proxy
configuration or a model JSON for an ordinary installation.

| Setting | Docker meaning |
|---|---|
| Database connections | Automatically generated and persisted; no user-supplied DSNs required |
| Read-only accounts | Automatically provisioned and retained separately from owner accounts |
| Redis connection | Automatically mapped to the private Redis service |
| `MEMSTARA_WEB_PORT` | Only published application port, bound to `127.0.0.1` |
| `MEMSTARA_API_PORT`, `MEMSTARA_CONTROL_PORT` | Native launcher ports; Docker uses private 8000/8072 listeners and never publishes them |
| `MEMSTARA_OUTPUT_DIR` | Host directory, mounted read/write at `/app/outputs` |
| `HF_HOME` | Host cache, mounted at `/app/cache` for control and the viewer model cache location for API |
| `MEMSTARA_INPUTS_DIR` | Host private-input folder, mounted read-only at `/app/user-inputs` |
| CSV/OKF/skill path settings | Paths inside the checkout/container: `examples/...`, `user-inputs/...`, `outputs/...`, `cache/...` or bundled `src/memstara/resources/...` |
| `MEMSTARA_UNIVERSE_SEMANTICS` | Optional local embedding dependencies in the viewer image; cache the documented pinned model before using semantic search |

Percent-encode special characters in URL credentials. Quote literal `.env` secrets
containing spaces, `#` or `$` using single quotes. Do not source `.env`. Remove shell
overrides for Compose settings: bootstrap rejects conflicting file/shell values.
No model credentials are passed to the API/web, and the `.env` is excluded from
image build contexts. It is mounted read-only only in the configuration service;
restricted generated settings are separated into per-service volumes.

No `config/` directory is required or shipped. Operational settings come from
`.env`, including advanced `MEMSTARA_PRICING_JSON` overrides (not required for installation),
`MEMSTARA_AZURE_PRICING_METERS_JSON` (verified Azure retail meter mappings), and
`MEMSTARA_EXPLANATION_SOURCES_JSON` (specialist database bindings). Leave these
unset for the default workflow; Explanation uses the selected OKF corpus.
For optional manual cost estimates, open a pipeline's **Settings and more →
Cost estimate settings**. Enter verified USD rates per million input/output tokens,
an optional cache-read rate, a source URL and an expiry date. The configured model
identities are filled in automatically; no JSON or model endpoint entry is required.
The editor applies to all pipelines in this installation, not just the open card.
Rates are saved as generated data in `outputs/pricing/manual-rates.json` and apply
to subsequent requests without a restart. Existing cost receipts are not rewritten.
Rates are estimates only; Azure actual billing remains a separate evidence source.
Missing, expired or unsupported cache-write rates are unavailable, not zero. Other
explicitly labeled estimate sources can still be used when manual rates are disabled.
Advanced `.env` pricing overrides take precedence and lock the UI editor; remove
those overrides and restart to switch to UI-managed rates. Do not discard an existing
catalog without first preserving its verified rates.

See [optional inline settings](deployment/README.md#optional-inline-settings) for schemas.
Prices are estimates, never actual Azure billing. An explicitly configured
`MEMSTARA_PRICING_PATH=outputs/pricing/catalog.json` may instead point at generated
pricing data; choose inline rates OR a catalog path. Release review metadata lives in
`deployment/release-readiness.json` and is not a user runtime setting.

Saved research profiles contain research-specific choices; `.env` contains
installation defaults. Each execution retains its own redacted configuration
snapshot. Changing `.env` does not rewrite prior results or frozen configurations.
For private data, place files under your `MEMSTARA_INPUTS_DIR` and select
`/app/user-inputs/...` in the browser. Files outside the supported mounts are rejected.

### Stop, restart and update

```bash
docker compose stop             # stops the application; retains data
# Restart / apply settings after finishing active experiments:
./start.sh
# Update this checkout, then rebuild and restart:
git pull --ff-only
./start.sh
# Remove containers/network, retaining database volumes and bind-mounted files:
docker compose down
```

Stop or pause running experiments deliberately before maintenance; container shutdown
is not a promise to resume an in-flight model request. Back up database volumes and
the output directory before upgrading. `docker compose down -v` is destructive and
is never part of ordinary installation or troubleshooting. Keep the same project
name to reopen the same Docker databases. Changing passwords in `.env` does not
change existing PostgreSQL passwords.

The native development workflow below remains available for debugging and separate
host-managed services. Do not run both launch paths on the same published ports.

## Get started (native development)

**Not required for Docker installation.** Expand only when developing or running
services directly on the host.

<details>
<summary>Native installation, CLI execution and detailed workspace walkthrough</summary>

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
    'src/memstara/resources/contributed/specialists',
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
| `MEMSTARA_<AGENT>_PROVIDER`, `MEMSTARA_<AGENT>_MODEL` | Required independent assignment for each of the six agents |
| `MEMSTARA_AZURE_FOUNDRY_API_KEY` | Authorized provider credential, shared by Foundry agents |
| `MEMSTARA_<AGENT>_API_BASE` | Explicit endpoint; required for Azure Foundry |
| `MEMSTARA_DATABASE_URL`, `MOTORO_DATABASE_URL`, `MOTORO_REDIS_URL` | Select independent service destinations; preserve existing values when migrating |
| `COMPOSE_PROJECT_NAME` | Choose a unique name for a new Docker installation |
| `MEMSTARA_WEB_PORT`, `MEMSTARA_API_PORT`, `MEMSTARA_CONTROL_PORT` | Choose free ports; launcher and web proxy use these same values |
| `MEMSTARA_VIEWER_DSN`, `CORE_VIEWER_DSN` | Read-only database accounts for the observation API |
| `MEMSTARA_OUTPUT_DIR`, `HF_HOME` | Tool output and model-cache directories |

Every agent has its own required model assignment. For example:

```dotenv
MEMSTARA_AZURE_FOUNDRY_API_KEY=YOUR_API_KEY
# Repeat PROVIDER/MODEL/API_BASE for all six agents, as in .env.example.
MEMSTARA_QUESTION_PROVIDER=azure_foundry
MEMSTARA_QUESTION_MODEL=YOUR_DEPLOYMENT_NAME
MEMSTARA_QUESTION_API_BASE=https://YOUR_RESOURCE.services.ai.azure.com
```

To use another model for Explanation, set `MEMSTARA_EXPLANATION_MODEL` in the same
file. Its required `MEMSTARA_EXPLANATION_PROVIDER` and provider-dependent
`MEMSTARA_EXPLANATION_API_BASE` select its provider/endpoint. Use `MEMSTARA_QUESTION_*`, `MEMSTARA_HYPOTHESIS_*`,
`MEMSTARA_DATA_*`, `MEMSTARA_ML_*` or `MEMSTARA_INTERPRETATION_*` for the other agents.
Provider/model values cannot be blank; optional generation fields use model runtime defaults. Credentials remain provider
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
Do not use the root application Compose stack for this native provisioning workflow.

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

#### What the HeartFailure inputs contain and how they are used

The supplied CSV has 1,700 rows and 113 columns. It is a supplied processed cohort,
not the generated 120-row synthetic tutorial in option A. The preparation above
creates a smaller **analysis CSV with eight predictors plus the target**. The
pipeline using that prepared study cannot choose the other raw columns. Changing
that selection requires a separately reviewed input contract and a new registration;
changing a skill or the pipeline name does not add columns to the analysis CSV.

| Exact predictor column | Meaning used in the demonstration |
|---|---|
| `age_years` | Age |
| `sex` | Supplied sex code; confirm its coding before clinical interpretation |
| `previous_myocardial_infarctions_count` | Number of prior myocardial infarctions |
| `essential_hypertension_stage` | Supplied hypertension stage |
| `diabetes_mellitus_history` | Diabetes history |
| `obesity_history` | Obesity history |
| `chronic_bronchitis_history` | Chronic bronchitis history |
| `bronchial_asthma_history` | Asthma history |

The target column is never a predictor. Predictor coding and measurement timing
must be checked against source documentation before using the demonstration for a
scientific claim; the software does not establish those meanings from column names.

The OKF is a searchable literature bundle, not a second patient table. Its
`index.md` describes 100 curated PubMed/PMC papers across eight topics:

- Hypertension and ischemic heart disease.
- Arrhythmia, valvular and other cardiac conditions.
- Metabolic and renal comorbidities.
- Biomarkers and subclinical cardiac dysfunction.
- Lifestyle and behavioural factors.
- Social, psychosocial and healthcare-access determinants.
- Cardiotoxic drugs, inflammatory and environmental exposures.
- Risk prediction models, demographics and genetics.

The Hypothesis Agent uses retrieved knowledge to propose a question, justify a
hypothesis and select **available CSV predictors**. The Data and ML stages work
with the selected study's CSV and fixed target. Interpretation explains the
recorded analysis; Explanation combines that interpretation with available
knowledge evidence. A paper mentioning a measurement does not make that
measurement available in the CSV. Literature claims are not measured model results.

Keep the whole `okf/` directory, including indexes, topic directories, citations
and supporting files. The bundle's generation model names, duration and costs
are historical corpus-build metadata; they do not select the model or describe
the cost of a new Memstara execution. Current execution models come from project
`.env` and are frozen into each run. Source provenance, redistribution terms and
clinical validity still require review; repository inclusion is not a new license
for the supplied data or cited publications.

After preparation, these files have different purposes:

| File | Purpose |
|---|---|
| `examples/heart-failure/dataset.csv` | Unmodified supplied CSV; do not pass it directly to the reject-missing-values demo |
| `examples/heart-failure/okf/index.md` | Entry point and overview of the supplied literature bundle |
| `outputs/heart-failure-demo/dataset.csv` | Derived complete-case analysis data |
| `outputs/heart-failure-demo/research.json` | CSV/OKF paths, target labels, missing-value policy and explicit timing limitations |
| `outputs/heart-failure-demo/preparation.json` | Source/derived hashes, chosen columns and retained/excluded counts |
| `outputs/launch.json` | Registered research ID, tutorial skill IDs and a one-Loop CLI command |

Preparation and registration do not run agents or train a model. Use **either**
the tutorial CLI route in steps 5–6 or the domain-specific browser walkthrough
below for your first execution. These use the same prepared inputs but different
Hypothesis/Explanation skills; they are not identical experimental conditions.

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

Each supplied domain profile offers 12 built-in choices across five roles
(4 × 2 × 2 × 2 × 2 = 64 combinations). Separate general-research skills support
other corpora. HeartFailure has its own Hypothesis/Explanation choices listed below. A
registered research profile cannot silently use an unrelated
Addiction/HIV specialty. The tutorial registers separate, versioned user skills
for Hypothesis and Explanation. It does not enable retired skills or edit originals.

| Role | HIV / Addiction catalogue | First-run CLI tutorial selection |
|---|---|---|
| Hypothesis | Psychiatric, social determinants, substance use, random features | User research tutorial, from `examples/research-inputs/skills/hypothesis.md` |
| Data | Training-heavy or balanced stratified | `data_training_heavy` |
| ML | LR or XGBoost | `ml_logistic_regression` |
| Interpretation | Anil SHAP or LIME | `shared-anil-shap` |
| Explanation | Anil Addiction or HIV | User research tutorial, from `examples/research-inputs/skills/explanation.md` |

Project skills are under `src/memstara/playbooks/`; common system prompts are under
`src/memstara/prompts/`. The four specialist documents have internal copies under
`src/memstara/resources/contributed/specialists/`; the two ML documents are under
`src/memstara/resources/contributed/machine-learning/`. These role-based paths do
not identify individual contributors. Existing `shared-anil-*` skill IDs remain
stable for saved designs and run compatibility; document contents are unchanged.
ML Knowledge is additive
background; the legacy ML Skill report selection remains disabled. No adjacent
contributor folders are discovered automatically. Explicit skill-path overrides
remain supported. If a required packaged document is missing, install a complete
candidate revision; do not silently fall back to an unrelated archived skill.

The preparation script uses the same two general tutorial files for both the
synthetic and HeartFailure CLI demonstrations. It does not automatically substitute
the HeartFailure specialists. Their registered user skill IDs are explicit in the
CLI command; the known-corpus browser picker instead offers the domain choices
listed below. Use the browser walkthrough for the HeartFailure specialist design.

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

In Floor plan, choose **Add pipeline → All Combinations**, select the research
version saved in step 4, and choose compatible skills from the displayed corpus
profile. For HeartFailure, follow the one-Loop walkthrough below. The tutorial CLI
skill IDs are not the same as the built-in domain choices shown in that picker.
Creating a pipeline saves settings; running it executes the design. Do not replay the already completed CLI
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
Hypothesis/Explanation choices are mapped to compatible choices in the destination
corpus profile (general research for an unrecognized corpus). Review
the resulting combination count before the next execution.

### HeartFailure browser walkthrough: one combination, one Loop

Complete installation steps 1–4 and browser startup in step 7 first. Use the URL
printed by the startup command: the documented development frontend normally uses
`http://localhost:5173`; a separately running Docker web service may use
`http://localhost:8070`. These can point at different installations. Check the
selected study and source paths rather than assuming two URLs share state.

1. Open **Add pipeline → All Combinations**. **Prepare research inputs** is the
   alternative for inspecting/registering new input files; the CLI preparation above
   has already registered this example on this installation.
2. In **Research inputs**, select the saved HeartFailure study. Open **Selected
   CSV and OKF files** and confirm the *derived* CSV, supplied HeartFailure OKF and
   `chronic_heart_failure` target with labels `1`/`0`. Do not leave **Deployment
   inputs** selected when intending to use this registered study.
3. In **Agent skills**, choose exactly one skill per role for the initial test:

   | Role | Example selection |
   |---|---|
   | Hypothesis | Cardiovascular disease and cardiac function |
   | Data | Training-heavy stratified (`data_training_heavy`) |
   | Machine learning | Logistic regression (`ml_logistic_regression`) |
   | Interpretation | Anil SHAP (`shared-anil-shap`) |
   | Explanation | Cardiovascular expert explanation (`report_heart_failure_cardiovascular`) |

   The design should show **1 possible combination**. Only LR is fitted for this
   selection. Add a separate XGBoost combination to run that model independently.
   This example does not select all 64 combinations.
4. Review model assignments and evaluation settings. **Advanced model settings**
   lets you fix supported ML parameters; blank/Auto leaves them for the ML Agent.
   These ML parameters are separate from the LLM deployment selected in `.env`.
   Keep the initial workload small and review the actual applied configuration in
   the saved results. The eight-column prepared dataset bounds available features.
5. In **Review & create**, give the design a name, set **Maximum Loops per execution**
   to **1**, review the selected study/skills/model settings, and acknowledge the
   execution cost notice. Choose **Create combination design**.
6. Start the created design with its Run control. Creation alone does not execute
   it. If the start response is delayed, wait for state reconciliation; do not
   launch another copy. Follow the Floor plan and Live log.
7. Confirm the Loop and report are completed, then inspect measured results and
   saved artifacts using the completion checks in step 6. A question, an agent
   response or an animation alone does not establish successful completion.

For a subsequent full built-in design, select all 4/2/2/2/2 domain choices and
review the **64 possible combinations**. The Loop limit is independent: a limit
of 1 attempts only one combination; 64 schedules one full cycle. Blocked Loops
count toward the limit; retries within a Loop do not add Loops. A limit above the
combination count repeats combinations. Random starting order is separate from
selecting the Random features Hypothesis skill. Do not start a larger run merely
to populate the interface.

### When the result views become populated

Navigation entries are available before execution finishes. Each view depends on
saved records, not simply on a running/completed badge:

| View | When useful content appears | What an empty view means |
|---|---|---|
| Floor plan / Live log | As execution state, agent calls and saved updates arrive | No recorded activity yet, or a loading/connection issue if explicitly reported |
| Question universe | When questions are saved, potentially before ML finishes | No questions in the displayed scope yet; a display error is a separate issue |
| Telemetry | As calls, timing and usage records become available | Measurements have not arrived or the selected execution has no records |
| Clinician view | When analysis results are saved; Interpretation fills in when recorded | A question/hypothesis may exist while there is no analysis finding yet |
| Final report | When Explanation saves report text | The report is not yet available, even if earlier stages have results |

**Memstara · Clinical insights**, **What is your research finding?** and **Choose
a finding to understand its meaning and what to check next.** are the Clinician
view's introductory heading and instructions, not additional pipeline stages.
The page can display these before its finding list has any entries. In that case,
wait for recorded analysis results and check execution progress rather than
assuming a rendering failure. An available result can still be awaiting Interpretation.

Clinician view defaults to recent findings across pipelines; **Past analyses**
selects a saved execution. Final report and detailed Telemetry follow the selected
execution. Check the pipeline, run and Loop scope when comparing these views.
Use Live log stage links for that stage's activity, or **Browse activity** for the
execution. This compact view has no search/agent/type filters; the full Activity
view retains filters and offers **Clear filters** when a search has no matches.

If the pipeline says **Needs attention**, inspect its recorded failure and trace;
waiting for a report does not repair a failed execution. If updates are unavailable,
check API/control connectivity. Do not reinterpret missing results as zero model
performance or missing billing as zero cost. A displayed cost estimate is not an
Azure bill; the billing rules and attribution limits above still apply.

### Research changes and ML settings in Add pipeline

The **Build pipelines** chooser offers **Prepare research inputs** and
**All Combinations**. The **Selected Pipelines** entry is temporarily hidden;
existing pipelines and the retained single-pipeline editor are preserved. To build
one combination, select one skill per agent in All Combinations. Creating a design
does not start it automatically.

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
Explanation skills. HeartFailure offers two project-authored adaptations of the
structure and evidence rules of Anil's HIV Explanation skill:

| HeartFailure Explanation skill | Focus | File under `src/memstara/playbooks/` |
|---|---|---|
| Cardiovascular expert explanation | Cardiac function and cardiovascular disease | `report_heart_failure_cardiovascular.md` |
| Cardiometabolic and renal expert explanation | Metabolic/renal comorbidity, lifestyle and care context | `report_heart_failure_cardiorenal.md` |

Both use the selected CSV/target contract, available LR/XGBoost Interpretation
outputs and supplied HeartFailure OKF evidence. Neither connects to a separate
specialty database or changes Anil's original instructions. They are project-authored
adaptations, not specialist-reviewed clinical guidance. With all built-in domain
choices selected, both HIV and HeartFailure offer 4 Hypothesis × 2 Data × 2 ML ×
2 Interpretation × 2 Explanation = 64 combinations. The execution Loop limit
still controls how many combinations are attempted. Existing saved designs retain
their settings until explicitly edited; old general Explanation runs remain readable.

New All Combinations executions use independent, knowledge-grounded question
creation for each scheduled Loop. They do not require a novel predictor set in
every Loop or feed earlier ML scores into later question selection. A supported
question may be submitted again in another Loop; duplicates within one Loop are
still rejected. This policy is frozen as `independent_combination_questions_v1`.
Ordinary iterative exploration and old frozen executions retain their original
policy. Independent generations are not guaranteed to be identical, so differences
between results cannot automatically be attributed to downstream skills alone.

After bounded question recovery, a combination with no executable question is
recorded as **skipped**, without running its downstream agents. Other scheduled
combinations continue. The outcome journal and final status distinguish completed,
skipped and blocked Loops. The UI shows **Finished with skips** when analyses were
saved, or **No findings** if every attempted combination was skipped. Neither means
all requested analyses succeeded. Database, provider and verification failures
remain errors, not skipped research questions. Existing failed runs are preserved;
start a new execution to use the new policy rather than editing old evidence.

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

For LR/XGBoost skills, only the model named by the selected skill is trained. The
ML Agent chooses supported parameters, scaling, threshold and training
CV within server limits. Random Forest and preset candidate-search controls belong
to the legacy evaluation mode and are not shown for this selected-model mode. Data skills
choose the split policy and seed; split evaluations add fits within a Loop. Review
actual applied values in saved results, not just the initial defaults.

New executions record unlimited ML resource ceilings (`null`): no fit-count cap,
wall-time deadline, memory budget, CSV-size cap, encoded-column cap or dense-matrix
cap. This applies to selected-model training and final validation. Jobs remain
serialized with one native thread, and input validity, split isolation and frozen
model settings are still enforced. Large jobs can consume available system memory;
the operating system can still terminate them. Existing saved execution policies
remain unchanged and require an explicit recovery/migration before using new limits.
Provider context limits and transport timeouts are separate from these ML settings.


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
| Execution state read failure | Inspect `board_read_events.jsonl`. Transient connection failures are retried up to five reads; permanent errors stop execution without treating an unavailable board as empty. |
| Data worker finishes without submitting | The controller verifies the unfinished task and requeues only that data handoff, bounded by five recovery attempts and the run claim limit. Model prose is not proof of submission. |
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

</details>

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

In the selected-model workflow, an independent validation reserve is set aside before
Data divides the exploration population into training and evaluation partitions. Agents
and adaptive Loops cannot access reserve outcomes. After every Loop finishes, Memstara
refits each completed hypothesis/ML task's selected model on **all non-reserve development
rows**, using its frozen parameters, seed, predictors and threshold. Preprocessing is
freshly fitted on these development rows only. Exploratory replicate models are retained
as internal evaluation evidence; no replicate winner is selected. Each final model is
saved before it scores the same reserve once per task. `final_validation.json` stores
separate final-fit provenance, confusion matrices, AUROC, trapezoidal PR-AUC, average
precision, Brier score and other metrics for every task. Local `final_models/task-*/`
bundles contain the final model, input, development/reserve row indices, predictions,
configuration, environment and integrity hashes. Final validation remains available in the final report.
General Explanation reports receive only the current Loop's results, projected to
hypotheses, interpretation text, feature importance and scalar evaluation values.
Raw evaluation arrays and per-row predictions remain in the saved evidence, outside
model context. Any shortened narrative is explicitly marked in the input receipt.
`report_io/` stores the exact supplied input, its hash, the source-result hash and
model response. The general final comparison copies recorded metrics in code rather
than asking an LLM to reread all detailed results; it retains the independent validation
record separately. Specialist Explanation continues to use its scoped evidence path.

Final-fit parameters and thresholds are not tuned using the reserve. Historical artifacts
from the previous no-refit policy are preserved and are not automatically rescored.
No hypothesis is selected using reserve performance, and scores must not be used to tune
or rank hypotheses. These are same-dataset holdout estimates, not external-cohort validation,
clinical utility or causal effects. If the record says `failed` or `not_run`, inspect its
per-task results and reason; successful results remain saved if another task failed.
Check split indices and provenance before comparing runs. See the
[artifact audit](DEVELOPER_GUIDE.md#read-and-verify-an-execution).

This reserve is generated from the run's dataset when execution starts; it is not a
separately registered user-supplied holdout. If the selected Data skill controls the
allocation, its saved seed and reserve fraction define the partition for that run.

CSV-based pipeline starts automatically prepare the semantic predictor-search index
before checking its readiness. This applies to HIV, HeartFailure, custom registered
inputs, and CSV-only runs without OKF. Missing, stale or damaged caches are rebuilt;
matching caches are reused. The UI displays **Preparing predictor search** during this
step. Registered inputs retain separate caches under their research fingerprints.
No-CSV proposal mode skips predictor indexing. Interrupted preparation can be retried
with a new start; preparation failures are recorded before any agent calls. The initial
embedding-model download requires network access unless the pinned model is cached.

## Everyday commands

For the Docker installation, run these from the checkout root:

```bash
docker compose logs --tail=80 control api web
docker compose exec control python -m memstara.trace.board --last 3 --summary
```

Use `./start.sh` to rebuild and apply changes after finishing active experiments.
The separate `viewer/docker-compose.yml` is for the native developer workflow.

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
| Target column | Selected in the UI research profile; propagated internally to exclude the target from predictor lists |
| `MEMSTARA_<AGENT>_PROVIDER`, `MEMSTARA_<AGENT>_MODEL` | Independent agent model assignments |
| `MEMSTARA_<AGENT>_API_BASE` | Agent-specific endpoint |

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
create a fresh schema for each test. The disposable image includes pgvector to
match the CI vector-memory restore checks. Install PostgreSQL 16 client tools
(`pg_dump`, `pg_restore`, and `psql`) and put them on PATH before running this suite.

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
After starting the app, `node scripts/check_live_ui.mjs` checks all served views
with real API reads at desktop and mobile widths. It blocks mutation requests,
so it does not launch or delete pipelines; this smoke test complements the fixture suite.

Real-provider acceptance is a separate, explicitly paid check. Configure the project
`.env` so both stage families use `claude-haiku-5-5`, then run:

```bash
python -m pytest tests/live/test_haiku_pipeline.py --run-live --live-loops=2 --live-audit-io -k 'not private_hiv' -x -s -q --tb=short
```

This runs the four supported input modes twice, four HeartFailure skill combinations,
and two HeartFailure random-feature Loops. Cases run sequentially and stop at the first
failure. It checks stored results, stage/model identity, IO evidence and registry
synchronization, not just process exit status. Skipped empirical Loops fail acceptance.
Evidence is retained under `outputs/verification/haiku_live_*/`; a completed case can
be audited with `--live-batch <directory>` without paying to run it again. Inspect failed
evidence before explicitly using `--live-retry-failed`; earlier attempts remain intact.
This representative matrix is not the entire 64-combination experiment or private HIV
validation, and successful repetitions cannot guarantee external-service availability.
Standalone `random_features` executions also use a frozen single-combination schedule:
the server samples 4–20 eligible original predictors, records their seed and order, and
removes knowledge retrieval and semantic-matching tools from question/hypothesis stages.
Use one skill per stage and one trial per Loop, or provide an explicit combination plan.
Legacy random executions without a frozen sampling policy require a new execution;
they cannot be resumed under a silently changed experimental condition.
For a separately authorized private HIV check, select `-k private_hiv` and provide
`--live-private-research /path/to/research.json` (a research configuration or saved
registration with its explicit target contract). Original inputs remain unchanged.

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

The project `.env` owns model selection. Configure all six agents and the credentials
for their providers. For independent assignments,
use `MEMSTARA_QUESTION_*`, `MEMSTARA_HYPOTHESIS_*`, `MEMSTARA_DATA_*`,
`MEMSTARA_ML_*`, `MEMSTARA_INTERPRETATION_*` and `MEMSTARA_EXPLANATION_*`; supported suffixes
are `PROVIDER`, `MODEL`, `API_BASE`, `TEMPERATURE`, `MAX_TOKENS` and `EFFORT`.
See [.env.example](.env.example) and installation step 2.

Each agent requires an explicit provider and model. No common fallback is used. The Explanation
assignment serves the selected Explanation expert. Legacy `MEMSTARA_NON_EXPLANATION_*`
settings must be replaced by individual agent settings. LR and
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

### Inspect KG novelty

In **Question universe**, open **Novelty ranking** to prioritize recorded
hypotheses by their **KG novelty proxy**: the fraction of declared-use paths that
contain predicted edges. Full annotation coverage is required; unknown, literature-only
and historical records remain **Unscored**, not zero. Filter by run ID to compare
within the same study/corpus. Inspect paths, rationale and calculation, or open the
linked agent outputs. AUROC remains separate. This metric does not establish novelty
across the literature or scientific validity. Existing results are not backfilled.

For supported OKF annotations, custom path metadata and reproducible scoring rules,
see [Knowledge-source provenance and KG novelty ranking](DEVELOPER_GUIDE.md#knowledge-source-provenance-and-kg-novelty-ranking-issue-186).

### Question Universe exploration

The default workspace opens Question Universe. **New research** reuses the existing
input registration and pipeline review wizard. Expand **Pipeline controls** for
**Go**, pause/resume and **Inspect** actions; **View floor plan** opens the existing
pipeline workspace. Every view remains directly accessible in navigation, including
Floor plan, Clinician view, Final report, Telemetry, Run log, Board, Task life and
Access map. Collapsing pipeline controls only changes their visibility.
Results/report headers remain available when their panels are initially collapsed.

Decorative placement is explicitly nonsemantic. **Semantic layout and search** uses
local question-text embeddings, cosine neighbors and a fixed PCA projection. Screen
distance is approximate, not a clinical association or an exact similarity score.
New questions require Refresh; existing projection coordinates remain stable. Model
identity, pinned revision, normalized text hashes, vectors and projection basis are
retained in the viewer's separate cache. Inputs longer than 512 model tokens use the
first 512 tokens. Cleared questions are excluded from the active index. This feature
never changes experiment data, models, skills or scientific outcomes.

The base viewer works without semantic dependencies. To enable local semantics:

1. For local Linux installations, first install CPU-only PyTorch with
   `python -m pip install torch --index-url https://download.pytorch.org/whl/cpu`.
   Then install `viewer/requirements-semantic.txt` in the viewer environment (or set
   `MEMSTARA_UNIVERSE_SEMANTICS=1` in the project `.env` for the Docker build; it installs CPU-only PyTorch first).
2. Cache `pritamdeka/S-PubMedBert-MS-MARCO` at revision
   `96786c7024f95c5aac7f2b9a18086c7b97b23036`. For Docker, place a Hugging Face
   cache tree under `outputs/embedding-cache`, or set `MEMSTARA_EMBEDDING_CACHE`.
   The API uses local files only and never silently downloads model weights.
   After installing the optional requirements, explicitly download the pinned public
   model once from the repository root (internet access is required for this step):

   ```bash
   python -c "from huggingface_hub import snapshot_download; snapshot_download('pritamdeka/S-PubMedBert-MS-MARCO', revision='96786c7024f95c5aac7f2b9a18086c7b97b23036', cache_dir='outputs/embedding-cache/hub')"
   ```

   For a non-Docker viewer using this cache, set `HF_HOME=outputs/embedding-cache`
   before starting the API from the repository root. Embeddings remain local;
   no paid model API calls are made by this feature.
3. From the repository root, build the viewer (this updates viewer services, not
   analysis/control workers):

   ```bash
   docker compose --env-file .env -f viewer/docker-compose.yml up -d --build api web
   ```
4. Open Semantic layout and search. The UI reports indexed/total question counts,
   model provenance and cosine scores; unavailable semantics does not disable the
   ordinary question list. Initial indexing can take time and uses one CPU thread.

**Color by historical AUC** uses each question's recorded best exploratory AUC across
its uses. It is not an independent holdout score or a controlled comparison of models.
Open an individual result for its model, features and evaluation provenance. Novelty
ranking remains separate from similarity and performance. AUC below 0.5, exactly 0.5,
above 0.5 and unavailable values are distinct; none establishes clinical usefulness.

Provider-specific `MEMSTARA_<PROVIDER>_API_KEY` values map to Motoro's existing
credential variables. There is no common model/provider/resource default.
Legacy provider credential names remain accepted; conflicting values fail validation.
No Motoro source changes are required. Credentials never enter saved model profiles.
