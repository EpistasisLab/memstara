#!/usr/bin/env python3
"""MCP server — the only way an agent touches the shared work board.

The 2026-08-12 alignment was explicit about this one:

    "we don't want the agents to start querying a table on another database —
     that would break that pattern and it just wouldn't become a foundation anymore."

So the board is a table, and this is the window. Agents never see the database.

Six tools, not the four the design document first listed.

**Creating a row and updating one are different acts** — the hypothesis stage makes new
work, everyone else picks up work that exists — so those are separate. And the board
and the results table are separate stores, so reading them is two tools, not one; the
report is written from finished results.

    create_task     hypothesis makes a new row
    claim_task      data / ml / interpret take one that is waiting
    submit_result   whoever holds a task writes what they produced
    count_waiting   how many are queued (the driving script, not an agent)
    read_board      the whole board, unfinished work included
    read_results    what has actually been produced (the reporting stage)

Core launches this file as a stdio subprocess, same shape as tools_data.py.

The board lives in **Memstara's own database**, not core's — see ``docker-compose.yml``.

Environment::

    MEMSTARA_DATABASE_URL    must be on `mcp_allowed_env_vars` in settings.py —
                           core does not hand credentials to a subprocess by default.
                           Unset falls back to the compose container on :5463.


==============================================================================
 How to read this file
==============================================================================

 The **only window** onto the board. Agents never look at the database directly.

 There are two tables. That distinction is the heart of this file.

   memstara_blackboard   the workbench. Work still in motion sits here.
                         Clear it and it is gone
   memstara_results      the record. Only finished work. Survives clearing the board

 The path one task travels:

   create_task      the hypothesis stage makes a new row   status=ready · type=data
        |
   claim_task       the data stage picks it up             status=in_progress
        |
   submit_result    writes its result and passes it on     status=ready · type=ml
        |           (the same thing repeats for ml -> interpret)
        |
   submit_result    when the last stage finishes           status=done
                    **that is when one row is copied to the results table**

 Three tools for reading:
   count_waiting    how many are queued (for the pipeline, not for an agent)
   read_board       the whole board — unfinished work included
   read_results     finished work only — this is what the reporting stage reads

 To call it by hand: `python debug_harness.py board`
"""

from __future__ import annotations

import difflib
import json
import os
import re
from typing import Any

import asyncpg                            # PostgreSQL async driver
from mcp.server.fastmcp import FastMCP

# This is a child process, so the parent's debugger cannot reach it. It waits for a
# debugger only when MEMSTARA_DEBUGPY contains this server's name — otherwise it
# does nothing at all. See debug_hook.py.
from memstara.mcp_servers.debug_hook import quiet_child, wait_for_debugger

quiet_child()          # silences the three startup messages a child prints
wait_for_debugger('memstara-blackboard')

mcp = FastMCP("memstara-blackboard")

# Who comes next once a stage finishes. A stage missing from this table (interpret)
# is the last one. submit_result reads this to decide whether status becomes
# 'ready' (there is a next stage) or 'done'.
NEXT_STAGE = {"hypothesis": "data", "data": "ml", "ml": "interpret"}


# The address used when the environment variable is unset. It points at the container
# docker-compose.yml starts. Port 5463 — a **different database** from core's 5453.
DEFAULT_DSN = "postgresql://memstara:memstara@localhost:5463/memstara"


def _dsn() -> str:
    """Read the address the same way blackboard.py does — Memstara's database, not core's.

    Read lazily rather than at import time: `os.environ[...]` up top kills the server
    during startup, and core reports that only as "tools available: []".
    """
    url = os.environ.get("MEMSTARA_DATABASE_URL", "").strip() or DEFAULT_DSN
    # SQLAlchemy attaches the driver to the scheme, as in "postgresql+asyncpg://",
    # but asyncpg does not understand that form. Strip it off if it is there.
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _err(e: Exception) -> str:
    """Turn an exception into JSON the agent can read, including the type's name.

    A tool never lets an exception out. Raised, it reads to the agent only as "the
    tool is broken", leaving nothing to reason about what should be fixed.
    """
    return json.dumps({"error": f"{type(e).__name__}: {e}"})


