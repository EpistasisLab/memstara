# Memstara Viewer

A living scene in which the five agents exist as **characters** and the board, knowledge
source, dataset, trainer and results table each have a **place**. Run the pipeline and you
watch, in real time, a character walk to the board, pick up a row, carry it to their own
place, work on it and put it back.

```bash
docker compose up -d --build     # → http://localhost:8070
python3 verify.py                # 25 verification items
```

During development the two are started separately.

```bash
.venv/bin/uvicorn main:app --app-dir api --port 8071 --reload
cd web && npm run dev            # → http://localhost:5173 (/api proxies to 8071)
```

## The screens

| | What |
|---|---|
| **Scene** | Five places and five characters. Click the board or the results table for that tab, click a character for that agent |
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

- **Control anything** — it is read-only
- Game engine, canvas, pixel assets — SVG and CSS transitions are enough
- Authentication — localhost only
