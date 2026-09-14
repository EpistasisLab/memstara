"""Memstara Viewer — read-only HTTP surface over the two databases.

One polling endpoint on purpose. Six screens each fetching their own slice would send
six requests every two seconds and could show mutually inconsistent states (one request
gets the data from before an update, another from after); `/api/snapshot` returns one
coherent object and the frontend selects from it.

Nothing here writes. The account it connects with (`memstara_viewer`) holds SELECT and
nothing else, so read-only is enforced by the database rather than by this code being
careful — verified: UPDATE and DELETE are refused.

==============================================================================
 How to read this file
==============================================================================

 What this file does
   The FastAPI entry point. All the actual work is done by scene.py; this file is only
   the HTTP shell — four routes, the CORS setting, and closing the pools on shutdown.
   Started under Docker, this app is :8071 of the `memstara-viewer-api` container.

 The five endpoints
   GET /api/health          which of the two DBs answers. Also used as the container
                            healthcheck
   GET /api/runs            the list of runs (run_tag). For the selector at the top of
                            the screen
   GET /api/snapshot        ★ the workhorse. Called every 2 seconds, it holds
                            everything all six screens need
   GET /api/task/{task_id}  one task + the history of the agent runs that touched it
   GET /api/result/{id}     one result + the matcher record behind its columns

 Easy things to miss
   1. **The pools are not built up front in lifespan.** The viewer has to start even
      when one DB is down. On shutdown it only closes them.
   2. Six screens and one endpoint: the reason is not performance but **consistency.**
   3. `allow_methods=["GET"]` — that this is read-only is written down once more here,
      in the CORS setting.
   4. The trail in `/api/task` cannot be read off the board. The board holds no run
      ids, so it is rebuilt by retracing the record of tool calls.
   5. **`/api/result` is the one read the snapshot deliberately does not carry**, and
      that is not an inconsistency with point 2. `match_trace` is 598 kB across the 81
      stored results against 89 kB for every explanation column the snapshot does
      carry, and the snapshot is polled every two seconds. Consistency is worth one
      request per screen; it is not worth six-fold that, thirty times a minute, for
      something a person opens one of at a time.
==============================================================================
"""

from __future__ import annotations

import os
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent))
# Put this directory on the import path so it can be written **flat**, as in
# `import queries`. The `# noqa: E402` on the imports below marks "the imports after
# this line are known about and intended" (this sys.path manipulation has to come
# first).

import run_artifacts  # noqa: E402
import scene  # noqa: E402
import stores  # noqa: E402
from db import pools  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The app's lifecycle. What comes before `yield` happens at startup, what comes
    # after at shutdown.
    # Pools are created on first use, not here: the viewer has to start even when a
    # database is down. That is the whole point of keeping the two stores apart.
    # Connect up front here and the container fails to boot while the core DB is
    # switched off. So there is nothing to do at startup (straight to yield) and only
    # closing to do at shutdown.
    yield
    await pools.close()


app = FastAPI(title="Memstara Viewer", lifespan=lifespan)
# The app itself. Everything below is GET and nothing else.

