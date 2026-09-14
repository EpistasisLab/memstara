"""The SQL. Kept in one file so the three record shapes are handled in exactly one place.

`run_steps.tool_call` comes in three shapes, and getting this wrong produces numbers
that look plausible and are not:

1. The column is `json`, and many rows hold the JSON literal `null` rather than SQL
   NULL. `tool_call IS NOT NULL` is therefore true for 424 rows that contain no call at
   all. Filter on `json_typeof(tool_call) = 'object'`, which also excludes anything that
   is not a call-shaped document. `::text <> 'null'` admits the same rows and is the
   obvious way to write it, but it serialises the whole value to compare it with four
   characters; see the note above `_FLAT_SELECT` for what that cost.
2. A step may hold **one** call `{server,tool,arguments,result}` or a **batch**
   `{"calls":[…]}`. Reading only the first shape reports `search_concepts` as 0 calls
   when the real figure is 458 — the knowledge-source searches all arrive batched.
3. Rows written before the 2026-08-18 rename carry `ecoxai-*` server names. Left alone,
   the access map lists one server twice.

`llm_call` has the same JSON-null problem: 1,622 rows are `IS NOT NULL`, only 700 hold
a value.

==============================================================================
 How to read this file
==============================================================================

 What this file does
   Almost nothing here executes. It is all **string constants (SQL).** scene.py feeds
   these constants to conn.fetch(). The top three are for the Memstara DB (the board
   and the results table), the rest for the core DB (agents and run history).

 The constants
   _FLAT_SELECT  ★ flattens the two call shapes into one relation. The foundation of
                 the five queries below it
   FLAT_TEMP_TABLE  that SELECT as a temp table, built once per connection by
                 `_core_facts` (`scene.py:230`)
   FLAT_CALLS    now empty. It stays as a name so each of the five still says at its own
                 site that it depends on `flat`
   --- Memstara DB ---
   RUNS          per run (run_tag): task count, done count, first/last time
   BOARD         every task row of one board
   RESULTS       the results table
   --- core DB ---
   AGENT_TOTALS  per agent: runs, tokens, cost
   OPEN_RUNS     ★ the runs actually going right now (by heartbeat)
   ACCESS        calls per agent × tool = the access map
   TASK_TOUCHES  ★ the bridge tying the board to the runs
   LAST_CALL     the most recent call per agent = where the character is standing
   LAST_ROSTER   ★ the workers of the most recent run, however long ago it was
   RECENT_CALLS  calls within the last few seconds = the flashing lines
   FEED          the newest calls regardless of age = the feed panel's rows

 Easy things to miss
   1. Everything that counts tool calls is built **on top of `flat`.** That is so the
      three traps are handled once. Build any new aggregate on it too — and if you do,
      it must run on the connection `_core_facts` built the table on.
   2. `$1` is asyncpg's positional argument. The window value arrives from the Python
      side (scene.py) as a string and is turned into an `::interval`.
   3. `WHERE ($1 = '' OR run_tag = $1)` means "an empty string means everything".
   4. verify.py recomputes the same numbers with **SQL written separately from this**
      and compares them. If this file regresses, that is what catches it.
==============================================================================
"""

