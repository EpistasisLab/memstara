# Memstara

A multi-agent pipeline that reads a literature corpus, proposes which features should
predict a clinical outcome, tests that proposal against a patient cohort, and writes up
what held. The agents coordinate through a shared board in Postgres, and every capability
they have is an MCP tool server — an agent can do exactly what it has been handed a tool
for, and nothing else.

**`memstara` is a working title, not the name.** The folder on disk and the
repository on GitHub still carry it, which is why every path and link below reads that
way — the project is Memstara.

It builds on **`motoro`** as a library: motoro supplies the agent runtime, the MCP client
and persistence. Everything under `src/memstara/` is this project.

## Quick start

```bash
conda activate memstara
python -m memstara.pipeline.hello --input "What is 17 times 23?"   # does the environment work
python -m memstara.prep.sample                                     # synthetic cohort + corpus
python -m memstara.pipeline.board --trials 3                       # a real run, 3 hypotheses
```

`hello` needs only a provider key. The other two need the environment in **Setup** below.

## Architecture

Two entry points run the same five stages. They differ in **who decides what happens
next**, and that is the only difference worth knowing:

```
  board.py  — agents coordinate through the board; the driver only turns the handle
  mvp.py    — a supervisor calls each stage in turn

  corpus (OKF)                       cohort CSV
      │                                   │
      ▼                                   ▼
  ┌────────────┐  question  ┌────────────┐   task   ┌──────┐   sub-CSV   ┌────┐
  │ hypothesis │ ─────────▶ │ hypothesis │ ───────▶ │ data │ ──────────▶ │ ml │
  │  (asking)  │            │(answering) │          └──────┘             └────┘
  └────────────┘            └────────────┘                                  │
       ▲                          │                                         │
       │      results of the      │  ┌───────────────┐    AUC + importance  │
       └──── previous wave ───────┘  │  interpreter  │ ◀─────────────────────┘
                                     └───────────────┘
                                             │
                                             ▼   once, at the end
                                        ┌────────┐
                                        │ report │
                                        └────────┘
```

**The board is the coordination.** A stage claims a row, works, and writes a result back;
nothing is passed from agent to agent directly. This is what makes a run resumable, lets
more than one worker of a stage run at once, and leaves a record that can be replayed
afterwards with `python -m memstara.trace.board`.

**The two boxes at the front are one agent.** The hypothesis agent writes the wave's
questions and then answers them, in two calls holding two different sets of tools. There
was a separate `curator` agent doing the asking until 2026-09-07; what kept the two jobs
apart was never the agent boundary but the tool grant, and that is unchanged.

**A wave is one turn of that loop.** With `--waves 2` or more, the question call reads the
previous wave's results before writing the next round of questions — that feedback path
is the reason `read_results` is in the question call's tools and not the answering call's.

## The agents

Five agents on the board pipeline. Each one's system prompt is a file, so changing what an
agent does does not mean touching `core.py`.

| Agent | What it decides | Tools | Prompt |
|---|---|---|---|
| `hypothesis` | **what gets asked** — writes the wave's questions from the corpus | 6 | `prompts/board/hypothesis.md`, first half |
| `hypothesis` | which columns should predict the outcome, and puts the work on the board | 8 | `prompts/board/hypothesis.md`, second half |
| `data` | cuts the requested columns into a sub-dataset | 4 | `prompts/board/data.md` |
| `ml` | trains on that sub-dataset, records AUC and feature importance | 3 | `prompts/board/ml.md` |
| `interpreter` | whether the hypothesis held | 2 | `prompts/board/interpreter.md` |
| `report` | the account of the whole run, once, after everything else | 3 | `prompts/board/report.md` |

The allocation is `BOARD_TOOLS` in `src/memstara/pipeline/core.py`, plus `QUESTION_TOOLS`
beside it for the hypothesis agent's asking call, and it is the ground truth — the table
above is a reading of it, not a second copy to keep in step:

```
hypothesis   okf_list_domains  okf_search  okf_read  read_questions  read_results  propose_questions
  (asking)
hypothesis   okf_list_domains  okf_search  okf_read  describe_dataset  match_concepts  match_concept
 (answering) claim_question  create_task
data         describe_dataset  slice_columns  claim_task  submit_result
ml           train_and_score  claim_task  submit_result
interpreter  claim_task  submit_result
report       read_results  okf_search  okf_read
```

