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

Core launches this file as a stdio subprocess, same shape as src/memstara/mcp_servers/data.py.

The board lives in **Memstara's own database**, not core's — see ``compose.yml``.

Environment::

    MEMSTARA_DATABASE_URL    must be on `mcp_allowed_env_vars` in src/memstara/config.py —
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

 To call it by hand: `python -m memstara.debug_harness board`
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
# does nothing at all. See src/memstara/mcp_servers/debug_hook.py.
from memstara.mcp_servers.debug_hook import quiet_child, wait_for_debugger

quiet_child()          # silences the three startup messages a child prints
wait_for_debugger('memstara-blackboard')

mcp = FastMCP("memstara-blackboard")

# Who comes next once a stage finishes. A stage missing from this table (interpret)
# is the last one. submit_result reads this to decide whether status becomes
# 'ready' (there is a next stage) or 'done'.
NEXT_STAGE = {"hypothesis": "data", "data": "ml", "ml": "interpret"}


# The address used when the environment variable is unset. It points at the container
# compose.yml starts. Port 5463 — a **different database** from core's 5453.
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



def _pipeline_run() -> str:
    from memstara.evaluation import active_plan
    config = active_plan() or {}
    primary = config.get("hypothesis_policy", {}).get("version") == "knowledge_only_v1"
    return str(config.get("run_tag", "")) if config.get("pipeline_id") or primary else ""

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
    scope = _pipeline_run()
    if scope:
        if run_tag and run_tag != scope:
            return json.dumps({"error": "This tool is scoped to its pipeline run"})
        run_tag = scope
    # A bare string is refused rather than iterated. Python would iterate it
    # character by character and store a JSON array of single letters — a task the
    # data stage then reports as 30-odd missing columns, which reads like a naming
    # problem and is not one.
    from memstara.evaluation import active_plan
    snapshot = active_plan()
    if snapshot and (y_column != snapshot["y_column"] or run_tag != snapshot["run_tag"]):
        return json.dumps({"error": "Task target or run differs from the immutable run configuration"})
    if isinstance(columns, list) and (y_column in columns or (os.environ.get("MEMSTARA_OUTCOME_COLUMN")
            and os.environ["MEMSTARA_OUTCOME_COLUMN"] in columns)):
        return json.dumps({"error": "The target must not be included as a feature"})
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
                     hypothesis, columns, y_column, okf_concept_ids, question_id, evaluation, hypothesis_id)
                VALUES ($1, $2, $3, 'ready', 'data', $4, $5::jsonb, $6, $7::jsonb, $8, $9::jsonb,
                    COALESCE((SELECT writer FROM memstara_questions WHERE question_id=$8), 'hypothesis'))
                RETURNING task_id
                """,
                run_tag, trial, perspective, hypothesis, json.dumps(cols), y_column,
                json.dumps(ids), (int(question_id) or None),
                json.dumps({"config_hash": snapshot.get("config_hash"), "plan": snapshot["evaluation"],
                            "skills": snapshot.get("books", {}),
                            "hypothesis_policy": snapshot.get("hypothesis_policy", {})} if snapshot else {}),
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001 - the agent must see why
        return _err(e)
    return json.dumps({"task_id": task_id, "status": "ready", "task_type": "data"})


@mcp.tool()
async def claim_task(task_type: str, run_tag: str = "", worker: str = "") -> str:
    """Take one waiting task of your type, so nobody else can take it.

    Args:
        task_type: one of "data", "ml", "interpret" — the stage you are.
        run_tag: the run you are working. Pass the one you were told to work and you
            will only ever be handed tasks from it. Leaving it empty takes the oldest
            waiting task of your type from *any* run — which is how a task abandoned
            by some earlier, unrelated run ends up being done, and paid for, by this
            one. Do not leave it empty when you were given a run tag.
        worker: who you are — the name you were given in your instructions. It is
            written onto the task and is what ``submit_result`` compares against, so
            pass the **same** string to both. When two workers of one type are running
            it is the only thing that tells them apart: leave it empty and the board
            records the task as held by nobody, and a result submitted late, after the
            task was handed to somebody else, is no longer refused.

    Returns:
        JSON with the task and everything earlier stages left on it, including
        ``y_column`` — the outcome to predict, carried on the task so no stage has to be
        told it separately, and ``claimed_by``, the identity it was recorded under.
        When the board has nothing waiting for you it returns
        ``{"task_id": null}`` — that means
        there is no work for you right now, so stop. Do not invent a task and do not
        take one of another type.
    """
    scope = _pipeline_run()
    if scope:
        if run_tag and run_tag != scope:
            return json.dumps({"error": "This tool is scoped to its pipeline run"})
        run_tag = scope
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
                        -- Written in the same statement that takes the row, not in a
                        -- second one afterwards. Between two statements there is a
                        -- moment where the task is in_progress and held by nobody,
                        -- and that moment is exactly what the column exists to close.
                        claimed_by = $3,
                        updated_at = now()
                    WHERE task_id = (
                        SELECT task_id FROM memstara_blackboard
                        WHERE task_type = $1 AND status = 'ready'
                          -- An empty string reads the whole board, as before
                          -- (backward compatible).
                          AND ($2 = '' OR run_tag = $2)
                          AND (NOT (evaluation ? 'interpretation_branch')
                               OR evaluation->'interpretation_branch'->>'worker' = $3)
                        ORDER BY task_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING task_id, run_tag, trial, perspective, hypothesis,
                              columns, y_column, okf_concept_ids, subset_path,
                              columns_used, auc, feature_importance, model, claimed_by, evaluation, hypothesis_id
                    """,
                    task_type, run_tag, worker,
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
    for k in ("columns", "okf_concept_ids", "columns_used", "feature_importance", "evaluation"):
        out[k] = json.loads(out[k]) if out[k] else ([] if k != "feature_importance" else {})
    # default=str — JSON does not know values such as datetime, so they become strings.
    return json.dumps(out, ensure_ascii=False, default=str)


