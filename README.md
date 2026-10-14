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

### 2. Start independent PostgreSQL and Redis services

Memstara owns the analysis board. Motoro owns its execution database and Redis
working memory. These database URLs must point to different databases. The Motoro
server needs pgvector; use the image below rather than plain PostgreSQL.

The following creates an ignored local Compose file. The passwords are local
development values, with ports bound only to loopback. It neither starts nor
modifies the repository's legacy Compose stack. On a host already using these
ports, select free ports and change every matching URL below before starting.
This procedure supplies all three services directly; no separate Motoro setup
instructions or source checkout are required.

First inspect existing containers and check that the proposed ports are available:

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'
python - <<'PYCODE'
import socket
ports = (55641, 55642, 56391)
listeners = []
try:
    for port in ports:
        sock = socket.socket()
        listeners.append(sock)
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as exc:
            raise SystemExit(f'Port {port} unavailable: {exc}. Choose unused ports first.')
    print('Database and Redis ports available')
finally:
    for sock in listeners:
        sock.close()
PYCODE
```

The port check is for initial creation; an existing instance of this same stack
will occupy its own ports. Inspect it instead of creating another one. If Docker
already shows a different installation named `memstara-local-*`, choose a unique
Compose project name in the YAML below. A unique project name isolates containers
and named volumes, but does not free occupied host ports. Deleting a checkout does
not delete its Docker containers or volumes.

Do not substitute bare `docker compose up -d`: the repository-root Compose file
uses the fixed `memstara-postgres` name, port 5463 and a shared named volume. It is
not the independent stack described here.

```bash
mkdir -p outputs/local-runtime
cat > outputs/local-runtime/compose.yml <<'YAML'
name: memstara-local
services:
  board:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: cleancheck
      POSTGRES_PASSWORD: cleancheck
      POSTGRES_DB: memstara
    ports: ['127.0.0.1:55641:5432']
    volumes: ['board-data:/var/lib/postgresql/data']
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U cleancheck -d memstara']
      interval: 2s
      timeout: 5s
      retries: 30
  runtime:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: cleancheck
      POSTGRES_PASSWORD: cleancheck
      POSTGRES_DB: motoro
    ports: ['127.0.0.1:55642:5432']
    volumes: ['runtime-data:/var/lib/postgresql/data']
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U cleancheck -d motoro']
      interval: 2s
      timeout: 5s
      retries: 30
  redis:
    image: redis:7-alpine
    ports: ['127.0.0.1:56391:6379']
volumes:
  board-data:
  runtime-data:
YAML
docker compose -f outputs/local-runtime/compose.yml up -d
docker compose -f outputs/local-runtime/compose.yml ps
```

Wait for both PostgreSQL services to be healthy. Keep volumes for subsequent
runs; changing a password in Compose does not change an existing database password.
Use `docker compose -f outputs/local-runtime/compose.yml stop` to stop this stack
without deleting data. Do not use `down -v` unless you intend to delete its databases.

### 3. Configure your own model connection and local paths

In a **new checkout only**, create `.env` with the following contents. Do not
overwrite an existing `.env`. If you already copied `.env.example`, edit that file:
replace the matching assignments below and remove duplicate assignments; do not
append a second conflicting set. Replace both `YOUR_...` values before continuing.
These settings use Claude on Azure Foundry; they do not authorize access to the
authors' deployment. The resource name is the hostname prefix, not a URL.

```dotenv
MEMSTARA_DISABLE_SIBLING_ENV=1
MOTORO_DATABASE_URL=postgresql+asyncpg://cleancheck:cleancheck@127.0.0.1:55642/motoro
MEMSTARA_DATABASE_URL=postgresql://cleancheck:cleancheck@127.0.0.1:55641/memstara
MOTORO_REDIS_URL=redis://127.0.0.1:56391/0
MEMSTARA_LLM_PROVIDER=azure_foundry
MEMSTARA_LLM_MODEL=claude-haiku-5-5
ANTHROPIC_FOUNDRY_RESOURCE=YOUR_RESOURCE_NAME
ANTHROPIC_FOUNDRY_API_KEY='YOUR_API_KEY'
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
TOKENIZERS_PARALLELISM=false
```

Use your actual deployed model identifier if it differs. Keep `.env` private.
Load only your own trusted shell-compatible configuration into each terminal:

```bash
set -a
source .env
set +a
export MEMSTARA_OUTPUT_DIR="$PWD/outputs"
export MOTORO_DATA_DIR="$PWD/outputs/motoro"
export HF_HOME="$PWD/outputs/huggingface"
export MEMSTARA_STAGE_MODELS_PATH="$PWD/config/stage-models.local.json"
mkdir -p outputs config
```

`MEMSTARA_DISABLE_SIBLING_ENV=1` prevents automatic reading of an adjacent
`motoro/.env`. Already exported values take precedence over `.env`; open a clean
terminal or unset stale variables when changing configurations. The embedding
model is `pritamdeka/S-PubMedBert-MS-MARCO`, revision
`96786c7024f95c5aac7f2b9a18086c7b97b23036`; its first download/build can take time.
The explicit `HF_HOME` above keeps this installation's model cache separate.

Generate the two stage profiles from those explicit settings. Run this only when
creating or deliberately replacing the local model configuration:

```bash
python - <<'PY'
import json, os
from pathlib import Path
resource = os.environ['ANTHROPIC_FOUNDRY_RESOURCE']
assert resource and resource != 'YOUR_RESOURCE_NAME', 'Set your resource first'
profile = {
    'provider': 'azure_foundry',
    'model': os.environ['MEMSTARA_LLM_MODEL'],
    'api_base': f'https://{resource}.services.ai.azure.com',
}
Path(os.environ['MEMSTARA_STAGE_MODELS_PATH']).write_text(json.dumps({
    'non_explanation_agents': profile,
    'explanation_agent': profile,
}, indent=2) + '\n')
PY
```

| Profile key | Stages |
|---|---|
| `non_explanation_agents` | Question, Hypothesis, Data, ML, Interpretation |
| `explanation_agent` | Explanation / final report |

For separate models, edit the two profiles independently and retain the deployment
provider and endpoint that actually serve each model. Explicit profiles override
stage assignments; legacy CLI `--model` is not a substitute. Other supported
connections include `anthropic` with `ANTHROPIC_API_KEY`, and `openai` with
`OPENAI_API_KEY`; change provider/model/endpoint consistently. Claude on Foundry
uses the `azure_foundry` provider, not an OpenAI chat endpoint. Credentials stay
in the environment, never in the stage-profile JSON. For advanced controls see
[model profiles](DEVELOPER_GUIDE.md#model-profiles-and-their-limits).

Initialize both schemas after the databases are healthy:

```bash
python -m motoro.migrations upgrade --url "$MOTORO_DATABASE_URL"
python -m memstara.blackboard --create
```

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

Copy `examples/research-inputs/research.json` to `outputs/my-study.json` and edit:

| Field | Required meaning |
|---|---|
| `dataset_path`, `knowledge_path` | CSV path and OKF root containing `index.md`; absolute paths recommended |
| `target.column`, `target.description` | Exact binary outcome column and what it means |
| `target.positive_label`, `target.negative_label` | Exact CSV values, not inferred label order |
| `target.prediction_time`, `target.horizon` | Predictor availability and outcome window |
| `excluded_columns` | IDs, leakage-prone or unavailable-at-prediction-time columns |
| `missing_policy` | `reject`; clean data explicitly before registering |

Relative paths resolve from the working directory, not the JSON file's directory.
Use an analysis-ready CSV up to 100 MiB with at least four eligible predictors.
Run the same `inspect` and `prepare_research_tutorial.py` commands with your JSON.
Review the tutorial skill contents for your study before a paid execution.

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

The normal specialty catalogue contains 12 choices (4 × 2 × 2 × 2 × 2 = 64
combinations), but a generic research profile cannot silently use an unrelated
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
docker compose -f outputs/local-runtime/compose.yml exec board psql -U cleancheck -d memstara
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

Repeat using `exec runtime psql -U cleancheck -d motoro` and replace the database
name in `GRANT CONNECT` with `motoro`. Keep the grants as the `cleancheck` table
owner so future tables are readable too. Do not use the owner account for the viewer.

Install the separate observation API environment and frontend:

```bash
python -m venv viewer/.venv
uv pip install --python viewer/.venv/bin/python -r viewer/requirements.txt
npm --prefix viewer/web ci
```

Before starting the UI, check ports 5173, 8071 and 8072 using the socket check in
step 2 with `ports = (5173, 8071, 8072)`. Do not connect the new UI to an old API or
control process just because those ports respond. If occupied, stop only the
instance you deliberately intend to replace, or choose different API/control ports
and update both matching `server.proxy` targets in `viewer/web/vite.config.ts`.
Use those same ports in the commands below. Keep the browser on port 5173 for the
documented local origin policy. An occupied 5173 must be resolved before continuing.

Start three terminals from the repository root:

1. **Host control:** activate `.venv`, load `.env` and export the local paths from
   step 3, then run `python -m memstara.control --port 8072`.
2. **Read-only observation API:** run the following:

```bash
export MEMSTARA_VIEWER_DSN='postgresql://memstara_viewer:viewer@127.0.0.1:55641/memstara'
export CORE_VIEWER_DSN='postgresql://memstara_viewer:viewer@127.0.0.1:55642/motoro'
viewer/.venv/bin/python -m uvicorn main:app --app-dir viewer/api --host 127.0.0.1 --port 8071
```

3. **Web:** run `npm --prefix viewer/web run dev -- --host 127.0.0.1 --port 5173 --strictPort` and open
   **http://localhost:5173**. This development UI proxies to 8071/8072; it is not the
   Docker-served UI at 8070. Free these ports or update the proxy configuration if
   another instance already occupies them. Node.js 22 is required for this path.

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

### 8. Troubleshooting and verification boundaries

| Symptom | Check / action |
|---|---|
| Foundry credentials missing | Set both API key and resource name in the active terminal; do not rely on an adjacent `.env` |
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