# Flatten both call shapes into one relation. Everything that counts tool calls builds
# on this, so the three traps are dealt with once. ★ The heart of this file.
#
#   above the UNION ALL = a step holding **one** call (`tool_call->>'server'` is there)
#   below the UNION ALL = a step holding **several** calls (the `tool_call->'calls'`
#                         array is unpacked with `json_array_elements`)
#
#   Both sides **throw away the JSON literal null first**, with
#   `json_typeof(s.tool_call) = 'object'`. `IS NOT NULL` does not filter it (trap 1).
#   And `replace(..., 'ecoxai-', 'memstara-')` folds the old server name in (trap 3).
#
#   Every query that counts tool calls reads the result. That is what makes the three
#   traps handled **once** and done with.
#   It used to be a CTE that each of the five queries carried its own copy of, and that
#   is what made the screen stop: five copies is five scans of `run_steps`, ~0.9s each,
#   so one poll cost ~6s against a 2s interval. Polls then overlapped, the core DB was
#   measured at 531% CPU running four copies of this same query at once, and the
#   connection pool drained. Now it is built **once** per `_core_facts` and the five
#   read the result.
#
#   `json_typeof(...) = 'object'` replaced `tool_call::text <> 'null'`. The old form
#   serialised the whole value — averaging 2.5kB and reaching 46kB, since LLM output is
#   in there — for every row, only to compare it with a four-character literal.
#   `json_typeof` reads the first token. Both admit the same rows: measured, 3234 in
#   each case.
#
#   The `steps` CTE exists for the `::jsonb` in it, and that cast is the other half of
#   the speed-up. `run_steps.tool_call` is `json`, which Postgres stores as **text**: a
#   `->` on it re-parses the whole document, and this query used to do five of them per
#   row on documents reaching 46kB. `jsonb` is parsed once and then indexed into. Same
#   3234 rows either way; measured 1.0s to 0.19s.
#: The only tools whose `arguments` and `result` anything reads — TASK_TOUCHES, to pull
#: `task_id`, `run_tag` and `worker` out of them (see its comment below). Every other
#: tool's payload is carried into `flat`, written to disk, and never looked at; and it is
#: the expensive half of the table, because a tool that calls a model puts the model's
#: whole answer in `result`, up to 46kB of it. So the two columns are kept for these four
#: and nulled for the rest. If a new query needs a payload, widen this list — do not
#: reach past `flat` for it.
#:
#: `claim_question` was added on 2026-09-08, and this is the sanctioned widening the
#: paragraph above describes rather than an exception to it. **It is the only place a
#: hypothesis worker writes its own name down.** The other three stages take their work
#: off the board and so pass `worker=` to `claim_task`; the hypothesis stage creates the
#: work instead, and the tool it passes `worker=` to is this one
#: (`src/memstara/mcp_servers/blackboard.py:799`) — `create_task` has no such argument.
#: Leave it out and the one stage `--hypothesis-agents` actually multiplies is the one
#: stage whose workers cannot be told apart. Its payload is cheap: the result is a single
#: question row, not model output.
BOARD_TOOLS = ("create_task", "claim_task", "claim_question", "submit_result", "propose_questions")
_TOOLS_SQL = "('" + "', '".join(BOARD_TOOLS) + "')"


def _payload(prefix: str, expr: str) -> str:
    """`expr` on `prefix`, but only for a board tool; NULL otherwise."""
    return f"CASE WHEN {prefix}->>'tool' IN {_TOOLS_SQL} THEN {prefix}{expr} END"


_FLAT_SELECT = f"""
WITH steps AS (
    SELECT s.run_id,
           s.id                AS step_id,
           s.started_at,
           s.tool_call::jsonb  AS tc
    FROM run_steps s
    WHERE json_typeof(s.tool_call) = 'object'
)
SELECT run_id,
       step_id,
       started_at,
       replace(tc->>'server', 'ecoxai-', 'memstara-')  AS server,
       tc->>'tool'                                     AS tool,
       {_payload("tc", "->'arguments'")}               AS arguments,
       {_payload("tc", "->>'result'")}                 AS result
FROM steps
WHERE tc->>'server' IS NOT NULL
UNION ALL
SELECT run_id,
       step_id,
       started_at,
       replace(c->>'server', 'ecoxai-', 'memstara-'),
       c->>'tool',
       {_payload("c", "->'arguments'")},
       {_payload("c", "->>'result'")}
FROM steps,
     jsonb_array_elements(tc->'calls') c
WHERE tc->'calls' IS NOT NULL
"""

#: Run once, first thing, on the connection the five queries below will use. Dropped
#: first because the connection is pooled and will already carry the table from the
#: previous poll.
FLAT_TEMP_TABLE = "DROP TABLE IF EXISTS flat; CREATE TEMP TABLE flat AS " + _FLAT_SELECT

