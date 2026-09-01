# memstara — a personal experiment space

> **The name changed.** `EcoXAI` was a working title; a team decision on 2026-08-18
> made **Memstara** the official one. Code, documents, databases, Docker and the

> alone** — they record what happened on a given day, and renaming them to a name
> nobody was using at the time would stop them being a record.

Where the experiment scripts and requirements live for the work that **uses `motoro`
as a library**. The name starts with `agentic-core-` so the folder alone says what the
experiment is about — the repository kept that name after the library was renamed to
`motoro`.

## What this folder is — a private repository, and a folder that is not backed up

```
EcoXAI_Projects/              ← not a git repository
├── motoro/                   ← a git repository (upstream + my private fork)
└── memstara/     ← here. Its own git repository since 2026-08-30
```

**This folder is a git repository of its own**, created 2026-08-30 and **private**,
at `HyunjunA/memstara`. `EcoXAI_Projects/` above it is not a repository,
so the sandbox is still outside `motoro`'s history and cannot be committed into it by
accident. That much is structural.

**What must not be committed is no longer structural — it is a matter of care.**
`.gitignore` is the whole of the protection, and it draws three lines:

| Never tracked | Why |
|---|---|
| `.env`, `*.pem`, `*.key` | Credentials. `.env.example` is the tracked template. |
| `outputs/*` | The cohort CSV, every sub-CSV cut from it, the matcher's catalogue of all 1,394 column names, and one folder per run. **Patient data and everything derived from it.** All of it is regenerable. |
| `kg/**/*.db`, `kg/**/*.cypherl` | A gigabyte of knowledge-graph exports, published elsewhere. The scripts are tracked; the payloads are not. |

Before it was a repository, it originally sat in `motoro/sandbox/` behind two layers of
ignore rules (`.gitignore`, `.git/info/exclude`). That was only ever safe while the
rules stayed correct, and `.git/info/exclude` does not travel with a clone, so the
protection vanished on any other machine. Moving out removed that dependency, and
**the library repository was restored to exactly upstream's state.**

This folder holds meeting records and photographs. Do not move it back inside the
library repository.

