# Memstara Viewer

A living scene in which the pipeline's agents exist as **characters** and the board,
knowledge source, dataset, trainer and results table each have a **place**. Run the
pipeline and you watch, in real time, a character walk to the board, pick up a row, carry
it to their own place, work on it and put it back.

**Five characters, and one of them used to be two.** The pipeline has five stages
(`viewer/api/stores.py:233-239`). It had six until 2026-09-07, when the `curator` was
merged into the hypothesis agent — writing the wave's questions is that agent's other job
now, done in a separate call with a separate set of tools.

**The viewer still knows the retired name, and must keep knowing it**
(`viewer/api/stores.py:153`). Hundreds of runs in the database are recorded against
`memstara-board-curator`, and `viewer/api/scene.py:517` drops any row whose agent name the
viewer does not recognise. Forget the name and that spend leaves the cost total with
nothing on any screen to say so. So `DRAWN_AS` (`viewer/api/stores.py:277`) is now a
compatibility layer rather than a drawing choice: it folds those historical rows into the
hypothesis agent, which is the agent that does that work today.

**Their numbers are added, not dropped.** Runs, tokens, calls and cost are the same totals
as before the fold; what you cannot ask the viewer is what the curator alone cost, and
`verify.py` reads the databases unfolded, which is why the checks below still work. The
Log panel prints `curator0` for a run made before the merge and `question0` for one made
after, because that panel tails the pipeline's stdout and rewriting a console is
falsifying a record.

```bash
docker compose up -d --build     # → http://localhost:8070
python3 verify.py                # every screen value, compared against the DBs
```

`verify.py` prints its own tally at the end — read that rather than trusting a count
written here, which goes stale the next time a check is added.

During development the two are started separately.

```bash
.venv/bin/uvicorn main:app --app-dir api --port 8071 --reload
cd web && npm run dev            # → http://localhost:5173 (/api proxies to 8071)
```

## The screens

| | What |
|---|---|
| **Scene** | Six places and five characters. Click the board or the results table for that tab, click a character for that agent |
| **Board** | Waiting / in progress / done lanes. Cards carry `attempts` and how many times the row came back |
| **Life of a row** | The trail of one row through the four stages, and the run id that handled each |
| **Agents** | Runs, iterations, tokens, cost, and the tools each stage is given |
| **Access map** | Who reached which store, through which tool, how many times |
| **Results** | AUC · importances · interpretation |

## Read-only is a permission, not a habit

The connecting account `memstara_viewer` holds `SELECT` and nothing else. It is read-only
not because the code is careful but because **the database refuses** — `verify.py` checks
on every run that an attempted `UPDATE` or `DELETE` is blocked. Changing the board is
still the tools (MCP) and the driving script, and only those.

## The Start button is a different service

The control panel can start a run, and **nothing above changes because of it.** The
button does not talk to `/api/`; it talks to `/control/`, which nginx proxies to a
separate process on the host (`python -m memstara.control`, 127.0.0.1:8072). That
process is in the sandbox's own environment, which is the only place a pipeline can be
launched from — this container has no `.venv`, no `../motoro` and no `.env`, and it is
not going to get them.

So the two failure modes stay apart. The viewer with no control service is the ordinary
state: everything is drawn, the third health dot is red, and the panel says which command
to run. The control service can also be up while a database is down, and the screen says
that too.

It binds the loopback interface and refuses a request that arrives under an unfamiliar
host name, from an origin that is not this viewer, or without a JSON content type. It
starts processes; those three are what keeps a page on the open web from starting one.
Exposing it beyond localhost needs an answer about authentication first, and there isn't
one.

## ⚠️ The record comes in three shapes

Read `run_steps.tool_call` naively and you get numbers that are **plausibly wrong**.

| The trap | Read naively |
|---|---|
| Rows where the column is `json` and the value is the **JSON literal `null`** | Steps with no tool call get counted as calls |
| Two shapes: single `{server,tool,…}` and **batched `{"calls":[…]}`** | `search_concepts` appears to run 0 times (really hundreds) |
| The `ecoxai-*` server name on older rows | One server splits into two |

All three are handled in one place, `FLAT_CALLS` in `api/queries.py`. `verify.py` goes as
far as checking that **the naive aggregate and the correct one must differ** — if they
happened to agree, the tests would still pass after the trap handling was deleted.

## Why there is a backend

A browser cannot connect to Postgres directly. And if six screens each interpreted
`tool_call` themselves, they would draw the same run differently. A single
`/api/snapshot` hands over the data for every screen **at once**, and the front end picks
from it — one request every two seconds.

Two endpoints stand outside that and are fetched per item, when a person opens one:
`/api/task/{task_id}` and `/api/result/{result_id}`. The second is the one with a measured
reason. `match_trace` — the matcher's candidates, chosen and rejected alike — is 598 kB
across the 81 stored results against 89 kB for every explanation column the snapshot does
carry, with one row at 23.6 kB. Polling that thirty times a minute to show something
nobody has opened is what the split avoids, not a preference about shape.

That trace is also the only place the **rejected** candidates exist. The board and the
results table keep the columns that were chosen, so "it picked `DX__D64.9__Anemia,
unspecified`" was already on screen and "it picked that over `DX__D50.9__Iron deficiency
anemia` at 0.975" was nowhere. The Results panel's *Why these columns* section is what
reads it.

## The board is still visible when core is down

The board (`memstara-postgres:5463`) and the agent records (`motoro-postgres:5453`) are
different servers. If one dies, only that part shows a notice and the rest is drawn as
usual — a character becomes **`unknown`**, not `idle`. So as not to claim to know
something we do not.

## The definitions come from the pipeline

`api/stores.py` uses `pipeline_core.BOARD_TOOLS` / `BOARD_SERVERS`. When the viewer runs
in its own virtualenv and the import fails, it falls back to a written-down copy — and
once that copy goes stale, only the screen is wrong, quietly. Hence a separate
cross-check.

```bash
# From viewer/. Needs an interpreter that can import both pipeline_core and motoro.
../.venv/bin/python check_definitions.py
```

## What it does not do

- **Change anything it shows** — the databases refuse it. Starting a run is the one
  exception and it goes through a different process; see above
- Game engine, canvas, pixel assets — SVG and CSS transitions are enough
- Authentication — localhost only