#: Kept as a name so the five queries still read `FLAT_CALLS + \"\"\"SELECT ...\"\"\"`, which
#: is what says at each site that it depends on `flat` existing. It is empty because the
#: table is now real rather than a CTE the query has to define for itself.
SCOPED_FLAT_TEMP_TABLE = FLAT_TEMP_TABLE.replace(
    "FROM run_steps s",
    "FROM run_steps s JOIN selected_run_ids selected ON selected.id = s.run_id",
)

FLAT_CALLS = ""

# --- Memstara's database ---------------------------------------------------- #

# The three from here (RUNS, BOARD, RESULTS) go out to the memstara DB, where the board
# lives. Remember that this is **an entirely separate connection** from the core DB
# below (see db.py).

# RUNS — the list that goes into the "run selector" at the top of the screen.
#   `count(*) FILTER (WHERE status = 'done')` counts "how many of them finished" in one
#   scan. It is in reverse order of last update, so **the most recent run comes first** —
#   that ordering is what lets scene.snapshot pick [0] when it is given no run_tag.
RUNS = """
SELECT run_tag,
       count(*)                                    AS tasks,
       count(*) FILTER (WHERE status = 'done')      AS done,
       min(created_at)                             AS first_seen,
       max(updated_at)                             AS last_seen
FROM memstara_blackboard
GROUP BY run_tag
ORDER BY max(updated_at) DESC
"""

# BOARD — every task row of one board. The cards on screen come from here.
#   `($1 = '' OR run_tag = $1)` → **give it an empty string and it fetches everything,**
#   regardless of run. (/api/task/{id} uses this, because a task has to open straight
#   from a link whichever run it belongs to.)
#   Ordered by task_id, so what appears on screen is in the same order every time.
BOARD = """
SELECT task_id, run_tag, trial, perspective, status, task_type, attempts,
       hypothesis, columns, y_column, columns_used, columns_missing, auc,
       feature_importance, interpretation, error,
       claimed_at, created_at, updated_at
FROM memstara_blackboard
WHERE ($1 = '' OR run_tag = $1)
ORDER BY task_id
"""

# RESULTS — the results table. That it is **a different table** from the board matters.
#   The board holds *what is moving*, the results table *what was found*. So the scene
#   draws them in different places too (see TOOL_STORE in stores.py).
#   **The explanation is selected from here, not from the board.** `feature_importance`,
#   `columns_missing` and `okf_concept_ids` live on both tables, and reading them off the
#   board loses them the moment the board row is cleaned away: `memstara_results.task_id`
#   is `ON DELETE SET NULL`, so a finished result outlives the row it came from. Taking
#   them from the result means "which columns went in, what each contributed, and which
#   OKF concepts justified them" survives for as long as the result does.
#
#   `columns_missing` is selected rather than derived from `columns` minus `columns_used`,
#   because the two are not the same claim. The subtraction says "asked for and not in the
#   final model", which a run that stopped before the ML stage satisfies for every column
#   it asked for — the three `curator-smoke` results have 91, 78 and 14 columns, no used
#   columns at all, and exactly one genuinely missing column each. `columns_missing` is
#   what the data stage reported as absent from the cohort, which is the thing worth
#   showing, and it is why `columns` itself is not selected: nothing draws it.
#
#   `match_trace` is deliberately **not** here either, for a measured reason. It is the
#   concept-to-column matching with every rejected candidate, and it is 598 kB across the
#   81 results now stored against 89 kB for the explanation columns above — one row
#   reaches 23.6 kB on its own. The snapshot is polled every two seconds and nothing draws
#   a trace yet, so it belongs to a per-result endpoint, not to this one.
#
#   `model` is selected because `feature_importance` is **not one quantity**. The two
#   engines this project runs produce numbers on different scales — gain for the boosted
#   trees, mean AUC drop for permutation — so a bar chart of contributions with no engine
#   beside it invites a comparison that is not there to make. The column is
#   `TEXT NOT NULL DEFAULT ''` and the empty string means *not recorded*: the 81 results
#   stored before 2026-09-08 take it and cannot be backfilled, because the engine was an
#   environment variable read inside the call and was never written down
#   (`src/memstara/mcp_servers/ml.py (at commit 0990ec5, lines 194)`). Three states reach the screen, not two.
RESULTS = """
SELECT result_id, task_id, run_tag, trial, perspective, hypothesis,
       columns_used, columns_missing, feature_importance, okf_concept_ids,
       y_column, auc, model, interpretation, created_at,
       COALESCE(to_jsonb(memstara_results)->'evaluation', '{}'::jsonb) AS evaluation,
       COALESCE(to_jsonb(memstara_results)->>'hypothesis_id', '') AS hypothesis_id
FROM memstara_results
WHERE ($1 = '' OR run_tag = $1)
ORDER BY result_id
"""

