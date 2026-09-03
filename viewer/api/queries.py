"""The SQL. Kept in one file so the three record shapes are handled in exactly one place.

`run_steps.tool_call` comes in three shapes, and getting this wrong produces numbers
that look plausible and are not:

1. The column is `json`, and many rows hold the JSON literal `null` rather than SQL
   NULL. `tool_call IS NOT NULL` is therefore true for 424 rows that contain no call at
   all. Filter on `::text <> 'null'`.
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
#: `task_id` and `run_tag` out of them (see its comment below). Every other tool's
#: payload is carried into `flat`, written to disk, and never looked at; and it is the
#: expensive half of the table, because a tool that calls a model puts the model's whole
#: answer in `result`, up to 46kB of it. So the two columns are kept for these three and
#: nulled for the rest. If a new query needs a payload, widen this list — do not reach
#: past `flat` for it.
BOARD_TOOLS = ("create_task", "claim_task", "submit_result")
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
RESULTS = """
SELECT result_id, task_id, run_tag, trial, perspective, hypothesis,
       columns_used, y_column, auc, interpretation, created_at
FROM memstara_results
WHERE ($1 = '' OR run_tag = $1)
ORDER BY result_id
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
# `completed_at IS NULL` alone is not enough. Six runs sit in `pending` and never
# finished — the oldest is seven days old — because the process that started them was
# killed. Without a freshness bound the ml character stands there "working" forever,
# which is the same trap `reclaim_stalled` fell into: no time condition makes a dead
# thing look alive.
#
# The bound is on the heartbeat, falling back to creation time. Runs heartbeat every
# few seconds (observed: 5s), and a stage takes 20-60s, so $1 seconds of silence means
# the run is gone rather than slow.
#
# ($1 is scene.py's RUN_ALIVE_SECONDS = 120, arriving here as a string.)
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
ORDER BY a.name, count(*) DESC
"""

# The board-to-run bridge. The board carries no run id, but claim_task's *result* does
# carry the task id, and submit_result's *arguments* do. Parsing these is the only way
# to say which agent run handled which task.
#
# `coalesce(the result side, the arguments side)` merges those two places into one
# column. `ORDER BY f.started_at` puts it in time order, so scene._carrying can replay
# this list as it stands and reconstruct "who is holding what right now" — it does not
# have to sort again.
TASK_TOUCHES = FLAT_CALLS + f"""
SELECT a.name,
       f.run_id,
       f.tool,
       f.started_at,
       coalesce(
           (f.result::json)->>'task_id',
           f.arguments->>'task_id'
       ) AS task_id,
       (f.result::json)->>'run_tag' AS run_tag
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE f.tool IN {_TOOLS_SQL}
ORDER BY f.started_at
"""

# The most recent tool call per agent, for "where is this character standing".
#
# `DISTINCT ON (a.name)` is PostgreSQL-only syntax: paired with the leading part of the
# ORDER BY, it keeps only "the first row per name". That is what makes
# `ORDER BY a.name, f.started_at DESC` mean "the most recent one per name". Change the
# order and the wrong row is kept, silently.
LAST_CALL = FLAT_CALLS + """
SELECT DISTINCT ON (a.name)
       a.name, f.server, f.tool, f.started_at, f.run_id
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE a.name LIKE 'memstara%'
ORDER BY a.name, f.started_at DESC
"""

# Recent calls, for the flashing lines. Window is applied in Python so the value lives
# next to the animation that depends on it.
#
# Why the window ($1) is passed from Python rather than baked into the SQL as a
# constant: the value has to equal the animation length (scene.FLASH_SECONDS = 4), so it
# is **kept right next to the code that depends on it.**
# `LIMIT 40` is a safeguard: even in a burst, only as much is drawn as the screen can
# take.
RECENT_CALLS = FLAT_CALLS + """
SELECT a.name, f.server, f.tool, f.started_at
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
