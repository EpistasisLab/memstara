"""The SQL. Kept in one file so the three record shapes are handled in exactly one place."""

# Materialize the requested run IDs before ANY JSON inspection. Without this
# boundary PostgreSQL can evaluate a JSON predicate on unrelated run_steps before
# joining selected_run_ids. On the affected execution this took over 11 seconds;
# an explicit scoped source reduced the same 434 tool calls to 0.13–0.34 seconds.
# json_to_record keeps large tool results as JSON and reads the outer shape once.
# Only board arguments/results used for task attribution are converted to JSONB,
# with the existing escaped-NUL protection. Both single and batched calls remain.
# These payloads are used to associate actual calls with tasks and named workers.
BOARD_TOOLS = ("create_task", "claim_task", "claim_question", "submit_result", "propose_questions")
_TOOLS_SQL = "('" + "', '".join(BOARD_TOOLS) + "')"


def _payload(prefix: str, expr: str) -> str:
    """`expr` on `prefix`, but only for a board tool; NULL otherwise."""
    return f"CASE WHEN {prefix}->>'tool' IN {_TOOLS_SQL} THEN {prefix}{expr} END"


def telemetry_jsonb(expression: str) -> str:
    r"""Render JSON safely without changing stored core history.

    PostgreSQL JSON accepts escaped NUL, but JSONB/text rejects it. Replace only
    an actual JSON NUL escape with U+FFFD; preserve literal backslash-u0000 text.
    The paired-backslash capture keeps JSON escape parity intact.
    """
    cleaned = (
        "regexp_replace(" + expression + "::text, "
        + r"$nul$(?<!\\)((?:\\\\)*)\\u0000$nul$, $nul$\1\\ufffd$nul$, 'g')"
    )
    # Most payloads need no regex scan. In particular, ML outputs can be large.
    return (f"(CASE WHEN strpos({expression}::text, " + r"$nul$\u0000$nul$"
            + f") > 0 THEN {cleaned} ELSE {expression}::text END)::jsonb")



# Keep large tool results as JSON. Convert only board payloads needed for task
# attribution; converting every ML/result document to JSONB dominated cold reads.
_FLAT_SELECT = f"""
WITH scoped_steps AS MATERIALIZED (
    SELECT s.run_id, s.id, s.started_at FROM run_steps s
)
SELECT s.run_id, s.id AS step_id, s.started_at,
       replace(c.server, 'ecoxai-', 'memstara-') AS server, c.tool,
       CASE WHEN c.tool IN {_TOOLS_SQL} THEN
            {telemetry_jsonb("json_build_object('task_id', attrs.task_id, 'worker', attrs.worker, 'writer', attrs.writer, 'run_tag', attrs.run_tag, 'origin_run', attrs.origin_run)")}
       END AS arguments,
       CASE WHEN c.tool IN {_TOOLS_SQL}
            THEN ({telemetry_jsonb("c.result")}) #>> '{{}}' END AS result
FROM scoped_steps s
JOIN run_steps raw ON raw.id=s.id
CROSS JOIN LATERAL json_to_record(
    CASE WHEN json_typeof(raw.tool_call) = 'object' THEN raw.tool_call ELSE '{{}}'::json END
) AS doc(server text, tool text, arguments json, result json, calls json)
CROSS JOIN LATERAL (
    SELECT doc.server, doc.tool, doc.arguments, doc.result WHERE doc.server IS NOT NULL
    UNION ALL
    SELECT batch.server, batch.tool, batch.arguments, batch.result
    FROM json_to_recordset(
        CASE WHEN json_typeof(doc.calls) = 'array' THEN doc.calls ELSE '[]'::json END
    ) AS batch(server text, tool text, arguments json, result json)
) c
CROSS JOIN LATERAL json_to_record(
    CASE WHEN c.tool IN {_TOOLS_SQL} AND json_typeof(c.arguments) = 'object'
         THEN c.arguments ELSE '{{}}'::json END
) AS attrs(task_id json, worker json, writer json, run_tag json, origin_run json)
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

# These columns are installed by the board schema migration. Reading them directly
# avoids serializing large match_trace values on every results poll.
RESULTS = """
SELECT result_id, task_id, run_tag, trial, perspective, hypothesis,
       columns_used, columns_missing, feature_importance, okf_concept_ids,
       y_column, auc, model, interpretation, created_at,
       COALESCE(evaluation, '{}'::jsonb) AS evaluation,
       COALESCE(hypothesis_id, '') AS hypothesis_id
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
       COALESCE(evaluation, '{}'::jsonb) AS evaluation,
       COALESCE(hypothesis_id, '') AS hypothesis_id
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

TASK_TOUCHES = FLAT_CALLS + f"""
SELECT a.name,
       f.run_id,
       f.tool,
       NOT (({telemetry_jsonb("f.result")}) ? 'error') AS succeeded,
       f.started_at,
       coalesce(
           ({telemetry_jsonb("f.result")})->>'task_id',
           f.arguments->>'task_id'
       ) AS task_id,
       ({telemetry_jsonb("f.result")})->>'run_tag' AS run_tag,
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
                    nullif(({telemetry_jsonb("f.result")})->>'run_tag', '')) AS pipeline_tag
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