# RESULT_ONE — one result, and this is the only query that selects `match_trace`.
#   It exists so the trace has somewhere to be read that is not the two-second poll. The
#   size is the whole reason for the split: 598 kB across the 81 results stored, one row
#   at 23.6 kB, against 89 kB for every explanation column in RESULTS put together. Sent
#   with the snapshot that is a six-fold increase every two seconds for something nothing
#   on screen was drawing; fetched here it is one request, made when a person opens one
#   result.
#
#   `run_tag` is selected even though RESULTS does not: this endpoint is reached by
#   result_id alone, so the row has to say which run it belongs to without a second read.
#   No run filter — a result opens from a link whichever run produced it, the same
#   reasoning as `/api/task/{task_id}` passing '' to BOARD.
RESULT_ONE = """
SELECT result_id, task_id, run_tag, trial, perspective, hypothesis,
       columns, columns_used, columns_missing, feature_importance, okf_concept_ids,
       match_trace, y_column, auc, model, interpretation, created_at,
       COALESCE(to_jsonb(memstara_results)->'evaluation', '{}'::jsonb) AS evaluation,
       COALESCE(to_jsonb(memstara_results)->>'hypothesis_id', '') AS hypothesis_id
FROM memstara_results
WHERE result_id = $1
"""

# --- core's database -------------------------------------------------------- #

# From here on it is the core DB (motoro-postgres:5453), where the agents and the
# run history live.

# AGENT_TOTALS — the running totals per agent.
#   It is a `LEFT JOIN`, so **an agent that has never run comes out as 0** — that is to
#   keep it from quietly vanishing from the list.
#   The `coalesce(..., 0)` calls are there for the same reason: even with a run whose
#   tokens or cost are NULL mixed in, the sum does not go NULL entirely.
#   `a.name LIKE 'memstara%'` keeps only this project's agents (both the board path and
#   the supervisor path).
AGENT_TOTALS = """
SELECT a.name,
       count(r.id)                                                   AS runs,
       count(r.id) FILTER (WHERE r.status = 'completed')             AS completed,
       count(r.id) FILTER (WHERE r.completed_at IS NULL
                             AND r.status NOT IN ('failed'))         AS open_runs,
       coalesce(sum((r.token_usage->>'prompt_tokens')::bigint), 0)   AS prompt_tokens,
       coalesce(sum((r.token_usage->>'completion_tokens')::bigint), 0) AS completion_tokens,
       coalesce(sum(r.cost_estimate), 0)                             AS cost,
       avg((r.pattern_overrides->'reason_act_state'->>'iterations')::float) AS avg_iterations,
       max(r.created_at)                                             AS last_run_at
FROM agents a
LEFT JOIN agent_runs r ON r.agent_id = a.id
WHERE a.name LIKE 'memstara%'
GROUP BY a.name
ORDER BY a.name
"""