@mcp.tool()
async def create_task(run_tag: str, trial: int, perspective: str, hypothesis: str,
                      columns: list[str], y_column: str,
                      okf_concept_ids: list[str] | None = None,
                      question_id: int = 0) -> str:
    """Put a new task on the board. The hypothesis stage uses this.

    Args:
        run_tag: which pipeline run this belongs to.
        trial: trial number within that run.
        perspective: the angle this trial was asked to take.
        hypothesis: one sentence on why these columns should predict the outcome.
        columns: a JSON list of column names, spelled exactly as the matcher spelled
            them. Not a comma-joined string: 158 of this cohort's 1,393 column names
            contain a comma inside the name (`LAB__HDL CHOLESTEROL, DIRECT`), so a
            joined string cannot be split back apart.
        y_column: the outcome column these are meant to predict, spelled as the dataset
            spells it. Recorded on the task so every later stage reads it from the board
            rather than being told separately.
        okf_concept_ids: a JSON list of the knowledge-source concept ids relied on.
        question_id: which question bank row this trial came from, if the driver gave
            you one. 0 means none — the run used the built-in perspective list instead.
            Recorded so a finished result can be traced back to what was asked, not
            just what was answered.

    Returns:
        JSON with the new task_id. The row starts as ready for the data stage.
    """
    # A bare string is refused rather than iterated. Python would iterate it
    # character by character and store a JSON array of single letters — a task the
    # data stage then reports as 30-odd missing columns, which reads like a naming
    # problem and is not one.
    if isinstance(columns, str) or isinstance(okf_concept_ids, str):
        return json.dumps(
            {
                "error": "columns and okf_concept_ids must be lists, not strings",
                "hint": 'Pass ["BMI", "LAB__HDL CHOLESTEROL, DIRECT"], not '
                '"BMI, LAB__HDL CHOLESTEROL, DIRECT". Column names contain commas, '
                "so a comma-separated string cannot be split back apart.",
            }
        )

    # Surrounding whitespace is stripped and empty entries dropped; the name itself,
    # commas included, is left exactly as given.
    cols = [str(c).strip() for c in columns if str(c).strip()]
    ids = [str(c).strip() for c in (okf_concept_ids or []) if str(c).strip()]
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            # A new row always starts as status='ready', task_type='data' — ready
            # for the data stage to pick up the moment it is created.
            # Writing y_column here matters: every later stage reads that value off
            # the board rather than being told it separately in a prompt.
            task_id = await conn.fetchval(
                """
                INSERT INTO memstara_blackboard
                    (run_tag, trial, perspective, status, task_type,
                     hypothesis, columns, y_column, okf_concept_ids, question_id)
                VALUES ($1, $2, $3, 'ready', 'data', $4, $5::jsonb, $6, $7::jsonb, $8)
                RETURNING task_id
                """,
                run_tag, trial, perspective, hypothesis, json.dumps(cols), y_column,
                json.dumps(ids), (int(question_id) or None),
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001 - the agent must see why
        return _err(e)
    return json.dumps({"task_id": task_id, "status": "ready", "task_type": "data"})


@mcp.tool()
async def claim_task(task_type: str, run_tag: str = "") -> str:
    """Take one waiting task of your type, so nobody else can take it.

    Args:
        task_type: one of "data", "ml", "interpret" — the stage you are.
        run_tag: the run you are working. Pass the one you were told to work and you
            will only ever be handed tasks from it. Leaving it empty takes the oldest
            waiting task of your type from *any* run — which is how a task abandoned
            by some earlier, unrelated run ends up being done, and paid for, by this
            one. Do not leave it empty when you were given a run tag.

    Returns:
        JSON with the task and everything earlier stages left on it, including
        ``y_column`` — the outcome to predict, carried on the task so no stage has to be
        told it separately. When the board has nothing waiting for you it returns
        ``{"task_id": null}`` — that means
        there is no work for you right now, so stop. Do not invent a task and do not
        take one of another type.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            # The whole point of this server, in one statement. FOR UPDATE locks the
            # row we picked; SKIP LOCKED makes a second claimer step over it instead
            # of waiting, so two agents of the same type never end up on one task.
            # Without SKIP LOCKED the second claimer waits for the first and then
            # takes **the very same row** once the first is done.
            #
            # None of this is visible from a breakpoint — while execution is stopped
            # there is no contention. Seeing it takes two psql windows.
            #
            # The run_tag condition is what keeps one run out of another's work. Without
            # it this picks the oldest ready row of the type from the whole board, and
            # ORDER BY task_id means *oldest* — so a task abandoned by a run that died
            # weeks ago is the first thing the next run reaches for. It then does that
            # work, on that run's money, and files the result under the dead run's tag.
            # run_lock() does not cover this: it only stops two drivers on the *same* tag.
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    UPDATE memstara_blackboard SET
                        status     = 'in_progress',
                        attempts   = attempts + 1,
                        claimed_at = now(),
                        updated_at = now()
                    WHERE task_id = (
                        SELECT task_id FROM memstara_blackboard
                        WHERE task_type = $1 AND status = 'ready'
                          -- An empty string reads the whole board, as before
                          -- (backward compatible).
                          AND ($2 = '' OR run_tag = $2)
                        ORDER BY task_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING task_id, run_tag, trial, perspective, hypothesis,
                              columns, y_column, okf_concept_ids, subset_path,
                              columns_used, auc, feature_importance
                    """,
                    task_type, run_tag,
                )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    # None comes back when there is nothing to claim. Not turning this into an error
    # matters — "there is no work for me right now" is a normal state, and the agent
    # is supposed to stop here.
    if row is None:
        return json.dumps({"task_id": None})

    out: dict[str, Any] = dict(row)
    # These are stored as JSON strings in the database. They are unpacked into Python
    # values before being returned — left packed, the agent would have to parse JSON
    # out of a string a second time.
    # The empty default differs by field: [] for the lists, {} for the importances.
    for k in ("columns", "okf_concept_ids", "columns_used", "feature_importance"):
        out[k] = json.loads(out[k]) if out[k] else ([] if k != "feature_importance" else {})
    # default=str — JSON does not know values such as datetime, so they become strings.
    return json.dumps(out, ensure_ascii=False, default=str)