@mcp.tool()
async def submit_result(task_id: int, subset_path: str = "",
                        columns_used: list[str] | None = None,
                        columns_missing: list[str] | None = None, auc: float | None = None,
                        feature_importance: str = "", model: str = "",
                        interpretation: str = "", worker: str = "", error: str = "") -> str:
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
        model: ml stage — **the `model` field train_and_score returned, copied through
            unchanged.** Not optional in practice: the engine decides what the numbers in
            feature_importance are. `random_forest` and `xgboost` return impurity/gain,
            non-negative and summing to about 1; `sklearn_hgb` returned a drop in AUC,
            which is a different unit and can be negative. Leave it out and the row
            records importances nobody can later say the scale of — which is what every
            result stored before 2026-09-08 does. Since that date `xgboost` is the only
            value a new row can carry, and copying it through unchanged is still the
            instruction: an agent that decides what the engine "should" be is guessing at
            something the tool already told it, and the first day the answer changes is
            the day the guess goes unnoticed.
        error: explicit failure reason without patient values; requires the current worker.
        interpretation: interpretation stage — the write-up.
        worker: who you are — **the same string you passed to claim_task.** If the task
            is now held by somebody else this is refused and nothing is written, which
            is what stops a late result from landing on work that was handed on while
            you were still busy. Leave it empty and that comparison cannot be made.

    Returns:
        JSON with the task's new status and whose turn it is now. After the
        interpretation stage the task is done and a row is added to the results table.
        On a refusal, JSON with ``error`` and nothing written.
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
                from memstara.interpretation_fanout import metadata, aggregate, expand
                scope = _pipeline_run()
                if scope and await conn.fetchval(
                    'SELECT run_tag FROM memstara_blackboard WHERE task_id=$1', task_id
                ) != scope:
                    return json.dumps({"error": "Task belongs to another pipeline run"})
                before = await conn.fetchval('SELECT evaluation FROM memstara_blackboard WHERE task_id=$1', task_id)
                branch = metadata(before).get('interpretation_branch')
                if branch:
                    await conn.execute('SELECT pg_advisory_xact_lock(72331, $1::integer)', branch['source_task_id'])
                cur = await conn.fetchrow(
                    "SELECT task_type, status, claimed_by, subset_path, evaluation, y_column FROM memstara_blackboard "
                    "WHERE task_id = $1 FOR UPDATE",
                    task_id,
                )
                if cur is None:
                    return json.dumps({"error": f"no task {task_id}"})
                if branch and (worker != branch['worker'] or worker != cur['claimed_by']):
                    return json.dumps({"error": "Only the assigned interpreter may submit this branch."})
                # Blocks writing a result to a task that was never claimed.
                if cur["status"] != "in_progress":
                    return json.dumps(
                        {"error": f"task {task_id} is '{cur['status']}', not in_progress — claim it first"}
                    )
                # And blocks writing it onto work somebody else is now holding, which
                # the status check above cannot do on its own — a task reclaimed after
                # a stall and taken by a second worker is in_progress again, and looks
                # from here exactly like the task the first worker still thinks is its
                # own. Comparing the holder is the only thing that tells those apart.
                #
                # **The guard is exactly as strong as the identities it is given.**
                # Both sides empty and this is a no-op, which is what keeps every
                # existing caller working — but it is a no-op, not a weaker check, and
                # a stage that does not name itself has no ownership protection at all.
                if cur["claimed_by"] and worker and cur["claimed_by"] != worker:
                    return json.dumps(
                        {"error": f"task {task_id} is held by '{cur['claimed_by']}', not '{worker}' "
                                  f"— it was reclaimed and taken by somebody else while you worked. "
                                  f"Do not resubmit; claim a new task."}
                    )

                if error:
                    if not worker or worker != cur["claimed_by"]:
                        return json.dumps({"error": "Reporting failure requires the current worker identity"})
                    await conn.execute(
                        "UPDATE memstara_blackboard SET status='failed', error=$2, claimed_by='', "
                        "claimed_at=NULL, updated_at=now() WHERE task_id=$1", task_id, error[:2000])
                    if branch:
                        await aggregate(conn, branch['source_task_id'])
                    return json.dumps({"ok": True, "task_id": task_id, "status": "failed",
                                       "task_type": cur["task_type"], "reason": error[:2000]})

                stage = cur["task_type"]          # the stage this task is at now
                if stage == "interpret" and not interpretation.strip():
                    return json.dumps({"error": "Interpretation must contain a nonempty evidence-based write-up"})
                if stage == "interpret":
                    # Store actual interpreter identity with the final result, so the
                    # report can distinguish skill-dependent perspectives across trials.
                    from pathlib import Path
                    previous = cur["evaluation"] or {}
                    if isinstance(previous, str):
                        previous = json.loads(previous)
                    identity = cur["claimed_by"] or worker
                    config_path = os.environ.get("MEMSTARA_RUN_CONFIG")
                    config = json.loads(Path(config_path).read_text()) if config_path else {}
                    books = config.get("books", {}).get("interpreter") or [""]
                    suffix = identity.rsplit("#", 1)[-1]
                    slot = int(suffix) - 1 if "#" in identity and suffix.isdigit() else 0
                    skill = books[slot] if slot < len(books) else books[0]
                    await conn.execute("UPDATE memstara_blackboard SET evaluation=$2::jsonb WHERE task_id=$1",
                                       task_id, json.dumps({**previous, "interpreter": {
                                           "worker": identity, "skill": skill}}))
                if stage == "ml":
                    from pathlib import Path
                    from memstara.paths import DEFAULT_OUTPUT_DIR
                    artifact = Path(cur["subset_path"]).resolve().with_suffix(".evaluation.json")
                    root = Path(os.environ.get("MEMSTARA_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR).resolve()
                    try:
                        artifact.relative_to(root)
                        measured = json.loads(artifact.read_text())
                    except (ValueError, OSError):
                        return json.dumps({"error": "Train the claimed subset before submitting its ML result"})
                    previous = cur["evaluation"]
                    if isinstance(previous, str):
                        previous = json.loads(previous)
                    import hashlib
                    if measured.get("y_column") != cur["y_column"]:
                        return json.dumps({"error": "The measured target differs from the claimed task"})
                    if previous and previous.get("config_hash") != measured.get("config_hash"):
                        return json.dumps({"error": "The measured artifact belongs to another run configuration"})
                    if measured["evaluation"]["dataset_sha256"] != hashlib.sha256(
                            Path(cur["subset_path"]).read_bytes()).hexdigest():
                        return json.dumps({"error": "The subset changed after training; evaluate it again"})
                    if measured.get("status") == "failed":
                        await conn.execute(
                            "UPDATE memstara_blackboard SET status='failed', error=$2, "
                            "evaluation=$3::jsonb, claimed_by='', claimed_at=NULL, updated_at=now() WHERE task_id=$1",
                            task_id, measured["error"], json.dumps({**(previous or {}), **measured}))
                        return json.dumps({"ok": True, "task_id": task_id, "status": "failed",
                                           "task_type": "ml", "reason": measured["error"]})
                    auc, model = measured["auc"], measured["model"]
                    feature_importance = json.dumps(measured["feature_importance"])
                    await conn.execute("UPDATE memstara_blackboard SET evaluation=$2::jsonb WHERE task_id=$1",
                                       task_id, json.dumps({**(previous or {}), **measured}))
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
                        -- $10 is last rather than beside $6 because appending a
                        -- parameter cannot renumber the nine that were already here.
                        model              = COALESCE(NULLIF($10, ''), model),
                        interpretation     = COALESCE(NULLIF($7, ''), interpretation),
                        status             = $8,
                        task_type          = $9,
                        claimed_at         = NULL,
                        -- Released with claimed_at. The task is either waiting for the
                        -- next stage or finished; either way the worker that just
                        -- submitted is no longer holding it, and a row that went back
                        -- to 'ready' still naming somebody would refuse that next
                        -- stage's own submission.
                        claimed_by         = '',
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
                    model,
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
                if stage == "ml":
                    config_path = os.environ.get("MEMSTARA_RUN_CONFIG")
                    config = json.loads(Path(config_path).read_text()) if config_path else {}
                    await expand(conn, task_id, config)
                if new_status == "done" and branch:
                    await aggregate(conn, branch['source_task_id'])
                elif new_status == "done":
                    await conn.execute(
                        """
                        INSERT INTO memstara_results
                            (task_id, run_tag, trial, perspective, hypothesis,
                             columns, columns_used, columns_missing,
                             okf_concept_ids, match_trace, question_id,
                             y_column, auc, feature_importance, model, interpretation, evaluation, hypothesis_id)
                        SELECT task_id, run_tag, trial, perspective, hypothesis,
                               columns, columns_used, columns_missing,
                               okf_concept_ids, match_trace, question_id,
                               y_column, auc, feature_importance, model, interpretation, evaluation, hypothesis_id
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
    scope = _pipeline_run()
    if scope:
        if run_tag and run_tag != scope:
            return json.dumps({"error": "This tool is scoped to its pipeline run"})
        run_tag = scope
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
    scope = _pipeline_run()
    if scope:
        if run_tag and run_tag != scope:
            return json.dumps({"error": "This tool is scoped to its pipeline run"})
        run_tag = scope
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                """
                SELECT task_id, run_tag, trial, perspective, status, task_type,
                       hypothesis, columns, okf_concept_ids, match_trace, question_id,
                       y_column, columns_used, columns_missing,
                       -- Who is holding it. This is the only window a person has onto
                       -- the board, so a status of 'in_progress' with no name beside it
                       -- says "somebody is working on this" without saying who — which
                       -- is the question worth asking the moment there are two workers
                       -- of one type. A plain TEXT column, so it needs no unpacking
                       -- below.
                       claimed_by,
                       auc, feature_importance,
                       -- Which engine produced those importances. '' means it was not
                       -- recorded, which is a different claim from any engine name and
                       -- is what every row written before 2026-09-08 says.
                       model,
                       interpretation, attempts, error, evaluation
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
                  "columns_missing", "feature_importance", "evaluation"):
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

        ``model`` says which engine produced the importances, and it has to be read
        before they are compared: impurity/gain from ``random_forest`` and ``xgboost``
        is not the same quantity as the permutation drop in AUC ``sklearn_hgb``
        fell back to. Two results with different ``model`` values have importances on
        different scales. ``''`` means the engine was not recorded — do not guess it.

        **This matters more since 2026-09-08, not less.** ``xgboost`` became the only
        engine that day, so every new row is on one scale — and the rows this tool
        returns are not all new. The mixed-scale case is now invisible from the code
        alone and reachable only through the data, which is precisely when a reader
        stops checking.
    """
    scope = _pipeline_run()
    if scope:
        if run_tag and run_tag != scope:
            return json.dumps({"error": "This tool is scoped to its pipeline run"})
        run_tag = scope
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                """
                SELECT result_id, task_id, run_tag, trial, perspective, hypothesis,
                       columns, columns_used, columns_missing,
                       okf_concept_ids, match_trace, question_id,
                       y_column, auc, feature_importance, model, interpretation, created_at, evaluation, hypothesis_id
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
                  "okf_concept_ids", "match_trace", "feature_importance", "evaluation"):
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
async def read_question_catalog(limit: int = 200) -> str:
    """Duplicate avoidance for primary generation: current-run knowledge text only.

    No performance, importance, prior rationale or historical mixed-policy questions
    are exposed. Missing policy fails closed rather than reading the legacy bank.
    """
    from memstara.evaluation import active_plan
    plan = active_plan() or {}
    if plan.get("hypothesis_policy", {}).get("version") != "knowledge_only_v1":
        return json.dumps({"error": "A new knowledge-only run is required", "questions": []})
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                "SELECT question_id, text, okf_tags FROM memstara_questions "
                "WHERE origin_run=$1 ORDER BY question_id DESC LIMIT $2",
                plan["run_tag"], max(1, min(200, int(limit))),
            )
        finally:
            await conn.close()
        return json.dumps({"questions": [
            {"question_id": row["question_id"], "text": row["text"],
             "okf_tags": json.loads(row["okf_tags"]) if isinstance(row["okf_tags"], str) else row["okf_tags"]}
            for row in rows]}, ensure_ascii=False)
    except Exception as exc:
        return _err(exc)


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
        been through a wave. ``claimed_run`` and ``claimed_by`` say whether some run is
        working it right now; both empty means nobody is.

        **A claimed question is still listed here.** This tool answers "what has this
        project thought to ask", which does not stop being true while somebody is asking
        it. Hiding claimed rows would make the bank look emptier than it is to the
        curator, which is exactly how it would propose a duplicate of the question
        another worker has in hand.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                """
                SELECT question_id, text, okf_tags, rationale, origin_run, origin_wave,
                       times_used, best_auc, status, created_at, writer,
                       -- Shown for the same reason claimed_by is shown on the board: a
                       -- claim nobody can see is a claim nobody trusts, and "who is
                       -- working this" is the question worth asking the moment there are
                       -- two hypothesis workers. Plain TEXT, so no unpacking below.
                       claimed_run, claimed_by
                FROM memstara_questions
                WHERE ($1 = '' OR status = $1) AND ($3 = '' OR origin_run = $3)
                ORDER BY question_id DESC
                LIMIT $2
                """,
                status,
                max(1, int(limit)), _pipeline_run(),
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
async def claim_question(run_tag: str = "", worker: str = "", stale_after: int = 600, question_id: int = 0) -> str:
    """Take one open question out of the bank, so no other agent sets out from it.

    The hypothesis stage's equivalent of ``claim_task``. The other three stages take work
    off the board; this stage **creates** the work, and what it needs to not collide over
    is the question it starts from. With two hypothesis agents seeding one wave, both
    would otherwise reach for the newest question in the bank and the wave would spend
    twice to investigate one thing.

    Args:
        run_tag: the run you are working. It is recorded as the holder, because the
            driver gives a whole run's questions back at once when its wave has finished
            seeding.
        worker: who you are — the name you were given in your instructions. Recorded
            beside the run so a person reading the bank can see which of that run's
            workers took which question.
        stale_after: seconds a claim may stand before it is treated as abandoned and the
            question may be taken again. This is what keeps a run that died mid-wave from
            removing its questions from the bank for good.

    Returns:
        JSON with ``question_id``, the question ``text``, and the ``okf_tags`` it is
        grounded in — pass the id and the text on to ``create_task``. When the bank has
        nothing open left it returns ``{"question_id": null}``: there is nothing to ask,
        so stop. Do not invent a question, and do not re-use one you were not handed.
    """
    from memstara.evaluation import active_plan
    plan = active_plan() or {}
    primary = plan.get("hypothesis_policy", {}).get("version") == "knowledge_only_v1"
    scope = plan.get("run_tag", "") if primary else _pipeline_run()
    if scope:
        if run_tag and run_tag != scope:
            return json.dumps({"error": "This tool is scoped to its pipeline run"})
        run_tag = scope
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            # The same statement shape as claim_task, for the same reason: FOR UPDATE
            # SKIP LOCKED makes a second claimer step over the row the first one picked
            # rather than queue behind it and take the very same one.
            #
            # ORDER BY question_id DESC is read_questions' own order, and it matters here
            # rather than being a detail — the curator's freshly grounded questions are
            # the highest ids, so this hands out the new ones before falling back on the
            # bank's older stock. Claiming ascending would spend a wave re-asking the
            # oldest questions in the project while the ones just proposed sat untouched.
            #
            # The staleness arm of the WHERE is the crash path. release_questions() is
            # the normal ending and the driver calls it when a wave finishes seeding; a
            # run that dies in between would otherwise hold its questions for ever, and
            # this table has no run_tag to scope a cleanup by, so nothing else would ever
            # find them.
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    UPDATE memstara_questions SET
                        claimed_run = $1,
                        claimed_by  = $2,
                        claimed_at  = now()
                    WHERE question_id = (
                        SELECT question_id FROM memstara_questions
                        WHERE status = 'open' AND ($4 = 0 OR question_id = $4)
                          AND ($5 = '' OR origin_run = $5)
                          AND (claimed_at IS NULL
                               OR claimed_at < now() - make_interval(secs => $3))
                        ORDER BY question_id DESC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING question_id, text, okf_tags, claimed_run, claimed_by
                    """,
                    run_tag, worker, max(0, int(stale_after)), question_id, scope,
                )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    # None means the bank is empty of open, unclaimed questions. A normal state, not an
    # error — same contract as claim_task's null task_id, and the agent stops here.
    if row is None:
        return json.dumps({"question_id": None})

    out: dict[str, Any] = dict(row)
    out["okf_tags"] = json.loads(out["okf_tags"]) if out["okf_tags"] else []
    return json.dumps(out, ensure_ascii=False, default=str)


@mcp.tool()
async def propose_questions(questions: str, origin_run: str = "", origin_wave: int = 0, writer: str = "") -> str:
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
    scope = _pipeline_run()
    if scope:
        if origin_run and origin_run != scope:
            return json.dumps({"error": "This tool is scoped to its pipeline run"})
        origin_run = scope
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
            async with conn.transaction(isolation="read_committed"):
                # Serialise the read/compare/insert decision across every writer and
                # run. The transaction lock releases on failure or disconnect.
                # A finite wait must not recreate an unbounded DB queue.
                await conn.execute("SET LOCAL lock_timeout = '3s'")
                await conn.execute("SELECT pg_advisory_xact_lock(180947, 53)")
                # Retired questions are included on purpose. A reword of a question this
                # project has already worked through and set aside is the same wasted trial
                # as a reword of an open one.
                banked: list[tuple[int, str, list[str]]] = [
                    (r["question_id"], r["text"],
                     json.loads(r["okf_tags"]) if r["okf_tags"] else [])
                    for r in await conn.fetch(
                        "SELECT question_id, text, okf_tags FROM memstara_questions "
                        "WHERE ($1 = '' OR origin_run = $1)", _pipeline_run())
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
                            (text, text_key, okf_tags, rationale, origin_run, origin_wave, writer)
                        VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
                        ON CONFLICT (text_key) DO NOTHING
                        RETURNING question_id
                        """,
                        text,
                        (f"{scope}::" if scope else "") + _question_key(text),
                        json.dumps(tags, ensure_ascii=False),
                        str(item.get("rationale", "")).strip(),
                        origin_run,
                        int(origin_wave), writer,
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
    scope = _pipeline_run()
    if scope:
        if run_tag and run_tag != scope:
            return json.dumps({"error": "This tool is scoped to its pipeline run"})
        run_tag = scope
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