Three things in that list are deliberate and easy to undo by accident:

- **Only `hypothesis` can `create_task`.** Every other stage takes work rather than making
  it. That is what lets a result be traced back to whose judgement produced it.
- **`read_results` and `propose_questions` are in the asking call, not the answering
  one.** The first is the whole feedback path between waves. Grant either to the answering
  call and a worker part way through the corpus can notice a promising column and write
  itself the question that column answers — which breaks the contract the stage is
  supposed to keep: one question in, one hypothesis out. `call_agent` takes the agent id
  and the tool list as separate arguments, so this holds even though one agent makes both
  calls: a tool absent from a call cannot be reached however the prompt is worded.
- **`interpreter` has two tools.** It is meant to reason over what it is handed, not go
  looking for more.

`mvp.py` runs four of these — `hypothesis`, `data`, `ml`, `interpreter` — under a
supervisor, with prompts in `prompts/mvp/`. There is no question step and no board.


rule file that loads when you do; the short version is that a prompt is an experimental
condition, so changing one and changing the code are two different commits.

## The tool servers

Five servers, each its own child process, launched with `sys.executable`. They are named
once in `src/memstara/servers.py` and nowhere else.

| Server | Module | What it exposes |
|---|---|---|
| `okf` | `mcp_servers/okf.py` | knowledge lookup over the OKF bundle |
| `memstara-data` | `mcp_servers/data.py` | the cohort CSV — describe it, slice columns out of it |
| `memstara-ml` | `mcp_servers/ml.py` | train a model on a subset and score it |
| `memstara-blackboard` | `mcp_servers/blackboard.py` | the shared work board the agents read and write |
| `semantic-matcher` | `mcp_servers/matcher.py` | OKF concept name → cohort column name |

Filtering happens in two layers: `BOARD_SERVERS` decides which servers a stage may reach
at all, then `BOARD_TOOLS` narrows again by tool name inside them.

**A traceback inside a server does not reach the console you are watching.** Read


`semantic-matcher` needs its cache built once: `python scripts/build_matcher_cache.py`.

## Layout

One package, `src/memstara/`, and no Python at the top level. Everything is reached by
import path and every entry point is run with `-m`.

```
src/memstara/
├── __init__.py        one statement, no imports — see its docstring
├── paths.py           resolves every path in the repository, once
├── config.py          the Settings subclass everything shares
├── env.py             the one place the environment is prepared
├── servers.py         names the five tool servers, once
├── blackboard.py      the shared board — table definitions
├── logging_setup.py   console + JSONL
├── preflight.py       checks everything before a run and says what to fix
├── debug_harness.py   calls a tool directly, in one process
│
├── pipeline/          hello · core (agents, supervisor, aggregation)
│                      mvp (supervisor-driven) · board (board-driven) · prompts (loader)
├── prompts/           one system prompt per agent, as files
├── mcp_servers/       one process per server, plus debug_hook and frontmatter
├── control/           a host service so the viewer can start a run
├── trace/             replay a saved run: run · board · report
├── prep/              build a cohort: sample · hiv · nhanes
└── matcher/           semantic matcher — catalogue, embedder, vocabulary

viewer/                live web viewer (web :8070, API :8071)
scripts/               cache building, calibration, checks
tests/                 pytest, fully offline

outputs/               datasets, OKF bundles, run records — never committed
```

## Setup

```bash
# 1) Infrastructure — postgres, redis, schema applied
cp .env.example .env          # then fill in an API key
docker compose up -d

# 2) Python — conda. motoro is installed editable
conda env create -f environment.yml
conda activate memstara
```

Python is one conda environment, **`memstara`** (3.12). Tool servers are launched with
`sys.executable`, so a child process gets the same environment. VS Code points at it
through `.vscode/settings.json`; picking conda `base` fails as early as `import asyncpg`.

`.env` needs at least one provider credential:

```bash
ANTHROPIC_API_KEY=sk-ant-...
# or Foundry — both are required
ANTHROPIC_FOUNDRY_API_KEY=...
ANTHROPIC_FOUNDRY_RESOURCE=...
```

## Running

Every run is launched from the `motoro` checkout, because that is where `.env` and the
compose file live:

```bash
cd /path/to/Documents/GitHub/EcoXAI_Projects/motoro
conda activate memstara
set -a && . ./.env && set +a          # read .env into the environment

export AGENTIC_OKF_BUNDLE_DIR="$PWD/../memstara/outputs/okf_synthetic_sample"
export MEMSTARA_DATASET_PATH="$PWD/../memstara/outputs/dataset.csv"
export MEMSTARA_OUTPUT_DIR="$PWD/../memstara/outputs"

python -m memstara.pipeline.board --trials 3            # board-driven
python -m memstara.pipeline.mvp --trials 3 --trace      # supervisor-driven
```

Skipping `set -a && . ./.env && set +a` fails at the database connection, or at resolving
credentials.

**The synthetic data has real signal planted in it** — `hba1c` · `bmi` · `age` ·
`systolic_bp` genuinely predict the outcome (univariate AUC 0.73 / 0.66 / 0.63 / 0.60;
the noise columns sit at 0.51). If those four rise to the top over 20 trials the pipeline
is working; if they do not, something is broken.

### The real operating data

| Role | Path | What it is |
|---|---|---|
| Knowledge source (OKF) | `../shared/hiv-suppression/okf/` | 142 papers on HIV suppression, across 8 branch folders |
| ML dataset | `../attri_shared/ecoxai_dataset_2.5pct_no_PHI.csv` | 1,707 patients × 1,393 features, outcome `HIV_DETECTABLE` |

The OKF bundle also contains **four decoy concepts naming variables the dataset does not
have.** The first place this pipeline breaks is the gap between concept names in the
knowledge source and column names in the dataset, so the example reproduces it on purpose.

## Configuration

`board.py` — the board-driven pipeline:

| Flag | Default | What it does |
|---|---|---|
| `--trials` | 1 | hypotheses seeded per wave |
| `--waves` | 1 | question-then-investigate rounds; wave 2 onward reads the previous wave's results |
| `--stop-after-dry` | 2 | stop early after this many waves in which the question step produced no new question; 0 never stops early |
| `--no-curator` | off | skip question generation, use the built-in perspective list. Keeps its name although there is no curator agent any more: the flag is already typed in saved command lines and its meaning has not changed |
| `--skill` | *(whole bundle)* | confine the corpus to one branch, as front-matter equalities: `terminus_kind=sud` |
| `--y-column` | `outcome` | the outcome column. **A literal default, not read from the environment** (`src/memstara/pipeline/board.py:1856`) — `outcome` is the synthetic dataset's column (`src/memstara/prep/sample.py:90`), so a real cohort needs this passed explicitly or the pre-flight stops the run. `mvp.py` is the one that falls back to `MEMSTARA_OUTCOME_COLUMN` (`src/memstara/pipeline/mvp.py:425`) |
| `--provider` | `azure_foundry` | `anthropic` · `azure_foundry` · `openai` |
| `--model` | `claude-sonnet-4-6` | model id |
| `--data-agents` `--ml-agents` `--interpret-agents` | 1 | how many workers of that stage claim from the board at once |
| `--hypothesis-agents` | 1 | how many seed the board at once; each claims its own question |
| `--max-attempts` | 5 | give up on a task after this many extra returns, mark it failed, go on; 0 retries forever |
| `--stale-after` | 600 | seconds a task may sit `in_progress` before it is presumed abandoned |
| `--run-tag` | — | names this run on the board |
| `--report-only` | off | write the report from what has already finished |
| `--verbose` `--run-dir` | — | console DEBUG · where to write this run's records |

`mvp.py` — the supervisor-driven pipeline: `--trials`, `--concurrency` (rate-limit cap),
`--y-column`, `--provider`, `--model`, `--no-overall` (skip the aggregate
interpretation), `--ablate-okf` (run without the OKF tools), `--trace`, `--verbose`,
`--run-dir`.

Environment:

| Variable | What it points at |
|---|---|
| `AGENTIC_OKF_BUNDLE_DIR` | the knowledge bundle. **Not** `MEMSTARA_*` — see below |
| `MEMSTARA_DATASET_PATH` | the cohort CSV |
| `MEMSTARA_OUTPUT_DIR` | where runs, sub-datasets and reports are written |
| `MEMSTARA_OUTCOME_COLUMN` | the label the matcher and the data server exclude from every column list (`src/memstara/mcp_servers/data.py:115`, `src/memstara/matcher/service.py:64`). It is **also** `mvp.py`'s default `--y-column` and **not** `board.py`'s — see that flag above |
| `MEMSTARA_DATABASE_URL` | the board's Postgres |
| `MEMSTARA_ML_ENGINE` | which learner `train_and_score` uses |
| `MEMSTARA_DEBUGPY` / `_WAIT` | attach a debugger to a tool-server child process |