@mcp.tool()
async def submit_result(task_id: int, subset_path: str = "",
                        columns_used: list[str] | None = None,
                        columns_missing: list[str] | None = None, auc: float | None = None,
                        feature_importance: str = "", interpretation: str = "") -> str:
    """Write what you produced and hand the task to the next stage.

    Pass only the fields your stage produces; leave the rest out.

    Args:
        task_id: the id claim_task gave you.
        subset_path: data stage — path of the sub-dataset produced.
        columns_used: data stage — a JSON list of the columns actually extracted. Copy
            them from what slice_columns returned; many contain a comma inside the
            name, so a comma-joined string cannot be split back apart.
        columns_missing: data stage — a JSON list of the columns that were absent. An
            empty list records "none were missing"; omitting it leaves the field alone.
        auc: ml stage — the test AUC.
        feature_importance: ml stage — JSON object of column to importance.
        interpretation: interpretation stage — the write-up.

    Returns:
        JSON with the task's new status and whose turn it is now. After the
        interpretation stage the task is done and a row is added to the results table.
    """
    if isinstance(columns_used, str) or isinstance(columns_missing, str):
        return json.dumps(
            {
                "error": "columns_used and columns_missing must be lists, not strings",
                "hint": "Pass slice_columns' own columns_used / columns_missing arrays "
                "through unchanged. Many column names contain a comma.",
            }
        )
    # `''` is the sentinel the UPDATE below reads as "this stage did not produce
    # this field" (the `$3 <> ''` cases). `None` means omitted; an empty list is a
    # real answer — it records that nothing was missing.
    used_json = json.dumps([str(c).strip() for c in columns_used if str(c).strip()]) \
        if columns_used is not None else ""
    missing_json = json.dumps([str(c).strip() for c in columns_missing if str(c).strip()]) \
        if columns_missing is not None else ""

    try:
        conn = await asyncpg.connect(_dsn())
        try:
            async with conn.transaction():
                cur = await conn.fetchrow(
                    "SELECT task_type, status FROM memstara_blackboard WHERE task_id = $1 FOR UPDATE",
                    task_id,
                )
                if cur is None:
                    return json.dumps({"error": f"no task {task_id}"})
                # Blocks writing a result to a task that was never claimed. Without
                # this check, one agent could overwrite its own result onto work
                # somebody else is holding.
                if cur["status"] != "in_progress":
                    return json.dumps(
                        {"error": f"task {task_id} is '{cur['status']}', not in_progress — claim it first"}
                    )

                stage = cur["task_type"]          # the stage this task is at now
                nxt = NEXT_STAGE.get(stage)       # the next stage (None = this was the last)
                new_status = "ready" if nxt else "done"   # waiting again if there is a next
                new_type = nxt or stage                   # on the last stage the type stays

                # Each stage fills in different fields, so **only what was given is
                # overwritten and the rest is left alone.** The COALESCE / NULLIF /
                # CASE below is what does that.
                #   NULLIF($2, '')  an empty string becomes NULL
                #   COALESCE(a, b)  b when a is NULL (= keep the original value)
                # Without it, the ml stage submitting its result would wipe the path
                # the data stage wrote, replacing it with an empty string.
                await conn.execute(
                    """
                    UPDATE memstara_blackboard SET
                        subset_path        = COALESCE(NULLIF($2, ''), subset_path),
                        columns_used       = CASE WHEN $3 <> '' THEN $3::jsonb ELSE columns_used END,
                        columns_missing    = CASE WHEN $4 <> '' THEN $4::jsonb ELSE columns_missing END,
                        auc                = COALESCE($5, auc),
                        feature_importance = CASE WHEN $6 <> '' THEN $6::jsonb ELSE feature_importance END,
                        interpretation     = COALESCE(NULLIF($7, ''), interpretation),
                        status             = $8,
                        task_type          = $9,
                        claimed_at         = NULL,
                        updated_at         = now()
                    WHERE task_id = $1
                    """,
                    task_id,
                    subset_path,
                    used_json,
                    missing_json,
                    auc,
                    feature_importance,
                    interpretation,
                    new_status,
                    new_type,
                )

                # The results table is separate on purpose: the board holds what is
                # still moving, this holds what was found. The copy happens **only at
                # this moment, when the last stage finishes** — which is why the
                # results table contains nothing but work that made it all the way
                # through. (Deleting the board row leaves this one standing: the
                # foreign key is ON DELETE SET NULL, so only task_id empties and the
                # content stays.)
                #
                #   The evidence columns travel with the conclusion on purpose. This
                #   copy used to carry nine columns — the hypothesis, the columns used,
                #   the outcome, the AUC and the write-up — which is what a report
                #   needs but not what a reader checking the work needs. Everything
                #   explaining *why* those columns (okf_concept_ids, match_trace) and
                #   *whether they earned their place* (feature_importance) stayed
                #   behind on a table designed to be cleared, so the record that
                #   outlived the run was exactly the part that could not be verified.
                if new_status == "done":
                    await conn.execute(
                        """
                        INSERT INTO memstara_results
                            (task_id, run_tag, trial, perspective, hypothesis,
                             columns, columns_used, columns_missing,
                             okf_concept_ids, match_trace, question_id,
                             y_column, auc, feature_importance, interpretation)
                        SELECT task_id, run_tag, trial, perspective, hypothesis,
                               columns, columns_used, columns_missing,
                               okf_concept_ids, match_trace, question_id,
                               y_column, auc, feature_importance, interpretation
                        FROM memstara_blackboard WHERE task_id = $1
                        """,
                        task_id,
                    )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)
    return json.dumps({"ok": True, "task_id": task_id, "status": new_status, "task_type": new_type})