**Where it should live, and who should be able to see it, is not settled** — that is
the first open item, `V-01` (issue
[#1](https://github.com/HyunjunA/memstara/issues/1)).

## Layout

**Flat**, like `examples/`. Scripts read their configuration from the same directory
with `from settings import Settings`, so moving one into a subfolder breaks that
import.

**Documents do not sit at the top level.** `README.md` is the only one; everything
else goes into the folder that matches what it is — with eight documents lying flat
at the top, a reader has to decide where to start every single time. Code being flat
is a different problem with a different reason.

```
memstara/
├── README.md              this file — the only top-level document

│
├── settings.py            CoreSettings subclass (shared by every script)
├── bootstrap.py           the single place the environment is set up
├── preflight.py           check everything before a run, and say what to fix
├── 01_hello_agent.py      the first script — a working-or-not check
│
│                          ── the pipeline ──
├── make_sample_data.py    synthetic dataset + sample OKF bundle (once)
├── prep_hiv_dataset.py    flatten the shared HIV cohort into a sliceable table
├── prep_nhanes.py         the same for the public NHANES survey
├── blackboard.py          the shared work board — table definitions
├── pipeline_core.py       the six agents · supervisor · aggregation
├── 02_mvp_pipeline.py     entry point — supervisor-driven, N trials
├── 03_board_pipeline.py   entry point — the same stages driven by the board
│
│                          ── MCP tool servers ──
├── tools_blackboard.py    the only way an agent touches the board
├── tools_data.py          describe_dataset · slice_columns
├── tools_ml.py            train_and_score
├── tools_okf.py           the OKF corpus, with a reading surface for real literature
├── tools_matcher.py       concept names → exact cohort columns
│
│                          ── looking at what happened ──
├── logging_setup.py       log output (console + JSONL)
├── run_report.py          read a run directory, say whether it went normally
├── trace_run.py           replay a stored run
├── trace_board.py         replay a board run — what was asked, and what came back
├── debug_harness.py       call the tools directly, in one process
├── debug_hook.py          let a debugger attach to a tool server child process
│
├── matcher_impl/          the semantic matcher — catalogue, embedder, vocabulary
├── viewer/                the live web viewer (web :8070, API :8071)
├── scripts/               instruments — cache building, threshold calibration, issues
├── tests/                 pytest
│

├── papers/                papers we obtained (indexed in _INDEX.md)
├── spec/                  the SRS + 10 component implementation plans + templates

├── kg/                    AlzKB and AddictionKB dumps + their loading scripts
└── outputs/               dataset · OKF bundles · run artefacts (indexed in its README.md)
```


what we obtained. That can be decided without opening a file, and each needs only one
index.


example `2026-08-12_AlzKB_구조_설명_KR.md`. When it was written shows up in the
listing itself, and `ls` alone puts them in order.

## This folder becomes the Memstara product

`spec/Memstara_SRS_KR.md` is **the requirements specification for the product**. It
moved here from `Rebuild_2026/` on 2026-08-11, because the product becomes this.

The specification is a **draft (0.3) awaiting approval**, with 15 unresolved items and
proposals needing sign-off marked distinctly. **Read that marking convention before
touching it.**

## What is open right now


it got here. Each item answers five questions: what · why · how we'll know it's done ·
what it depends on · evidence. The shape comes from the four questions in

*Reading order* below is "what are we building", this is "where have we got to".**

All 45 of them are GitHub issues as of 2026-09-01 —
**[issues](https://github.com/HyunjunA/memstara/issues)** ·
the file and line it was written from, and every item in the file carries its issue
number. `scripts/backlog_to_issues.py` keeps the two in step and is safe to re-run.

**`BACKLOG_KR.md`** is a full Korean edition of it, not a summary. **The English file
is the one that becomes issues, and it is the one that is correct if the two


## Reading order

1. **`spec/Memstara_SRS_KR.pdf`** — **what has to be built.** Start with §2.3 (user
   characteristics) and §11 (unresolved items) to see what is settled and what is not

   meeting that cut the MVP down to four stages. `_WHITEBOARD.HEIC` of the same date
   is that meeting's whiteboard

   repository's API. The table in §2 ("what core gives / what I build") sizes the work
   immediately

   to do first.** The items left incomplete against the 8/12 alignment discussion, in
   order
5. **`01_hello_agent.py`** — run this first, to confirm the environment works
6. **`02_mvp_pipeline.py`** — the whole four-stage pipeline



## Running the MVP pipeline

```bash
cd /path/to/Documents/GitHub/EcoXAI_Projects/motoro

# Setup (once) — activate the conda environment
conda activate memstara
python ../memstara/make_sample_data.py

# Environment variables — without these the MCP tool servers cannot find their paths
set -a && . ./.env && set +a
export AGENTIC_OKF_BUNDLE_DIR="$PWD/../memstara/outputs/okf_synthetic_sample"
export MEMSTARA_DATASET_PATH="$PWD/../memstara/outputs/dataset.csv"
export MEMSTARA_OUTPUT_DIR="$PWD/../memstara/outputs"

# 3-trial smoke run → 20-trial real run
python ../memstara/02_mvp_pipeline.py --trials 3 --trace
python ../memstara/02_mvp_pipeline.py --trials 20
```

**The synthetic data has real signal planted in it** — `hba1c` · `bmi` · `age` ·
`systolic_bp` genuinely predict the outcome (univariate AUC 0.73/0.66/0.63/0.60;
noise columns sit at 0.51). If those four come out on top across 20 trials the
pipeline is working; if they do not, something is broken.

### The real operating data (settled 2026-08-23)

Once the synthetic smoke test passes, switch to the data below.

| Role | Path | Contents |
|---|---|---|
| Knowledge source (OKF) | `../shared/hiv-suppression/okf/` | 142 papers on HIV suppression, across 8 domain folders |
| ML dataset | `../attri_shared/ecoxai_dataset_2.5pct_no_PHI.csv` | 1,707 patients × 1,393 features, outcome `HIV_DETECTABLE` |

```bash
export AGENTIC_OKF_BUNDLE_DIR=../shared/hiv-suppression/okf
export MEMSTARA_DATASET_PATH=../attri_shared/ecoxai_dataset_2.5pct_no_PHI.csv
export MEMSTARA_OUTCOME_COLUMN=HIV_DETECTABLE
python 03_board_pipeline.py --trials 3 --trace
```

**Who reads what:**
- OKF → the hypothesis agent reads it and proposes which features to select
- the cohort CSV → the data and ML agents read it and check the proposal for real

The OKF bundle also contains **four trap concepts that point at variables the dataset
does not have.** The place this pipeline breaks first is the gap between a concept
name in the knowledge source and a column name in the dataset, so the examples
reproduce that on purpose.

## Setup (once)

```bash
cd /path/to/Documents/GitHub/EcoXAI_Projects/motoro

# 1) Infrastructure — postgres :5453, redis :6381, schema applied
cp .env.example .env          # then fill in the API keys in .env
docker compose up -d

# 2) Python — conda. core goes in as an editable install
#    (run from the sandbox folder; environment.yml points at ../motoro by relative path)
conda env create -f ../memstara/environment.yml
conda activate memstara
```

> **core is `motoro` throughout** (2026-09-01, as of `v0.5.2`).
> Python package `motoro` (`from motoro import ...`), local folder `../motoro/`,
> environment-variable prefix `MOTORO_`, Docker containers
> `motoro-postgres`/`motoro-redis`, databases `motoro`/`motoro_test`, alembic version
> table `alembic_version_motoro`.
> `environment.yml` and `.vscode/launch.json` point at `../motoro` by relative path,
> so **renaming the folder means fixing both.**
>
> **Two names do not follow this rule.**
> One is **this repository's own name, `memstara`**, kept so the folder
> name alone says what the experiment is about (see the top of this file).
> The other is **`AGENTIC_OKF_BUNDLE_DIR`**, which upstream reads as that literal
> string without going through the prefix
> (`motoro/src/motoro/mcp_servers/okf.py:66`, `mcp/client.py:57`) — renaming it to
> match the prefix means **the OKF server cannot find its bundle.**
>
> The Postgres role name stays **`agentic`**. Upstream itself uses
> `POSTGRES_USER=agentic` (`motoro/.env.example:6`), so changing it here would put
> this repository out of step with upstream.

Python is one conda environment, **`memstara`** (3.12). `motoro` is installed
editable, so editing its source takes effect without reinstalling. Tool servers are
launched with `sys.executable`, so child processes use the same environment.

VS Code points at this environment through `.vscode/settings.json`. Choosing conda
`base` fails as early as `import asyncpg`.

`.env` needs at least one provider credential:

```bash
ANTHROPIC_API_KEY=sk-ant-...
# or Foundry — both are required
ANTHROPIC_FOUNDRY_API_KEY=...
ANTHROPIC_FOUNDRY_RESOURCE=...
```

## Running

```bash
cd /path/to/Documents/GitHub/EcoXAI_Projects/motoro
set -a && . ./.env && set +a          # load .env into the environment
python ../memstara/01_hello_agent.py --input "What is 17 times 23?"
```

Forgetting `set -a && . ./.env && set +a` makes it fail at the database connection or
at resolving credentials.

## Adding a new experiment script

1. Create `NN_name.py` in this folder (the number exists only to make the order easy
   to see).
2. At the very top, call `from settings import Settings` → `configure(Settings())`
   **first, before anything else.** Calling it after a core module has started reading
   configuration raises `RuntimeError`.
3. Copying `01_hello_agent.py` is the fastest way to start.

## Reference

- The full public API and usage examples: `../AgenticCore_상세해설_KR.pdf` §4, outside
  this repository
- The original examples core ships: `../motoro/examples/` (provision / run /
  memory_run / mcp_run)