# Who is mid-flight right now. This is what makes a character "working".
#
# `completed_at IS NULL` alone is not enough. Nine runs sit in `pending` and never
# finished — the oldest 26 days old — because the process that started them was killed.
# Without a freshness bound the ml character stands there "working" forever, which is
# the same trap `reclaim_stalled` fell into: no time condition makes a dead thing look
# alive.
#
# The bound is on the heartbeat, falling back to creation time. It used to be justified
# here by "runs heartbeat every few seconds (observed: 5s), and a stage takes 20-60s".
# That is not what motoro does: `_update_heartbeat` is called inside the phase loop, so
# a run heartbeats once per phase and a long phase is silent for its whole length —
# measured up to 500.3s, in runs that completed normally. A window shorter than the
# longest phase does not hide dead runs, it hides live ones. See the note on
# RUN_ALIVE_SECONDS in scene.py for the measurement and the margins.
#
# ($1 is scene.py's RUN_ALIVE_SECONDS = 900, arriving here as a string.)
OPEN_RUNS = """
SELECT r.id AS run_id, a.name, r.created_at,
       coalesce(r.last_heartbeat_at, r.created_at) AS alive_at
FROM agent_runs r
JOIN agents a ON a.id = r.agent_id
WHERE r.completed_at IS NULL
  AND r.status NOT IN ('failed')
  AND a.name LIKE 'memstara%'
  AND coalesce(r.last_heartbeat_at, r.created_at)
      > now() - ($1::text || ' seconds')::interval
ORDER BY r.created_at
"""

# Per agent, per window: how many calls. The access map.
#
# Note that it starts with `FLAT_CALLS +`. What is counted here is the access map on
# screen exactly, so if the three traps are not handled here every number on screen is
# wrong. `LIKE 'memstara%'` catches **both** the board path and the supervisor path —
# leave the supervisor side out and the real call volume is under-reported about
# fivefold (see stores.py).
ACCESS = FLAT_CALLS + """
SELECT a.name, f.server, f.tool, count(*) AS calls,
       max(f.started_at) AS last_at
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE a.name LIKE 'memstara%'
GROUP BY a.name, f.server, f.tool
-- `f.server, f.tool` is the tie-break, and it is not decoration. `a.name, count(*) DESC`
-- alone leaves rows with equal counts in whatever order the plan happened to produce, so
-- the access map re-shuffled its own rows between two polls that had found no new calls.
-- Caught by diffing this query's output against the previous definition of `flat`: same
-- 43 rows as a multiset, different order, and the only rows that moved were three tied
-- at 18 calls each.
ORDER BY a.name, count(*) DESC, f.server, f.tool
"""

# The board-to-run bridge. The board carries no run id, but claim_task's *result* does
# carry the task id, and submit_result's *arguments* do. Parsing these is the only way
# to say which agent run handled which task.
#
# `coalesce(the result side, the arguments side)` merges those two places into one
# column. `ORDER BY f.started_at` puts it in time order, so scene._carrying can replay
# this list as it stands and reconstruct "who is holding what right now" — it does not
# have to sort again.
#
# The window is not an optimisation, it is a correctness bound, and it is the same
# argument as OPEN_RUNS above. `_carrying` replays claims against releases and reports
# whoever is left holding something. An interrupted run leaves a `claim_task` with no
# matching `submit_result`, and over an unbounded history that orphan never expires:
# the agent is pinned as `moving` on every screen, under every run tag, permanently.
# There is no such orphan right now, so this is a trap rather than a live fault — but
# it is armed by any run that is killed part way, which is an ordinary thing to do.
# Without the bound the replay also grows without limit; it is at 578 rows reaching
# back to 2026-08-10, re-read on every 2s poll.
#
# ($1 is scene.py's RUN_ALIVE_SECONDS, as a string, exactly as OPEN_RUNS takes it. A
# claim older than the longest a run may live cannot belong to a run still holding it.)
TASK_TOUCHES = FLAT_CALLS + f"""
SELECT a.name,
       f.run_id,
       f.tool,
       NOT ((f.result::jsonb) ? 'error') AS succeeded,
       f.started_at,
       coalesce(
           (f.result::json)->>'task_id',
           f.arguments->>'task_id'
       ) AS task_id,
       (f.result::json)->>'run_tag' AS run_tag,
       -- Which of a stage's workers made this call. Only the arguments side has it:
       -- the worker names itself when it asks for work, and no board row this query
       -- reads is keyed by it.
       --
       -- NULL on every call the tool lets omit it, which is most of them: `create_task`
       -- has no such argument at all, and `submit_result` defaults it to '' and treats
       -- that as "no opinion" (`src/memstara/mcp_servers/blackboard.py:293`). So this is
       -- read as "a name where there is one", never as "the name of this run" — one
       -- named call anywhere in a run is enough, and no named call is not a failure.
       f.arguments->>'worker' AS worker
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE f.tool IN {_TOOLS_SQL}
  AND f.started_at > now() - ($1::text || ' seconds')::interval
ORDER BY f.started_at
"""
# Historical task details must retain completed calls outside the live-agent window.
TASK_HISTORY = TASK_TOUCHES.replace(
    "  AND f.started_at > now() - ($1::text || ' seconds')::interval", ""
)