# During development the Vite dev server (5173) runs on another port, so CORS has to be
# allowed. In Docker nginx serves both the web and the API from **one origin** and this
# setting becomes a no-op. The list can be swapped out with the `VIEWER_CORS`
# environment variable.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("VIEWER_CORS", "http://localhost:5173").split(",") if o],
    allow_methods=["GET"],
    # GET only. That this is read-only is written down **three times over** — in the DB
    # grants, in the account, and here.
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Which stores answered. Cheap enough to be the container healthcheck."""
    # It does not return a fake True; **it actually fires one query at each side.**
    # That is what stops "up, but cannot read the DB" from passing for healthy.
    # `definitions_from_pipeline` says whether stores.py imported the real pipeline
    # definitions (True) or is using the copied stand-in table (False).
    async def probe(which: str, table: str):
        async def read(conn):
            await conn.fetchval(f"SELECT 1 FROM {table} LIMIT 1")
        await pools.guarded(which, read, None)

    await asyncio.gather(probe("memstara", "memstara_blackboard"),
                         probe("core", "run_steps"))
    return {
        "health": pools.health.as_dict(),
        "definitions_from_pipeline": stores.IMPORTED_FROM_PIPELINE,
    }


@app.get("/api/runs")
async def runs() -> dict[str, Any]:
    # The run tags and nothing else. The run selector at the top of the screen uses
    # this. The same list is inside snapshot too, but this is opened separately for
    # when only the selector needs refreshing.
    return {"runs": await scene.list_runs()}


@app.get("/api/pipeline-results")
async def pipeline_results(run_tags: str = Query(min_length=1, max_length=600)):
    """Return every result for up to three explicitly selected executions."""
    tags = list(dict.fromkeys(run_tags.split(",")))
    if len(tags) > 3 or any(not tag for tag in tags):
        raise HTTPException(400, "Choose one to three execution IDs")
    try:
        async with asyncio.timeout(4):
            groups = await asyncio.gather(*(scene._results(tag) for tag in tags))
            boards = await asyncio.gather(*(scene._board(tag) for tag in tags))
            configs = await asyncio.to_thread(run_artifacts.configs)
    except TimeoutError:
        raise HTTPException(503, "Results temporarily unavailable; retain previous results") from None
    if not pools.health.as_dict()["memstara"]["up"]:
        raise HTTPException(503, "Results database is unavailable")
    output = []
    for tag, results in zip(tags, groups, strict=True):
        config = configs.get(tag) or {}
        for result in results:
            output.append({**result, **run_artifacts.result_identity(config, tag, result["trial"])})
    failures = []
    for tag, tasks in zip(tags, boards, strict=True):
        for task in tasks:
            if task["status"] == "failed":
                failures.append({key: task[key] for key in ("task_id", "trial", "task_type", "error")} |
                                run_artifacts.result_identity(configs.get(tag) or {}, tag, task["trial"]))
    return {"results": output, "failures": failures}


@app.get("/api/snapshot")
async def snapshot(run_tag: str | None = Query(default=None)) -> dict[str, Any]:
    # ★ The workhorse endpoint. The frontend calls this one thing every 2 seconds.
    # Given no `run_tag`, scene picks the most recent run itself.
    # All the work is inside scene.snapshot and this only passes it along — the
    # interpretation has to live in one place or the screens start contradicting
    # each other.
    return await scene.snapshot(run_tag)


@app.get("/api/task/{task_id}")
async def task(task_id: int) -> dict[str, Any]:
    """One task with the agent runs that touched it, in order.

    The board holds no run ids, so the trail is rebuilt from the board windows —
    create_task / claim_task / submit_result carry the task id in their payloads, which
    is what lets them be strung back together.
    """
    board = await scene._board("", task_id=task_id)
    # The empty string means "every run" (the `$1 = '' OR ...` in queries.BOARD). Why it
    # is not narrowed to one run: a task detail has to open straight from a link
    # whichever run it belongs to.
    found = next((t for t in board if t["task_id"] == task_id), None)
    if found is None:
        if not pools.health.memstara:
            raise HTTPException(
                status_code=503,
                detail="The Memstara database is unavailable; task existence could not be checked.",
            )
        raise HTTPException(status_code=404, detail=f"task {task_id} is not on the board")
    # A task that does not exist is reported plainly as a **404**, not as an empty
    # shell. Show a blank screen and it cannot be told apart from "has the data not
    # arrived yet?".

    artifacts = await asyncio.to_thread(run_artifacts.lookup, found["run_tag"])
    run_ids = [call["run_id"] for call in (artifacts or {}).get("calls", []) if call.get("run_id")]
    core = await scene._core_facts(run_ids, task_history=True)
    trail = [{
        # Through `stage_of_agent` / `label_of` rather than the dicts, so a hypothesis
        # agent carrying a playbook resolves to its stage and keeps its standard on the
        # label. Straight off the dict it would fall through to the raw agent name in
        # both fields, which is the one place a trail is read to see which *stage*
        # touched a task.
        "agent": stores.stage_of_agent(t["name"]) or t["name"],
        "agent_label": stores.label_of(t["name"]),
        "tool": t["tool"],
        "run_id": str(t["run_id"]),
        "at": scene._iso(t["started_at"]),
    } for t in core["touches"] if t.get("task_id") and int(t["task_id"]) == task_id]
    # The trail above: core["touches"] is already in time order (the ORDER BY in
    # queries.TASK_TOUCHES), so it is not sorted again here. task_id comes out of JSON
    # and may be a string, so it is lined up with `int()` before comparing — leave that
    # out and the whole trail looks empty.
    #
    # Why the return below carries health along: when the core DB is down and the trail
    # is empty, the screen has to be able to tell "no history" from "core cannot be
    # read".

    return {"task": found, "trail": trail, "health": pools.health.as_dict()}


@app.get("/api/result/{result_id}")
async def result(result_id: int) -> dict[str, Any]:
    """One result, with the matcher record that explains where its columns came from.

    This is the only place `match_trace` is served. It is left out of the snapshot for a
    measured reason (see the note on queries.RESULT_ONE), so a screen that wants to show
    *why this column* asks here, once, when someone opens a result.
    """
    found = await scene.result_detail(result_id)
    if found is None:
        # Two different failures reach this line and they are told apart rather than
        # both reported as 404. `scene.result_detail` returns None for "no such row" and
        # also for "the query could not run" — `guarded` hands back the fallback either
        # way — so a database that is down would otherwise be reported to a person as a
        # result that does not exist. That is not a degraded answer, it is a wrong one.
        # `/api/task` follows the same unavailable-versus-absent distinction.
        if not pools.health.memstara:
            raise HTTPException(
                status_code=503,
                detail=f"the memstara database is not answering: {pools.health.memstara_error}",
            )
        raise HTTPException(status_code=404, detail=f"no result {result_id}")

    return {"result": found, "health": pools.health.as_dict()}


@app.get("/api/discovery/questions")
async def discovery_questions(before: int = Query(default=0, ge=0)):
    from discovery import question_list
    return await question_list(before)


@app.get("/api/discovery/questions/{question_id}")
async def discovery_question(question_id: int):
    from discovery import question_detail
    return await question_detail(question_id)


@app.get("/api/discovery/report")
async def discovery_report(run_tag: str = Query(min_length=1, max_length=200)):
    from discovery import run_report
    return await run_report(run_tag)


@app.get("/api/discovery/live")
async def discovery_live(run_tags: str = Query(min_length=1, max_length=600)):
    from discovery import live_outputs
    tags = list(dict.fromkeys(run_tags.split(',')))
    if len(tags) > 3 or any(not tag for tag in tags):
        raise HTTPException(400, 'Choose one to three pipeline executions.')
    return await live_outputs(tags)