@mcp.tool()
async def count_waiting(task_type: str = "", run_tag: str = "") -> str:
    """How many tasks are waiting, and how many are being worked on.

    Args:
        task_type: restrict to one stage; "" counts every stage.
        run_tag: restrict to one run; "" counts the whole board — including tasks left
            behind by runs that ended, which is almost never the number you want.

    Returns:
        JSON with counts per stage.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                """
                SELECT task_type, status, count(*) AS n FROM memstara_blackboard
                WHERE ($1 = '' OR task_type = $1)
                  AND ($2 = '' OR run_tag = $2)
                GROUP BY task_type, status
                """,
                task_type, run_tag,
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    out: dict[str, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["task_type"], {})[r["status"]] = r["n"]
    return json.dumps(
        {
            "by_type": out,
            "ready": sum(v.get("ready", 0) for v in out.values()),
            "in_progress": sum(v.get("in_progress", 0) for v in out.values()),
        }
    )


@mcp.tool()
async def attach_match_trace(task_id: int, match_trace: str) -> str:
    """Record what the matcher was asked and what it offered back, for one task.

    The driver program calls this, not an agent. The matcher runs as a tool inside the
    hypothesis agent's turn, so every call it made is already in that run's trace with
    its arguments and its full result; the driver lifts them from there and files them
    against the task the agent created in the same turn.

    The two alternatives were both worse. Passing this through ``create_task`` would
    ask the agent to hand-copy hundreds of candidate rows into a tool argument with
    nothing to check the copy against — another place for it to invent things. Letting
    the matcher write here itself would give it board access, and the matcher is
    deliberately ignorant of the board so it can be reused by a pipeline that has none.

    Args:
        task_id: which task the trace belongs to.
        match_trace: JSON array of calls, each ``{"tool", "arguments", "result"}``.
            An empty array is accepted and means the agent matched nothing.

    Returns:
        ``{"ok": true, "task_id": N, "calls": M}``, or ``{"error": ...}`` if the JSON
        does not parse or no such task exists.
    """
    try:
        parsed = json.loads(match_trace or "[]")
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"match_trace is not valid JSON: {e}"})
    if not isinstance(parsed, list):
        return json.dumps({"error": "match_trace must be a JSON array"})

    try:
        conn = await asyncpg.connect(_dsn())
        try:
            # Written straight over rather than appended to: the driver harvests the
            # whole run at once, so a second call for the same task is a re-harvest of
            # the same calls, not new ones. Appending would double them.
            updated = await conn.fetchval(
                """
                UPDATE memstara_blackboard
                SET match_trace = $2::jsonb, updated_at = now()
                WHERE task_id = $1
                RETURNING task_id
                """,
                task_id,
                json.dumps(parsed, ensure_ascii=False),
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    if updated is None:
        return json.dumps({"error": f"no task {task_id}"})
    return json.dumps({"ok": True, "task_id": task_id, "calls": len(parsed)})


@mcp.tool()
async def read_board(run_tag: str = "") -> str:
    """Every task of a run, finished or not. The reporting stage uses this.

    Args:
        run_tag: which run; "" reads the whole board.

    Returns:
        JSON list of tasks with what each stage left on them, including the ones that
        did not finish and why.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                """
                SELECT task_id, run_tag, trial, perspective, status, task_type,
                       hypothesis, columns, okf_concept_ids, match_trace, question_id,
                       y_column, columns_used, columns_missing,
                       auc, feature_importance, interpretation, attempts, error
                FROM memstara_blackboard
                WHERE ($1 = '' OR run_tag = $1)
                ORDER BY trial, task_id
                """,
                run_tag,
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    tasks = []
    for r in rows:
        d = dict(r)
        # Every JSONB column selected above has to be listed here too. A column added
        # to the SELECT and forgotten here comes back as a string holding JSON, and the
        # caller has to parse it a second time to notice.
        for k in ("columns", "okf_concept_ids", "match_trace", "columns_used",
                  "columns_missing", "feature_importance"):
            d[k] = json.loads(d[k]) if d[k] else ([] if k != "feature_importance" else {})
        tasks.append(d)
    return json.dumps({"count": len(tasks), "tasks": tasks}, ensure_ascii=False, default=str)