## What is never committed

`.gitignore` is the whole of the protection, and it draws three lines:

| Never tracked | Why |
|---|---|
| `.env`, `*.pem`, `*.key` | credentials. `.env.example` is the tracked template |
| `outputs/*` | the cohort CSV, every sub-CSV cut from it, the matcher's catalogue of 1,393 column names, and one folder per run. **Patient data and everything derived from it.** All of it is regenerable |
| `kg/**/*.db`, `kg/**/*.cypherl` | a gigabyte of knowledge-graph exports, published elsewhere. Scripts tracked, payloads not |

`*_KR*` is also ignored: the Korean editions live on the machine that writes them and in
no clone. The repository is private.

**`HIV_DETECTABLE` is the target column and is never a feature.** It is legitimate as
`--y-column`. It must never appear in a column list handed to an agent — a model that can
see the label does not predict it, it reads it.

## Tests and checks

```bash
ruff check src/                      # lint
python -m pytest -q                  # 148 tests, fully offline, ~4s
python scripts/check_citations.py    # every file.py:NNN cited in prose points somewhere real
```

Those three are what CI runs. **None of them starts a server, connects to Postgres, or
calls a model** — any claim about those is made by hand, in a commit's `Verified:` line,
or it is not made. The citation checker proves a cited line exists, not that it still says
what the citing text claims.

There is no type checker: `src/` carries no type hints, so `--strict` would produce
thousands of findings and one habit, which is ignoring the output.

## Conventions that are not obvious

**Always `python -m memstara.<module>`, never by file path.** Running a file by its path
skips `src/memstara/__init__.py`, the only place `LITELLM_LOG` is set before litellm can
read it — and litellm reads it *while being imported*, so setting it a moment later logs
nothing and raises nothing. Under `-m` the ordering cannot be got wrong. `-m` is not a
matter of taste here.

**`configure(Settings())` first, before anything else in an entry point.** Calling it
after a motoro module has started reading configuration raises `RuntimeError`. Copy
`src/memstara/pipeline/hello.py` rather than writing the preamble from memory.

**Three names look like inconsistencies and are not:**

> **`AGENTIC_OKF_BUNDLE_DIR`** — upstream reads that literal string without going through
> the environment prefix (`motoro/src/motoro/mcp_servers/okf.py:66`,
> `mcp/client.py:57`). Renaming it to match `MOTORO_*` means **the OKF server cannot find
> its bundle**, at run time, with no import error to warn you.
>
> **The Postgres role stays `agentic`.** Upstream itself sets `POSTGRES_USER=agentic`
> (`motoro/.env.example:6`), so changing it here puts this repository out of step with the
> library it consumes.
>
> **The repository keeps the folder name `memstara`** — a working title the
> folder and the remote still carry, so paths and links keep spelling it.

`environment.yml` and `.vscode/launch.json` point at `../motoro` by relative path, so
renaming that folder means fixing both.

Commits follow `type: short description` and carry a **`Verified:`** line naming a

loads on every session; four more load only inside the directory they apply to.

## Where work is tracked


why, how we will know it is done, what it depends on, and the evidence. All 45 items are
GitHub issues —
[issues](https://github.com/HyunjunA/memstara/issues) ·
line it was written from.

Each item carries two labels on two axes, both required: a **kind** (`bug`,
`enhancement`, `research-decision`, `verification`, `housekeeping`) and an **area**, which
reaches GitHub as `area:matcher`. A value outside either vocabulary is a hard error.

Do not open an issue without a backlog item behind it.

## Documents

| Folder | What is in it |
|---|---|

| `papers/` | what we obtained. Indexed in `papers/_INDEX.md` |
| `spec/` | the SRS, plus one implementation plan per component |

| `kg/` | AlzKB · AddictionKB load scripts |


them in order.


not to fix a name, not to repair a citation. Rewriting one to say what we know now would
stop it being a record. `scripts/check_citations.py` skips both by name and prints the
reason on every run.

**Korean editions carry `_KR` and are not in the repository.** A `_KR` file is a full
mirror, not a summary, and **the English file is the one that is correct if the two
disagree.** Nothing checks them: they are not scanned for citations and CI never sees
them, so a citation *into* one is reported as *not verifiable here*.