# The most recent tool call per agent **run**, for "where is this character standing".
#
# `DISTINCT ON (a.name, f.run_id)` is PostgreSQL-only syntax: paired with the leading
# part of the ORDER BY, it keeps only "the first row per name and run". That is what
# makes `ORDER BY a.name, f.run_id, f.started_at DESC` mean "the most recent one per
# run". Change the order and the wrong row is kept, silently.
#
# It was `DISTINCT ON (a.name)` until 2026-09-08, and that is what made the viewer draw
# one character however many workers were running. `--hypothesis-agents 3` starts three
# `call_agent`s against **one** agent (`src/memstara/pipeline/board.py:1412`), so the
# three are three `agent_runs` rows sharing a name: keyed by name, two of the three were
# dropped here before scene.py ever saw them. `run_id` is the axis that separates them,
# and it is the axis `OPEN_RUNS` was already keyed by, which is why that query needed no
# change at all.
#
# This returns one row per run rather than per live worker, so it holds finished runs
# too. That is not waste — scene.py looks each run up by id, and a character whose run
# has ended still has to say what it last did.
LAST_CALL = FLAT_CALLS + """
SELECT DISTINCT ON (a.name, f.run_id)
       a.name, f.server, f.tool, f.started_at, f.run_id, r.status AS run_status
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE a.name LIKE 'memstara%'
ORDER BY a.name, f.run_id, f.started_at DESC
"""