@mcp.tool()
async def read_results(run_tag: str = "", include_match_trace: bool = False) -> str:
    """Every finished result of a run. The reporting stage reads this.

    This is the results table, not the board. The board holds work that is still
    moving; this holds what the interpretation stage produced and is done with. The
    report is written from finished results, so this is what it reads.

    Args:
        run_tag: which run; "" reads everything.
        include_match_trace: whether to return the matcher's candidate lists in full.
            Off by default because they are large — hundreds of candidates with scores
            per trial — and this tool's output goes straight into an agent's prompt.
            Off, each result carries ``match_trace_calls`` (how many calls were kept)
            so a reader knows the record exists and can ask for it. The data is stored
            either way; this only decides what gets read back.

    Returns:
        JSON list of results — the hypothesis, the columns that were used, the outcome
        they predicted (``y_column``), the AUC and the write-up, one entry per trial that
        made it all the way through. The outcome is here so a report can say what its
        numbers are numbers *of*.

        Each entry also carries the evidence behind it, which is what makes this
        readable as feedback rather than only as a report: ``okf_concept_ids`` (the
        corpus documents the hypothesis came from), ``match_trace`` (what the matcher
        offered, chosen and rejected alike) and ``feature_importance`` (which columns
        actually carried the AUC). A later trial can use the last of these to avoid
        columns that contributed nothing.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                """
                SELECT result_id, task_id, run_tag, trial, perspective, hypothesis,
                       columns, columns_used, columns_missing,
                       okf_concept_ids, match_trace, question_id,
                       y_column, auc, feature_importance, interpretation, created_at
                FROM memstara_results
                WHERE ($1 = '' OR run_tag = $1)
                ORDER BY trial, result_id
                """,
                run_tag,
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    out = []
    for r in rows:
        d = dict(r)
        for k in ("columns", "columns_used", "columns_missing",
                  "okf_concept_ids", "match_trace", "feature_importance"):
            d[k] = json.loads(d[k]) if d[k] else ([] if k != "feature_importance" else {})
        # Summarised rather than dropped: a caller that cannot see the field at all has
        # no way to learn the record is there to ask for.
        d["match_trace_calls"] = len(d["match_trace"])
        if not include_match_trace:
            del d["match_trace"]
        out.append(d)
    return json.dumps({"count": len(out), "results": out}, ensure_ascii=False, default=str)


#: How a proposed question is reduced to a duplicate-detection key. Case and repeated
#: whitespace are the two ways the same question comes back looking different; nothing
#: cleverer is attempted, because a near-miss that gets through is a wasted trial while a
#: false collision silently loses a question nobody can see was lost.
def _question_key(text: str) -> str:
    return " ".join(text.lower().split())


#: How similar two questions may be before the second is treated as a reword of the
#: first rather than a new question. The key above only catches a literal repeat: it
#: sees "Does naltrexone raise transaminases?" twice, and does not see that "Is
#: naltrexone associated with elevated liver enzymes?" buys the same trial. Until
#: 2026-08-30 nothing else did either — the curator was merely *asked* not to reword,
#: which is a request and not a check.
#:
#: 0.75 was set by hand against the questions already banked. It is deliberately not a
#: tunable knob: a threshold a person can read, argue with, and reproduce is worth more
#: here than a better one they cannot.
_NEAR_DUPLICATE_RATIO = 0.75


def _near_duplicate(
    text: str,
    tags: list[str],
    banked: list[tuple[int, str, list[str]]],
) -> tuple[int, float] | None:
    """Which banked question this one rewords, and how closely. None if it is new.

    Two guards, and both must fire. **The tag sets have to match exactly first.** A
    question grounded in different corpus branches is a different question however
    similar the sentence, and collapsing those would quietly cost the bank a branch
    nobody can see was lost. Only within one branch is the wording compared.

    ``difflib`` rather than an embedding on purpose. The matcher's embeddings are built
    for column names, not for English questions, and borrowing them here would make the
    bank depend on a cache built for something else.
    """
    key = _question_key(text)
    want = set(tags)
    for qid, other_text, other_tags in banked:
        if set(other_tags) != want:
            continue
        ratio = difflib.SequenceMatcher(None, key, _question_key(other_text)).ratio()
        if ratio >= _NEAR_DUPLICATE_RATIO:
            return qid, ratio
    return None


@mcp.tool()
async def read_questions(status: str = "open", limit: int = 200) -> str:
    """What this project has already thought to ask. Read this before proposing more.

    The question bank spans runs. That is the point of reading it: without it every run
    starts from nothing and re-proposes the questions the last run already worked
    through, which looks like progress and is not.

    Args:
        status: "open" for questions still worth using, "exhausted" for ones retired,
            or "" for both.
        limit: how many to return, newest first. The default is high enough to be the
            whole open bank in practice — a caller that sees only the newest slice
            proposes against a partial memory and re-asks what fell off the end, which
            is the failure this tool exists to prevent. ``record_question_outcomes``
            retires used-up questions, so the open list does not grow without bound.

    Returns:
        JSON list. Each entry carries the question ``text``, the ``okf_tags`` it was
        grounded in, the ``rationale`` for asking it, and how it has done so far —
        ``times_used`` and ``best_auc``. The last two are empty until a question has
        been through a wave.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                """
                SELECT question_id, text, okf_tags, rationale, origin_run, origin_wave,
                       times_used, best_auc, status, created_at
                FROM memstara_questions
                WHERE ($1 = '' OR status = $1)
                ORDER BY question_id DESC
                LIMIT $2
                """,
                status,
                max(1, int(limit)),
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    out = []
    for r in rows:
        d = dict(r)
        d["okf_tags"] = json.loads(d["okf_tags"]) if d["okf_tags"] else []
        out.append(d)
    return json.dumps({"count": len(out), "questions": out}, ensure_ascii=False, default=str)


@mcp.tool()
async def propose_questions(questions: str, origin_run: str = "", origin_wave: int = 0) -> str:
    """Add questions to the bank. Duplicates are dropped, not rejected.

    Each question needs ``okf_tags``: which branches of the knowledge source it is
    grounded in. This is enforced rather than encouraged. A question no corpus branch
    can answer still gets answered by the hypothesis agent — with citations it had to
    invent, because being unable to find support is not an outcome the stage has. The
    tag requirement is where that becomes impossible instead of merely discouraged.

    Args:
        questions: JSON array of ``{"text", "okf_tags", "rationale"}``. ``text`` is the
            phrase handed to the hypothesis agent verbatim, so write it as an
            instruction ("from a ... perspective"), not as a sentence about one.
            ``okf_tags`` must be tags the corpus actually carries — check with
            ``okf_list_domains`` first.
        origin_run: which run proposed these. The driver fills this in.
        origin_wave: which wave within that run.

    Returns:
        ``{"added": [...], "duplicates": [...], "skipped": [...], "rejected": [...]}``.
        ``duplicates`` are word-for-word repeats. ``skipped`` are questions on the same
        tags whose wording is a reword of one already banked; each carries
        ``duplicate_of`` and ``similarity`` so the caller can see *which* question it
        collided with and go somewhere else instead of guessing. Neither is an error —
        both mean the generator converged on something already known, which is worth
        seeing. ``rejected`` is questions dropped for having no tags, with the reason.
    """
    try:
        parsed = json.loads(questions or "[]")
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"questions is not valid JSON: {e}"})
    if not isinstance(parsed, list):
        return json.dumps({"error": "questions must be a JSON array"})

    added: list[dict] = []
    duplicates: list[str] = []
    skipped: list[dict] = []
    rejected: list[dict] = []
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            # Retired questions are included on purpose. A reword of a question this
            # project has already worked through and set aside is the same wasted trial
            # as a reword of an open one.
            banked: list[tuple[int, str, list[str]]] = [
                (r["question_id"], r["text"],
                 json.loads(r["okf_tags"]) if r["okf_tags"] else [])
                for r in await conn.fetch(
                    "SELECT question_id, text, okf_tags FROM memstara_questions")
            ]
            for item in parsed:
                if not isinstance(item, dict):
                    rejected.append({"item": str(item), "why": "not an object"})
                    continue
                text = str(item.get("text", "")).strip()
                tags = [str(t).strip() for t in (item.get("okf_tags") or []) if str(t).strip()]
                if not text:
                    rejected.append({"text": text, "why": "empty text"})
                    continue
                if not tags:
                    rejected.append({
                        "text": text,
                        "why": "no okf_tags — a question the corpus cannot answer forces "
                               "the hypothesis stage to invent its citations",
                    })
                    continue
                # The literal check runs first so that "duplicates" keeps meaning what
                # it always meant — word-for-word repeat — and does not quietly turn
                # into a subset of the reword check below. The unique index is still the
                # backstop; this is only what decides which bucket the caller is told.
                key = _question_key(text)
                if any(_question_key(t) == key for _, t, _ in banked):
                    duplicates.append(text)
                    continue
                # Checked before the insert, not after: the unique index below is a
                # string comparison and would let this one through.
                near = _near_duplicate(text, tags, banked)
                if near is not None:
                    near_qid, ratio = near
                    skipped.append({
                        "text": text,
                        "duplicate_of": near_qid,
                        "similarity": round(ratio, 3),
                        "why": "same okf_tags and near-identical wording — this is a "
                               "reword of a banked question, not a new one. Ask about "
                               "a neighbouring mechanism instead.",
                    })
                    continue
                # ON CONFLICT DO NOTHING returns no row, which is how a duplicate is
                # told apart from an insert without a second query.
                qid = await conn.fetchval(
                    """
                    INSERT INTO memstara_questions
                        (text, text_key, okf_tags, rationale, origin_run, origin_wave)
                    VALUES ($1, $2, $3::jsonb, $4, $5, $6)
                    ON CONFLICT (text_key) DO NOTHING
                    RETURNING question_id
                    """,
                    text,
                    _question_key(text),
                    json.dumps(tags, ensure_ascii=False),
                    str(item.get("rationale", "")).strip(),
                    origin_run,
                    int(origin_wave),
                )
                if qid is None:
                    duplicates.append(text)
                else:
                    added.append({"question_id": qid, "text": text, "okf_tags": tags})
                    # So that two rewords of each other inside one batch cannot both
                    # land — neither is in the table yet when the other is checked.
                    banked.append((qid, text, tags))
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    return json.dumps(
        {"added": added, "duplicates": duplicates,
         "skipped": skipped, "rejected": rejected},
        ensure_ascii=False,
    )