# The workers of the most recent run, **however long ago that run was.**
#
# TASK_TOUCHES answers "who is working right now", and its window is anchored on `now()`
# for that reason. This answers the different question of *how many workers the last run
# had*, and anchoring that on `now()` is what made the viewer wrong: a quarter of an hour
# after a three-worker run finished, the hypothesis column folded back to one card and the
# screen said the pipeline had one hypothesis agent. The number of hypothesis agents is a
# property of the **run**, chosen on the form before it started; it does not become one
# because nobody has looked at the screen for fifteen minutes.
#
# So the window is kept — it is still what groups a cohort of workers and separates it from
# the run before — and only its **anchor** moves, from `now()` to the newest named call
# there is (`anchor`). Idle for a day, this returns exactly the workers of the last run.
# Mid-run, `anchor` is a few seconds old and this returns exactly what TASK_TOUCHES does,
# which is why turning it on changes nothing about a live screen.
#
# `worker` is the only column this is for. A call carries it when the worker names itself
# asking for work, which is the one place a stage's workers are told apart
# (`_worker_names`, `scene.py:446`), and a call without one says nothing about how many
# workers there were — hence the `<> ''` rather than a coalesce to a placeholder.
#
# `DISTINCT ON (run_id)`: one row per worker run, keyed by the same axis OPEN_RUNS and
# LAST_CALL use. `name` comes along so scene.py can place the run at a stage without
# having to find it in another result set — a run this old may be in none of them.
#
# ($1 is scene.py's RUN_ALIVE_SECONDS, the same value TASK_TOUCHES takes, because it is
# the same question about the same cohort asked from a different anchor.)
LAST_ROSTER = FLAT_CALLS + f"""
WITH named AS (
    SELECT a.name, f.run_id, f.started_at,
           coalesce(nullif(f.arguments->>'worker', ''), f.arguments->>'writer') AS worker,
           coalesce(nullif(f.arguments->>'run_tag', ''),
                    nullif(f.arguments->>'origin_run', ''),
                    nullif((f.result::json)->>'run_tag', '')) AS pipeline_tag
    FROM flat f
    JOIN agent_runs r ON r.id = f.run_id
    JOIN agents a ON a.id = r.agent_id
    WHERE f.tool IN {_TOOLS_SQL}
      AND coalesce(nullif(f.arguments->>'worker', ''), f.arguments->>'writer', '') <> ''
),
anchor AS (SELECT pipeline_tag, started_at AS newest FROM named ORDER BY started_at DESC LIMIT 1)
SELECT DISTINCT ON (n.run_id)
       n.name, n.run_id, n.worker, n.started_at
FROM named n, anchor
WHERE (anchor.pipeline_tag IS NOT NULL AND n.pipeline_tag = anchor.pipeline_tag)
   OR (anchor.pipeline_tag IS NULL
       AND n.started_at > anchor.newest - ($1::text || ' seconds')::interval)
ORDER BY n.run_id, n.started_at

"""

# Recent calls, for the flashing lines. Window is applied in Python so the value lives
# next to the animation that depends on it.
#
# Why the window ($1) is passed from Python rather than baked into the SQL as a
# constant: the value has to equal the animation length (scene.FLASH_SECONDS = 4), so it
# is **kept right next to the code that depends on it.**
# `LIMIT 40` is a safeguard: even in a burst, only as much is drawn as the screen can
# take.
#
# `f.run_id` is here so a flash can be attributed to the **worker** that made the call
# and not merely to its stage. With N workers of one stage on the floor, a flash keyed by
# stage names no character on screen and the line is simply not drawn (`ScenePanel.tsx`
# builds each edge as `source: agent-${f.agent}`).
RECENT_CALLS = FLAT_CALLS + """
SELECT a.name, f.server, f.tool, f.started_at, f.run_id
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE f.started_at > now() - ($1::text || ' seconds')::interval
ORDER BY f.started_at DESC
LIMIT 40
"""

# The feed panel's rows: the newest calls, **with no time window at all.**
#
# Why this is not RECENT_CALLS with a bigger number. RECENT_CALLS exists to drive the
# flashing edges, so its window has to equal the animation length (4 seconds). The
# screen polls every 2 seconds, so a feed built on it would show a handful of rows and
# would lose anything that happened during a tick that ran slow. A feed has to be "the
# last N calls, whenever they were" — then a quiet system shows its last activity
# instead of showing nothing.
#
# No run_tag filter, on purpose. Only create_task/claim_task/submit_result carry a
# run_tag (see TASK_TOUCHES above); a curator's okf_read has none, so filtering by the
# selected run would silently drop most of the feed. The panel says "All runs" on
# screen rather than pretending otherwise.
#
# `seq` is there so the screen has a stable key. One step can hold a batch containing
# the same tool twice, so step_id alone collides and step_id + tool collides too.
FEED = FLAT_CALLS + """
SELECT a.name,
       f.server,
       f.tool,
       f.started_at,
       f.step_id,
       row_number() OVER (PARTITION BY f.step_id ORDER BY f.tool) AS seq
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
ORDER BY f.started_at DESC, f.step_id DESC
LIMIT 60
"""