@mcp.tool()
async def record_question_outcomes(run_tag: str, retire_after: int = 3) -> str:
    """Fold a finished run's scores back into the question bank, and retire used-up ones.

    The driver calls this, not an agent — it is bookkeeping about a wave that has ended,
    and no agent is in a position to know a wave has ended. It is also why the bank can
    say anything about which questions were worth asking: without this the bank is a
    list of what was asked and never a record of what came of it.

    Safe to call twice for the same run: ``times_used`` is recomputed from the results
    table rather than incremented, so a repeat lands on the same number.

    This is also where ``status`` finally gets written. The column and its two values
    have been in the schema since the bank was built, and until 2026-08-30 nothing ever
    set ``'exhausted'`` — so the open list only ever grew, and a question that had been
    tried three times came back to the curator looking exactly as untouched as one
    nobody had asked yet.

    Args:
        run_tag: the run whose results should be folded in.
        retire_after: how many results a question may accumulate before it is retired
            out of the open list. Pass 0 to retire nothing. Retiring is not deletion —
            ``read_questions(status="exhausted")`` still returns it, and it still blocks
            a reword in ``propose_questions``.

    Returns:
        ``{"ok": true, "questions_updated": N, "questions_retired": M}``.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            updated = await conn.fetch(
                """
                UPDATE memstara_questions q
                   SET times_used = s.n,
                       best_auc   = GREATEST(q.best_auc, s.mx),
                       status     = CASE WHEN $2 > 0 AND s.n >= $2
                                         THEN 'exhausted' ELSE q.status END
                  FROM (SELECT question_id, count(*) AS n, max(auc) AS mx
                          FROM memstara_results
                         WHERE question_id IS NOT NULL
                         GROUP BY question_id) s
                 WHERE q.question_id = s.question_id
                   AND EXISTS (SELECT 1 FROM memstara_results r
                                WHERE r.question_id = q.question_id
                                  AND ($1 = '' OR r.run_tag = $1))
                RETURNING q.question_id, q.status
                """,
                run_tag,
                max(0, int(retire_after)),
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)
    retired = sum(1 for r in updated if r["status"] == "exhausted")
    return json.dumps(
        {"ok": True, "questions_updated": len(updated), "questions_retired": retired})


if __name__ == "__main__":
    mcp.run()
