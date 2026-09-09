"""Turns database rows into the one snapshot every screen reads.

All interpretation happens here, on purpose. If each screen worked out for itself what
"this agent is carrying task 27" means, two screens would eventually disagree about the
same run — and the viewer's only job is to be trusted.

Two stores are read independently (see db.guarded). If core's database is down the board
and results still come back and `health.core.up` is false; the scene then draws the
characters as **"unknown", not at rest** — it does not pretend to know what they are
doing.

==============================================================================
 How to read this file
==============================================================================

 What this file does
   It assembles the raw rows returned by the SQL in queries.py into one lump of JSON
   (a "snapshot") the frontend can draw as it stands. This is the viewer's **brain.**
   There is one entry point, `snapshot()` at the bottom, called once every 2 seconds.

 Top to bottom
   FLASH_SECONDS / RUN_ALIVE_SECONDS / STAGE_INDEX   the three judgement thresholds
   _jsonb / _iso / _retried        the small converters
   --- Reads ---
   list_runs / _board / _results   from the memstara DB
   _trace_groups / result_detail   one result and its matcher record. **Not part of the
                                   snapshot** — the trace is too big to poll, which is
                                   why it has its own endpoint. See queries.RESULT_ONE.
   _core_facts                     from the core DB (seven queries on one connection)
   --- The scene ---
   _carrying     ★ replays who is holding which task right now
   _build_scene  ★ settles the characters' state, position and flashing
   _agent_totals / _access         the table and the access map
   _feed                           the newest calls, in order, for the feed panel
   snapshot()    ★ gathers all of the above into one object

 Easy things to miss
   1. **RUN_ALIVE_SECONDS (900s)** — the time window that stops a dead run from
      looking alive. Without it a character stands there "working" forever because of
      a run whose process died. Set it too tight, though, and it does the opposite
      harm: it hides a run that is alive but thinking. See the note on the constant.
   2. **`attempts` is not a retry count.** A task is claimed afresh at every stage
      handover, so even a healthy task ends at attempts 3. `_retried()` subtracts that
      difference out.
   3. **When core is down it is "unknown", not "idle".** Saying idle would be making
      an assertion that cannot be made.
   4. `_carrying` answers a question the board does not. A board row marked
      `in_progress` says only "somebody is holding it", never **who.**
   5. The access map counts **both** the board path and the supervisor path. Count
      only one and it is under-reported about fivefold.
==============================================================================
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

import asyncpg

import queries
import stores
from db import pools

#: Seconds a computed snapshot may be reused. Every open tab asks for the same object at
#: the same cadence, so without this each one pays for its own copy of the same work.
SNAPSHOT_TTL = 1.5

#: Seconds to wait for whoever is already computing this run's snapshot. Without a bound
#: here the lock below is an unbounded wait, and one slow computation holds every other
#: tab on the same run until nginx gives up at 60s and returns a 504 to all of them —
#: which is how one slow database turns into every screen going blank at once. `db.py`
#: had exactly this bug in `pool.acquire()`; this is the same mistake in a lock.
LOCK_WAIT = 3.0

#: Seconds a single computation may take before the caller stops waiting for it. Well
#: under nginx's 60s so the ceiling is ours and is explainable, and above the slowest
#: healthy snapshot measured (2.5-6.2s while a pipeline was running) so an honestly busy
#: database is not called a failure.
SNAPSHOT_DEADLINE = 12.0

_snapshot_cache: dict[str | None, tuple[float, dict[str, Any]]] = {}
_snapshot_locks: dict[str | None, asyncio.Lock] = {}

# How long a tool call keeps lighting up its line. Long enough to notice at a 2s poll,
# short enough that the scene does not look permanently busy. The value goes straight
# through to queries.RECENT_CALLS as its $1.
FLASH_SECONDS = 4

# ★ The time window that stops a dead run from looking alive.
# How long a run may go without a heartbeat before it stops counting as in-flight.
#
# This was 120, on the stated reasoning that "runs heartbeat every few seconds and a
# stage takes under a minute". Both halves are false. The heartbeat is written by
# `_update_heartbeat` in motoro's orchestrator, and that call sits *inside the phase
# loop* — so a run heartbeats **once per phase, not on a timer**, and a phase that
# thinks for a long time is silent for exactly that long. Measured against core: 10
# gaps between consecutive steps exceed 120s, up to 500.3s, and every one of them
# belongs to a run that went on to complete normally. For those 380 seconds the run was
# missing from OPEN_RUNS, so `_build_scene` below drew a working stage as idle and the
# chain's live link stopped moving. That is the intermittent fault this window caused.
#
# 900 clears the measured worst case (500.3s) with 1.8x to spare. It still does the job
# it was introduced for: the abandoned runs sitting with `completed_at IS NULL` are
# 381,232s to 2,255,407s stale, so the window has a 425x margin before one of them could
# reappear as a character standing there "working" forever.
#
# The real repair is in motoro — heartbeat on a timer rather than per phase — after
# which this can come back down. Until then the viewer must not call a thinking agent
# dead. It goes to queries.OPEN_RUNS as its $1.
RUN_ALIVE_SECONDS = 900

# A task's stage order, used to tell a genuine retry from normal progress. `attempts`
# counts *claims*: a task that goes data -> ml -> interpret is claimed three times and
# has failed nothing. Reading it as a retry count reports a clean run as troubled.
# `_retried()` below uses this table to subtract that difference out.
STAGE_INDEX = {"data": 1, "ml": 2, "interpret": 3}


def _jsonb(value: Any, empty: Any) -> Any:
    # Safely unfold a JSON column the DB returned into a Python value.
    # Depending on the driver settings it may arrive already as a list/dict or as a
    # string, so both are accepted. If it cannot be read, *empty* (usually [] or {}) is
    # returned rather than an exception raised — one broken column must not take the
    # whole screen down with it.
    if value in (None, ""):
        return empty
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return empty


def _iso(dt: datetime | None) -> str | None:
    # Bring every time onto one shape, a **UTC ISO string.** The point is to stop the
    # frontend from having to guess a timezone. None passes through as None (which keeps
    # "no time yet" distinguishable from midnight).
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def _retried(task: dict[str, Any]) -> int:
    """Extra claims beyond what a healthy task of this stage would have had.

    For example, at the `ml` stage with a status other than 'ready' the healthy claim
    count is 2 (once at data, once at ml). attempts of 2 therefore means 0 retries. At
    'ready' the task has not been picked up for this stage yet, so 1 is taken off the
    expected figure.

    The two `max(..., 0)` calls keep the result from going negative — so that an unknown
    stage or data that does not line up cannot make it say something like "-1 retries".
    """
    expected = STAGE_INDEX.get(task["task_type"], 0) - (1 if task["status"] == "ready" else 0)
    return max((task.get("attempts") or 0) - max(expected, 0), 0)


# --------------------------------------------------------------------------- #
#  Reads
# --------------------------------------------------------------------------- #


async def list_runs() -> list[dict[str, Any]]:
    # The list of runs (run_tag). This shape — handing the inner `q` to `pools.guarded` —
    # is the common pattern of the whole file: **if the DB is down an empty list comes
    # back** (the fallback) instead of an exception, and the fact that it is down is
    # recorded in pools.health.
    # queries.RUNS orders newest first, so [0] is "the most recent run".
    async def q(conn: asyncpg.Connection) -> list[dict[str, Any]]:
        rows = await conn.fetch(queries.RUNS)
        return [
            {"run_tag": r["run_tag"], "tasks": r["tasks"], "done": r["done"],
             "first_seen": _iso(r["first_seen"]), "last_seen": _iso(r["last_seen"])}
            for r in rows
        ]

    return await pools.guarded("memstara", q, [])


async def _board(run_tag: str) -> list[dict[str, Any]]:
    # Every task of one board. Each card on screen is one dictionary here.
    # Why the DB rows are not passed straight through but **translated once here:** to
    # keep the screen from being tied directly to the DB's column names and types, and
    # to gather the interpretation in one place.
    async def q(conn: asyncpg.Connection) -> list[dict[str, Any]]:
        rows = await conn.fetch(queries.BOARD, run_tag)
        out = []
        for r in rows:
            t = {
                "task_id": r["task_id"], "run_tag": r["run_tag"], "trial": r["trial"],
                "perspective": r["perspective"], "status": r["status"],
                "task_type": r["task_type"], "attempts": r["attempts"],
                "hypothesis": r["hypothesis"],
                "columns": _jsonb(r["columns"], []),
                # Every JSON column goes through `_jsonb`. Naming the shape of the empty
                # value alongside it matters — [] where a list belongs, {} where a
                # dictionary does. Let None leak out to the screen and the frontend has
                # to defend against it every single time.
                "y_column": r["y_column"],
                "columns_used": _jsonb(r["columns_used"], []),
                "columns_missing": _jsonb(r["columns_missing"], []),
                "auc": r["auc"],
                "importance": _jsonb(r["feature_importance"], {}),
                "interpretation": r["interpretation"], "error": r["error"],
                "claimed_at": _iso(r["claimed_at"]), "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r["updated_at"]),
            }
            t["retried"] = _retried(t)
            # **Worked out and attached here.** If the screen judged attempts for
            # itself, different screens could reach different answers. The judgement is
            # kept in the backend, once.
            out.append(t)
        return out

    return await pools.guarded("memstara", q, [])


async def _results(run_tag: str) -> list[dict[str, Any]]:
    # The results table. It is **a different table** from the board and a different
    # place in the scene too. The board holds what is in progress, this table what has
    # been settled as found.
    async def q(conn: asyncpg.Connection) -> list[dict[str, Any]]:
        rows = await conn.fetch(queries.RESULTS, run_tag)
        return [
            {"result_id": r["result_id"], "task_id": r["task_id"], "trial": r["trial"],
             "perspective": r["perspective"], "hypothesis": r["hypothesis"],
             "columns_used": _jsonb(r["columns_used"], []),
             "columns_missing": _jsonb(r["columns_missing"], []),
             # Named `importance` to match the board's field of the same meaning
             # (see `_board` above), so a panel can read either without a second shape.
             "importance": _jsonb(r["feature_importance"], {}),
             "okf_concept_ids": _jsonb(r["okf_concept_ids"], []),
             "y_column": r["y_column"], "auc": r["auc"],
             # The engine that produced `importance`, and it travels with it because the
             # two engines do not measure the same thing — gain for the boosted trees,
             # mean AUC drop under permutation for the forest. Passed through exactly as
             # stored, empty string included: `''` is *not recorded*, which is what every
             # result from before 2026-09-08 says, and turning it into "unknown" here
             # would put a word in the database's mouth on the screen's behalf.
             "model": r["model"],
             "interpretation": r["interpretation"], "created_at": _iso(r["created_at"])}
            for r in rows
        ]

    return await pools.guarded("memstara", q, [])


def _trace_groups(trace: Any, asked: list[str], used: list[str]) -> list[dict[str, Any]]:
    """Flatten a `match_trace` into one group per concept the matcher was asked about.

    The stored trace is a list of calls, each `{"tool", "arguments", "result"}`, and the
    two matcher tools answer in two different shapes: `match_concepts` returns
    `{"results": [group, ...]}` and `match_concept` returns a single group. Both are
    unwrapped to the same thing here rather than on screen, for the reason `_board` gives
    — one translation, in one place, or two panels reach two answers.

    Each candidate is marked against the task's own column lists:

      `chosen`  the agent asked for this column after reading the group. Judged against
                `columns` (what was asked for) and **not** `columns_used` (what the
                cohort turned out to have), because a candidate the agent picked and the
                data stage could not find is still a candidate the agent picked. Marking
                it unchosen would blame the agent for the cohort.
      `present` it also survived into the model.

    A group with no chosen candidate is normal and is not a bug in this function.
    `harvest_match_trace` files the turn's whole matcher record on **every** task the
    same turn created (`src/memstara/pipeline/board.py:913-921`), so one result's trace
    legitimately carries concepts matched for a sibling task. Nothing here hides that: the
    groups are returned in call order, none is dropped, and none is merged with another
    of the same name — two calls for one concept with different `top_k` are two different
    answers and collapsing them would invent a third.
    """
    out: list[dict[str, Any]] = []
    asked_set, used_set = set(asked), set(used)
    for call in _jsonb(trace, []):
        if not isinstance(call, dict):
            continue
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        groups = result.get("results") if isinstance(result.get("results"), list) else [result]
        for g in groups:
            if not isinstance(g, dict) or "concept" not in g:
                continue
            candidates = g.get("candidates")
            out.append({
                "tool": call.get("tool") or "",
                "concept": g.get("concept") or "",
                # The matcher's own explanation for an empty group — "nothing was close
                # enough" and "a code this cohort does not carry" are different findings
                # and only one of them is worth rewording for. Dropping it would leave an
                # empty group looking like a failed call.
                "note": g.get("note") or "",
                "candidates": [
                    {"column": c.get("feature_name") or "",
                     "feature_type": c.get("feature_type") or "",
                     "score": c.get("similarity_score"),
                     "chosen": (c.get("feature_name") or "") in asked_set,
                     "present": (c.get("feature_name") or "") in used_set}
                    for c in (candidates if isinstance(candidates, list) else [])
                    if isinstance(c, dict)
                ],
            })
    return out


async def result_detail(result_id: int) -> dict[str, Any] | None:
    """One result with its matcher record, or None when there is no such row.

    None means "the query ran and found nothing" *or* "the query could not run" —
    `guarded` returns the fallback for both. The caller separates them by looking at
    `pools.health`, because a 404 for a database that is down tells a person the result
    does not exist, which is a different and wrong thing.
    """
    async def q(conn: asyncpg.Connection) -> dict[str, Any] | None:
        r = await conn.fetchrow(queries.RESULT_ONE, result_id)
        if r is None:
            return None
        asked = _jsonb(r["columns"], [])
        used = _jsonb(r["columns_used"], [])
        return {
            "result_id": r["result_id"], "task_id": r["task_id"], "run_tag": r["run_tag"],
            "trial": r["trial"], "perspective": r["perspective"],
            "hypothesis": r["hypothesis"],
            "columns": asked, "columns_used": used,
            "columns_missing": _jsonb(r["columns_missing"], []),
            # Named `importance` to match `_results` and `_board`, so the same panel can
            # read a result from either place without a second shape.
            "importance": _jsonb(r["feature_importance"], {}),
            "okf_concept_ids": _jsonb(r["okf_concept_ids"], []),
            "y_column": r["y_column"], "auc": r["auc"],
            # Same field and same reasoning as `_results` above: the scale the numbers in
            # `importance` are on. `''` means it was never written down.
            "model": r["model"],
            "interpretation": r["interpretation"], "created_at": _iso(r["created_at"]),
            "match_trace": _trace_groups(r["match_trace"], asked, used),
            # `match_trace_calls` is the number of calls **stored**, before flattening,
            # so a trace that unwraps to nothing can still be told apart from a task the
            # matcher was never called for. Those need opposite fixes.
            "match_trace_calls": len(_jsonb(r["match_trace"], [])),
        }

    return await pools.guarded("memstara", q, None)


async def _core_facts() -> dict[str, Any]:
    """Everything from core's database, in one connection acquisition.

    Why seven queries but not seven calls to `guarded`:
    - there is no acquiring and releasing a connection seven times over, and
    - above all **the seven results are the DB state of one same moment,** so they cannot
      contradict each other. (One query never sees before an update while another sees
      after it.)
    - and when it fails, **all seven fail together:** a half-populated scene never arises.

    One connection is also what makes the temp table below possible, and that is now the
    load-bearing reason rather than a side benefit: a temp table lives on the session, so
    the five queries that read it have to be on the connection that built it.
    """

    async def q(conn: asyncpg.Connection) -> dict[str, Any]:
        # Build `flat` once. Five of the seven queries below read it, and each of them
        # used to derive it again for itself — the same scan of `run_steps` five times,
        # ~0.9s apiece, so a snapshot cost ~6s against a 2s poll and the polls piled up.
        # Read-only accounts may still do this: CREATE TEMPORARY is granted to PUBLIC by
        # default, and it was checked on this database with this account rather than
        # assumed.
        await conn.execute(queries.FLAT_TEMP_TABLE)
        return {
            "totals": [dict(r) for r in await conn.fetch(queries.AGENT_TOTALS)],
            "open": [dict(r) for r in await conn.fetch(queries.OPEN_RUNS,
                                                       str(RUN_ALIVE_SECONDS))],
            "access": [dict(r) for r in await conn.fetch(queries.ACCESS)],
            "touches": [dict(r) for r in await conn.fetch(queries.TASK_TOUCHES,
                                                          str(RUN_ALIVE_SECONDS))],
            "last_call": [dict(r) for r in await conn.fetch(queries.LAST_CALL)],
            "roster": [dict(r) for r in await conn.fetch(queries.LAST_ROSTER,
                                                         str(RUN_ALIVE_SECONDS))],
            "recent": [dict(r) for r in await conn.fetch(queries.RECENT_CALLS,
                                                        str(FLASH_SECONDS))],
            "feed": [dict(r) for r in await conn.fetch(queries.FEED)],
        }

    # The empty shell to return when core is down. It has to carry **the same eight keys**
    # as above. Leave even one out and a KeyError comes up below, turning "core is down"
    # into "the viewer crashed" — which makes everything guarded holds off pointless.
    empty: dict[str, Any] = {"totals": [], "open": [], "access": [], "touches": [],
                             "last_call": [], "roster": [], "recent": [], "feed": []}
    return await pools.guarded("core", q, empty)


# --------------------------------------------------------------------------- #
#  The scene
# --------------------------------------------------------------------------- #


def _carrying(touches: list[dict[str, Any]]) -> dict[str, int]:
    """Which agent **run** currently holds which task, replayed from the board windows.

    A `claim_task` puts a task in an agent's hands; the matching `submit_result` takes
    it back. Replaying in time order leaves exactly what is still held — the board's own
    `in_progress` rows say a task is held but not by whom, and "by whom" is the thing
    the scene needs to draw.

    **Keyed by run id, not by stage.** It was keyed by stage until 2026-09-08, on the
    stated assumption that one stage holds one thing at a time. That is false the moment
    `--data-agents 2` is passed: two workers of one stage claim two tasks, the second
    claim overwrote the first here, and the floor showed one card where there were two.
    A *run* really does hold one task at a time — `call_agent` is given one task to do
    (`src/memstara/pipeline/board.py:1591`) — so the assumption is true at this key and
    was only ever approximately true at the old one.
    """
    held: dict[str, int] = {}
    for t in touches:
        # The stage is not the key any more, but it is still the filter: only board-path
        # runs are drawn, and a supervisor-path claim must not put a card in anyone's
        # hand.
        if stores.stage_of_agent(t["name"]) is None or not t.get("task_id"):
            continue
        run_id = str(t["run_id"])
        task_id = int(t["task_id"])
        if t["tool"] == "claim_task":
            held[run_id] = task_id
        elif t["tool"] == "submit_result":
            # Cleared **by task**, across runs, rather than "clear whatever this run
            # holds". Both halves of that matter and they are separate points.
            #
            # By task, because an old submit_result arriving late must not drop the new
            # task the run has just picked up. That was already the rule when this was
            # keyed by stage and it is unchanged.
            #
            # Across runs, because a task reclaimed after a stall is claimed a second
            # time by a different run while the run that stalled is still, in this
            # replay, holding it. Keyed by run, only the submitter's own entry would go
            # and the stalled worker would stand there holding a card that had been
            # handed in — for the whole of RUN_ALIVE_SECONDS, since nothing else expires
            # it. The stage-keyed version got this right by accident, both runs being
            # one key; here it has to be said.
            for holder in [r for r, held_id in held.items() if held_id == task_id]:
                held.pop(holder, None)
    return held


def _worker_names(touches: list[dict[str, Any]]) -> dict[str, str]:
    """run id -> the name that run called itself, where it gave one.

    `--hypothesis-agents 3` starts three calls against one agent, so the three runs share
    an agent name and the database has nothing else to tell them apart by. The name they
    were each given in their instructions — `hypothesis#2` — is written down in exactly
    one place: the `worker=` argument they pass when they ask for work
    (`src/memstara/pipeline/board.py:1403, 1596`).

    Most calls in a run do not carry it (see `queries.TASK_TOUCHES`), so this takes the
    first one that does and keeps it. A run with no named call at all is absent from the
    map and gets drawn under a slot number instead, which is a worse label but not a
    wrong one.

    Called on **both** `touches` and `roster`, which carry the same two columns and differ
    only in what their window is anchored on. Nothing here has to know which it was given.
    """
    names: dict[str, str] = {}
    for t in touches:
        worker = (t.get("worker") or "").strip()
        if worker:
            names.setdefault(str(t["run_id"]), worker)
    return names


def _slot_key(run_id: str, worker: str) -> tuple[int, int, str, str]:
    """Order the workers of one character so they do not swap places between polls.

    The screen re-reads this every 2 seconds. Order the figures by anything the database
    is free to return in a different order and the characters shuffle along the floor
    while nothing has happened.

    Worker names sort first and numerically: `data#10` after `data#2`, which plain string
    order gets backwards. A run with no name sorts last, by run id, which is arbitrary but
    fixed.
    """
    tail = worker.rsplit("#", 1)[-1] if worker else ""
    if tail.isdigit():
        return (0, int(tail), worker, run_id)
    return (1, 0, worker, run_id)


def _recency(run_id: str | None, last: dict[str, Any] | None,
             open_by_run: dict[str, dict[str, Any]]) -> tuple[int, Any, str]:
    """How recently a run did something, for picking which run a folded figure shows.

    A station that is not in `stores.SPLITTABLE` draws one figure however many runs stand
    at it, and this is what decides which of them the figure describes. The answer is the
    run that **called a tool most recently**, falling back to when the run opened for a
    run that has not called anything yet.

    That is not an arbitrary tie-break. The rest of the card — `state`, `at`, `carrying`,
    `last_tool` — all answer "what is this character doing right now", so the run they
    describe has to be the one that is doing it. Picking the oldest, or the first the
    database happened to return, would draw a figure standing still at a station whose
    other worker is the one actually moving.

    Returns:
        A sort key, largest = most recent. The leading flag keeps a run with no timestamp
        at all comparable with one that has a real datetime, and sorts it last.
    """
    if last is not None:
        return (1, last["started_at"], run_id or "")
    run = open_by_run.get(run_id or "")
    if run is not None:
        return (1, run["created_at"], run_id or "")
    return (0, 0, run_id or "")


def _members_of_each_character() -> dict[str, list[str]]:
    # Which real stages each character on the floor stands for.
    #
    # Five stages come out of the pipeline and five characters stand on the floor, so
    # for anything run since 2026-09-07 this is an identity. It is not dead code: the
    # retired `curator` stage still reaches the floor through `stores.DRAWN_AS`, which
    # is the only route by which a run recorded against `memstara-board-curator` gets
    # drawn at all. See `stores.LEGACY_BOARD_AGENT_NAMES`.
    #
    # Read off `BOARD_AGENT_NAMES_ANY` rather than written out, so a stage added to the
    # pipeline arrives here by itself instead of going missing until somebody notices —
    # and a stage *retired* from it stays, which `BOARD_TOOLS` would not give us.
    members: dict[str, list[str]] = {character: [] for character in stores.HOME}
    for stage in stores.BOARD_AGENT_NAMES_ANY:
        members.setdefault(stores.drawn_as(stage), []).append(stage)
    return members


def _build_scene(core: dict[str, Any], core_up: bool) -> dict[str, Any]:
    # ★ Assembles the scene: the characters' **state, position and what they are
    # holding,** and the lines that will flash.
    #
    # **A character is one worker, not one stage.** Until 2026-09-08 this walked
    # `stores.HOME` and produced exactly five figures, so `--hypothesis-agents 3` — which
    # the pipeline has supported since A-11 — drew one hypothesis character while three
    # were running, and the two it dropped were invisible rather than merged: their runs,
    # their tool calls and the cards in their hands were simply not on the screen. The
    # floor plan is the thing people watch to see whether parallelism is doing anything,
    # and it was the one screen that could not show it.
    #
    # `stores.HOME` is still the list of *characters* and still has five entries — the
    # floor has five stations and each stage rests at its own. What changed is that a
    # station can now have more than one figure standing at it.
    #
    # **And only one station may.** The first version of this split all five, which is the
    # opposite of what the meeting decided and of what A-24 was written to do: the user
    # chooses how many hypothesis agents to run and sees them, and everything else is one
    # character however many workers are behind it (`stores.SPLITTABLE`). The count is not
    # hidden — it rides on the card as `running`.
    #
    # First the rows that came from core are indexed by **run**. `stores.stage_of_agent`
    # is what does the filtering — only **board-path characters** appear in the scene, so
    # supervisor-path agents are quietly dropped here.
    # (The access map is the opposite: it has to count both. See _access.)
    #
    # A function rather than `name in stores.AGENT_BY_NAME`, and that is not a style
    # preference: since `A-32` a hypothesis agent may be named for the standard it
    # carries, so the set of board agent names is open and the dict holds only the bases.
    # A membership test would drop every run made under a playbook — no figure, no error.
    open_by_run = {
        str(r["run_id"]): r
        for r in core["open"] if stores.stage_of_agent(r["name"]) is not None
    }
    last_by_run = {
        str(r["run_id"]): r
        for r in core["last_call"] if stores.stage_of_agent(r["name"]) is not None
    }
    held = _carrying(core["touches"])
    # **Two sources, and the roster is the one that outlives the run.** `touches` is
    # windowed on `now()`, so fifteen minutes after a run it is empty and every worker of
    # it is nameless; `roster` asks the same question anchored on the run's own last call
    # (`queries.LAST_ROSTER`) and so still names them. Merged rather than chosen between:
    # while a run is live the two agree exactly, and `touches` is put second so anything
    # happening this instant wins a disagreement.
    workers = _worker_names(core["roster"]) | _worker_names(core["touches"])

    # Which stage a run belongs to. All three sources are read because they cover
    # different runs: `open` has only what is running, `last_call` only what has made a
    # tool call, and `touches` is the one that still names a run which has finished but
    # is holding a card — the "moving" state below exists for exactly that run, and
    # without this line it would have no stage and no figure.
    stage_by_run: dict[str, str] = {}
    # …and which **agent** it ran as, which is a different question since `A-32`. The stage
    # is `hypothesis` for every hypothesis worker; the agent name is what carries the
    # standard it was provisioned with (`memstara-board-hypothesis-cardiometabolic`), and
    # it is the only place on this path that standard survives. `stage_by_run` cannot
    # answer it — resolving the stage is exactly the step that takes the suffix off.
    agent_by_run: dict[str, str] = {}
    # …and the same question asked of a **station** rather than a run, which is the only
    # form that survives the run ending. A figure with nothing open has no `run_id` to
    # look up, so until 2026-09-09 its standard came back `""` and the card read *no
    # standard* the moment the work finished — the one reading the field exists to rule
    # out. The standard belongs to the agent, and the agent does not stop having been
    # provisioned under it because its run closed.
    #
    # **The most recent agent, not the only one.** A set of every name ever seen at the
    # station was tried first and answered nothing on this machine: the database holds
    # every run since August, so `hypothesis` had both `memstara-board-hypothesis` and
    # `memstara-board-hypothesis-ml_reporting` in it and a rule of "use it when there is
    # exactly one" fell through on the very case it was written for. Recency is the
    # question actually being asked — *what was this station last doing* — and
    # `last_call.started_at` is the one timestamp that answers it for a run that has
    # closed. Built from `last_call` alone because it is the only one of the three that
    # carries that column.
    #
    # While two workers run at once under two standards this is not consulted at all:
    # each has an open run and `agent_by_run` answers per figure. It is only what an
    # **idle** figure falls back to, and there the station has one past, not two.
    agents_at: dict[str, tuple[Any, str]] = {}
    for r in core["last_call"]:
        stage = stores.stage_of_agent(r["name"])
        if stage is None:
            continue
        character = stores.drawn_as(stage)
        seen = agents_at.get(character)
        if seen is None or r["started_at"] > seen[0]:
            agents_at[character] = (r["started_at"], r["name"])
    for rows in (core["open"], core["last_call"], core["touches"], core["roster"]):
        for r in rows:
            stage = stores.stage_of_agent(r["name"])
            if stage is not None and r.get("run_id") is not None:
                stage_by_run[str(r["run_id"])] = stage
                agent_by_run[str(r["run_id"])] = r["name"]

    # The three ingredients are now gathered: the runs going right now (open), the last
    # call per run (last), and what is in each run's hand (held). The loop below combines
    # the three to settle one figure's state.
    members = _members_of_each_character()

    # Every run that has a figure of its own: it is running, or it is holding a card and
    # has not handed it in. Grouped by the character whose station it stands at.
    live: dict[str, list[str]] = {character: [] for character in stores.HOME}
    for run_id in set(open_by_run) | set(held):
        stage = stage_by_run.get(run_id)
        if stage is not None:
            live.setdefault(stores.drawn_as(stage), []).append(run_id)

    # **A splittable station keeps a figure for every worker it has, not only for the ones
    # mid-call.** The two lines above are "what is happening this instant", and for the
    # four folded stations that is the whole question. For `hypothesis` it is not.
    #
    # Three workers propose their questions roughly together and finish roughly together,
    # so with the rule above alone the column held three cards for **two minutes and
    # twenty-seven seconds** of a run that lasted twenty (measured, 2026-09-09 07:03:01 to
    # 07:05:28) and one card for the rest of it. Anyone who looked before or after saw a
    # pipeline with a single hypothesis agent, which is the picture the stack was built to
    # replace — and it was not wrong about this instant, it was answering a different
    # question from the one being asked. The number of hypothesis agents is a property of
    # the **run**, chosen on the form before it started; it does not drop to one because
    # the workers happen to be between calls.
    #
    # A worker is known here by having named itself to the board, and `workers` above now
    # reads that from two queries rather than one. That is the half of this fix made on
    # **2026-09-09 in the afternoon**, and the reason is that the paragraph above was still
    # true for fifteen minutes and false afterwards: `TASK_TOUCHES` is windowed on `now()`,
    # so the stack survived the run by exactly `RUN_ALIVE_SECONDS` and then folded back to
    # one card. Measured — the 07:31 run's three cards were still there at 07:44:05 and the
    # snapshot read at 08:02:31 had one, `idle`. The paragraph above says why that is the
    # wrong answer, and it is no less wrong at minute sixteen than at minute two.
    #
    # `queries.LAST_ROSTER` asks the same question with the window anchored on the run's own
    # newest call instead of on the clock, so the cohort is grouped the same way and simply
    # does not expire. **Two runs of the same station less than 900s apart will show the
    # workers of both**, which is unchanged, and is the honest answer for a panel whose own
    # header says `All runs`.
    #
    # Only splittable stations. Adding a resting figure at a folded station would put a
    # second `data` character on the floor that the meeting asked to be drawn once.
    for run_id, worker in workers.items():
        if not worker:
            continue
        stage = stage_by_run.get(run_id)
        if stage is None or stage not in stores.SPLITTABLE:
            continue
        character = stores.drawn_as(stage)
        if run_id not in live[character]:
            live[character].append(run_id)

    agents = []
    # run id -> the id of the figure drawn for it, filled in as the figures are built.
    # The flashes below are keyed by run and need it.
    figure_of_run: dict[str, str] = {}
    # character -> the id of its first figure, for a call by a run that has no figure.
    first_figure: dict[str, str] = {}

    for character in stores.HOME:
        # The character's own name, and only its own: a merged character is labelled for
        # the stage it is drawn as, not for every stage folded into it. The loop walks
        # `HOME`, which has five keys, so a folded-away stage is never looked up here —
        # `AGENT_LABELS` still holds the retired `curator` because
        # `check_definitions.py:154` requires a label for every stage the viewer knows,
        # not because anything on screen reads it.
        label = stores.AGENT_LABELS.get(character, character)
        mine = members.get(character, [character])

        runs = sorted(live.get(character, []),
                      key=lambda rid: _slot_key(rid, workers.get(rid, "")))

        # One entry per figure. A character with nothing running still puts one figure
        # down — resting at home is a state, not an absence — and that entry carries no
        # run at all.
        instances: list[tuple[str | None, dict[str, Any] | None,
                              dict[str, Any] | None, str | None]] = []
        for run_id in runs:
            instances.append((run_id, open_by_run.get(run_id), last_by_run.get(run_id),
                              stage_by_run.get(run_id)))
        if not instances:
            # Idle. `last` is then the most recent call across every run of every stage
            # this character stands for — what the character last did, rather than what
            # any one of its runs last did. Both members can have a last call: on a
            # pre-2026-09-07 run the curator and the hypothesis stage were two agents
            # drawn as one figure.
            calls = [(r, stores.stage_of_agent(r["name"])) for r in core["last_call"]
                     if stores.stage_of_agent(r["name"]) in mine]
            last, last_stage = (max(calls, key=lambda pair: pair[0]["started_at"])
                                if calls else (None, None))
            instances.append((None, None, last, last_stage))

        # **Only a splittable station gets a figure per worker.** Everything else keeps one
        # figure however many runs it has, and the one it keeps is the run that called a
        # tool most recently — the same "what is happening now" the rest of the card is
        # built on (`state`, `at`, `carrying` all describe this instant, so the run they
        # describe has to be the current one). A run folded away here still reaches the
        # screen: its flash falls back to `first_figure[character]` below, which is this
        # figure, so the station lights up for every worker's call and not just one's.
        folded = character not in stores.SPLITTABLE and len(instances) > 1
        if folded:
            instances = [max(instances, key=lambda inst: _recency(inst[0], inst[2],
                                                                  open_by_run))]

        # How many runs **each figure** stands for. One apiece where the station splits,
        # all of them where it folds, and zero for a figure that is resting. This is the
        # reason folding is not the same as hiding: the meeting asked for the data agent
        # to be *drawn* once, not for the second one's existence to be taken off the
        # screen, and without a count `--data-agents 2` would look exactly like
        # `--data-agents 1` with nothing anywhere to say otherwise.
        stands_for = [len(runs)] if folded else [
            1 if run_id is not None and (run_id in open_by_run or run_id in held) else 0
            for run_id, *_ in instances
        ]

        # The id each figure is drawn under, and it is the id every other part of the
        # screen keys off: React Flow nodes, the flash edges' `source`, the colour table.
        #
        # **A character with one figure keeps the stage's own id.** That is deliberate
        # and it is what makes this change invisible to a default run: with every
        # `--*-agents` at 1 the scene is byte-identical to what it was before, so nothing
        # that reads `hypothesis` had to be found and changed. The worker name only
        # becomes the id when there is a second worker for it to be told apart from.
        ids: list[str] = []
        for run_id, _run, _last, _stage in instances:
            if len(instances) == 1:
                ids.append(character)
            else:
                # The fallback names the **run**, never a worker number. It used to be
                # `f"{character}#{slot + 1}"`, and that put an invented name into the
                # workers' own namespace: real workers are 0-indexed (`wid =
                # f"hypothesis#{i}"`, `src/memstara/pipeline/board.py:1403`), so a
                # three-worker run drew `hypothesis#0`, `hypothesis#2`, `hypothesis#3` in
                # the seconds before the third worker reached its `claim_question` — one
                # id naming a worker that does not exist, and `hypothesis#1` nowhere,
                # while `hypothesis#1` was in fact running. Seen on a live run on
                # 2026-09-08. A worker has no name here only until it makes its first
                # call; the run id is what genuinely tells these apart in the meantime,
                # and it cannot be mistaken for something the board wrote.
                ids.append(workers.get(run_id or "") or f"{character}:run{run_id}")
        # Two runs can genuinely report the same worker name: `data#1` is what the first
        # worker of every wave is called, so a task reclaimed after a stall is claimed by
        # a `data#1` in a later run while the run that stalled is still holding one. Node
        # ids have to be unique or React Flow draws one figure where there are two, and
        # silently — so uniqueness is made here rather than assumed.
        seen: set[str] = set()
        for k, ident in enumerate(ids):
            base, n = ident, 1
            while ident in seen:
                n += 1
                ident = f"{base}/{n}"
            seen.add(ident)
            ids[k] = ident

        first_figure[character] = ids[0]
        for slot, (run_id, run, last, run_stage) in enumerate(instances):
            if run_id is not None:
                figure_of_run[run_id] = ids[slot]
            carrying = held.get(run_id) if run_id is not None else None

            if not core_up:
                # Not "idle" — unknown. Saying idle would be an assertion we cannot make.
                # With the core DB unreadable, saying "this agent is doing nothing" is
                # making **an assertion that cannot be made.** Not knowing has to be
                # reported as not knowing, or the screen cannot be trusted.
                state, at = "unknown", None
            elif run is not None:
                state = "working"
                at = stores.store_of(last["tool"]) if last else None
            elif carrying is not None:
                # Holds a task but no run is open: it picked the task up and its run
                # ended. It cannot be called dead and it cannot be called working, so it
                # is drawn as **"moving"** and stood in front of the board.
                #
                # The order these states are decided in is the priority order:
                # unknown -> working -> moving -> idle.
                state, at = "moving", "board"
            else:
                # No run going and nothing in hand means it really is idle.
                state, at = "idle", None

            # The agent this figure is: the one its own run ran as while it has one, and
            # otherwise the one this station most recently ran as. The second half is what
            # keeps the standard on the card after the work is done — see `agents_at`.
            # Empty only for a station that has never made a call, which is the one case
            # where "no standard" is the true answer.
            ran_as = agent_by_run.get(run_id or "") or agents_at.get(character, (None, ""))[1]

            # `name` is the agent that produced the state just settled, not the
            # character's own — so replaying a pre-2026-09-07 run, the merged character
            # says `memstara-board-curator` while that agent is the one running, and
            # which of the two is working stays readable from the card. It is the same
            # for every worker of one stage, which is exactly why it cannot be what the
            # figures are told apart by.
            agents.append({
                "id": ids[slot],
                # The station this figure stands at, and the key for everything indexed
                # by stage — the colour table and the pictogram, both of which are
                # exhaustive over the five and would return undefined for `hypothesis#2`.
                # `id` says which figure; `stage` says which of the five it is one of.
                "stage": character,
                "label": label,
                # The name this run called itself, or null when it never said. Drawn as a
                # second line under the label, so two figures at one station are told
                # apart by the name the board also records in `claimed_by` rather than by
                # their position on the floor.
                "worker": workers.get(run_id or "") or None,
                # Which of its character's figures this is, from 0. The floor plan offsets
                # by it so two workers do not stand on the same spot; a character with one
                # figure is always slot 0 and therefore exactly where it always was.
                "slot": slot,
                # How many runs **this figure** stands for: 1 where the station splits,
                # the whole count where it folds, 0 while it rests. The screen draws it as
                # a badge only when it is more than one, which is exactly the case the
                # fold would otherwise have made invisible.
                "running": stands_for[slot],
                # The agent this run actually ran as, **including its playbook suffix**,
                # falling back to the stage's canonical name for a figure with no run
                # behind it. It used to be the canonical name always, and that was a
                # silent mismatch as soon as `A-32` made the name open-ended: the cost
                # table lists a suffixed agent under its own name (`reported_as` keeps the
                # suffix on purpose), and `AgentsTab` highlights the row where
                # `selected === r.name`, so clicking a figure running under a standard
                # highlighted nothing at all — no error, just a table that did not react.
                "name": (ran_as
                         or stores.BOARD_AGENT_NAMES_ANY.get(run_stage or character,
                                                             character)),
                # The behavioural standard this figure is running under, or `""` for the
                # prompt as written. Its own field rather than part of `label`, and that
                # is the point of it: `label` is the **station's** — every figure standing
                # at one shares it, and it is what the colour and pictogram tables are
                # keyed beside — while the standard belongs to the worker. Three agents
                # under three standards were three figures all reading `Hypothesis`.
                #
                # `""` is drawn as *no standard*, not left blank. "The prompt as written"
                # and "the suffix was dropped on the way here" look identical when the
                # answer is empty, and those two need opposite fixes.
                "playbook": stores.playbook_of(ran_as),
                "state": state,
                "at": at,
                "home": stores.HOME[character],
                "carrying": carrying,
                "run_id": str(run["run_id"]) if run else None,
                "since": _iso(run["created_at"]) if run else None,
                "last_tool": None if not last else {
                    "server": last["server"], "tool": last["tool"],
                    "store": stores.store_of(last["tool"]), "at": _iso(last["started_at"]),
                },
                "windows": sorted({t for s in mine
                                   for t in stores.STAGE_WINDOWS.get(s, set())}),
                # The list of windows this character can open — the **union** over the
                # stages it stands for, because a merged character really can open all of
                # them. A set has no order, so left alone the order shifts on every
                # refresh and the screen flickers. Hence the sort.
                #
                # `STAGE_WINDOWS` and not `BOARD_TOOLS`: the latter is what one *call* may
                # hold, and the hypothesis agent has two calls with two different lists
                # (`stores.STAGE_WINDOWS`). Reading BOARD_TOOLS here would drop
                # `read_questions`, `read_results` and `propose_questions` from the card
                # while `BOARD_WINDOWS` still names Hypothesis as their holder — two
                # screens disagreeing, with neither saying so.
            })

    # flashes below: the calls of the last few seconds = **the lines that will flash**
    # on screen.
    # `place` is settled by the **tool**, not the server (stores.store_of) — because the
    # one board server is responsible for two places, the board and the results table.
    # Here too only board-path characters are kept. A line for a character that is not
    # in the scene has nowhere to be drawn — which is why the figure is looked up here as
    # well as built above. `ScenePanel.tsx` builds each edge as `source: agent-${agent}`
    # against the node ids it got from `agents`, so a flash naming anything else would
    # name a node that does not exist and the line would simply not appear.
    #
    # The run is tried first and the character's first figure is the fallback. Both arms
    # are load-bearing: with several workers at one station there is no figure called
    # `hypothesis` for a stage-keyed flash to reach, and a run that has just finished has
    # no figure of its own for a run-keyed one — its last call belongs on the figure
    # resting at its station, which is what the fallback returns.
    flashes = []
    for r in core["recent"]:
        if stores.stage_of_agent(r["name"]) is None:
            continue
        character = stores.drawn_as(stores.stage_of_agent(r["name"]))
        agent_id = figure_of_run.get(str(r["run_id"])) or first_figure.get(character)
        if agent_id is None:
            continue
        flashes.append({
            "agent": agent_id,
            "place": stores.store_of(r["tool"]),
            "tool": r["tool"], "server": r["server"], "at": _iso(r["started_at"]),
        })

    return {"places": stores.PLACES, "agents": agents, "flashes": flashes}


def _agent_totals(core: dict[str, Any]) -> list[dict[str, Any]]:
    # The running totals per agent (run count, tokens, cost). Unlike the scene, this
    # **shows both paths.** That is why it uses `stage_of_agent_any` rather than
    # `stage_of_agent`, and marks with `path` whether it is the board path or the
    # supervisor path. Two hypothesis agents carrying two standards stay two rows here,
    # labelled `Hypothesis · <standard>` apiece — folding them would make "what did each
    # standard cost" a question the screen cannot answer.
    # Why the `int()` and `float()` wrappers: PostgreSQL's numeric arrives in Python as
    # a Decimal, which left as it is trips up JSON serialisation.
    # `r["cost"] or 0` handles NULL and 0 together.
    #
    # Rows are keyed by the name they are **reported under** (stores.reported_as), which
    # folds the curator into the hypothesis agent. Two source rows can therefore land on
    # one key, and when they do they are **added**, not overwritten: run counts, token
    # counts and cost all stay equal to the unfolded database. That is the property worth
    # protecting here — a fold that dropped a row would take real spend off the total and
    # no screen would show it.
    merged: dict[str, dict[str, Any]] = {}
    for r in core["totals"]:
        name = stores.reported_as(r["name"])
        runs = r["runs"]
        row = merged.get(name)
        if row is None:
            row = merged[name] = {
                "name": name,
                "id": stores.stage_of_agent_any(name),
                "path": stores.path_of_agent(name),
                "label": stores.label_of(name),
                "runs": 0, "completed": 0, "open_runs": 0,
                "tokens": {"prompt": 0, "completion": 0},
                "cost": 0.0,
                # Kept as a running (iterations, runs) pair and divided at the end: an
                # average of two averages is not the average, and the cheap version would
                # be quietly wrong by a little, which is the worst amount.
                "_iterations": 0.0, "_iteration_runs": 0,
                "last_run_at": None,
            }
        row["runs"] += runs
        row["completed"] += r["completed"]
        row["open_runs"] += r["open_runs"]
        row["tokens"]["prompt"] += int(r["prompt_tokens"])
        row["tokens"]["completion"] += int(r["completion_tokens"])
        row["cost"] += float(r["cost"] or 0)
        if r["avg_iterations"]:
            row["_iterations"] += float(r["avg_iterations"]) * runs
            row["_iteration_runs"] += runs
        at = _iso(r["last_run_at"])
        # The freshest of the folded rows: "when did this agent last run" is a question
        # about the merged agent, so the later of the two is the answer.
        if at and (row["last_run_at"] is None or at > row["last_run_at"]):
            row["last_run_at"] = at

    out = []
    for row in merged.values():
        runs = row.pop("_iteration_runs")
        iterations = row.pop("_iterations")
        row["avg_iterations"] = round(iterations / runs, 2) if runs else None
        out.append(row)
    return out


def _access(core: dict[str, Any]) -> dict[str, Any]:
    # Both driving paths, not just the board one. The supervisor agents did most of the
    # tool calls historically; filtering them out made this map understate reality
    # roughly fivefold while still looking internally consistent — exactly the kind of
    # error that is hard to notice.
    #
    # Filtering by server would let the hypothesis stage pick up work that is not its
    # own. So the store is settled **one tool at a time** (stores.store_of).
    #
    # The agent is the one the row is **reported under** (stores.reported_as), so the
    # curator's calls arrive here as the hypothesis agent's. That makes duplicate keys
    # possible where there were none before — the curator and the hypothesis agent both
    # call `okf_read` — so the rows are **re-aggregated**, not merely relabelled. Skip
    # that and the map draws two "Hypothesis / okf_read" lines that a reader has to add up
    # by eye, and `windows` below would still be right, which is what makes it easy to
    # miss.
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in core["access"]:
        if stores.stage_of_agent_any(r["name"]) is None:
            continue
        name = stores.reported_as(r["name"])
        key = (name, r["server"], r["tool"])
        row = merged.get(key)
        if row is None:
            row = merged[key] = {
                "agent": stores.stage_of_agent_any(name) or name,
                "agent_label": stores.label_of(name),
                "name": name,
                "path": stores.path_of_agent(name),
                "server": r["server"], "tool": r["tool"],
                "store": stores.store_of(r["tool"]),
                "calls": 0, "last_at": None,
            }
        row["calls"] += r["calls"]
        at = _iso(r["last_at"])
        if at and (row["last_at"] is None or at > row["last_at"]):
            row["last_at"] = at
    rows = list(merged.values())

    called = {r["tool"] for r in rows}
    # The set of tools that were actually called at least once.
    # Below, **every window** of the board server is walked through and each one gets
    # its call count and a "has an agent ever called it" attached.
    # `read_board` (the driving script's business) and `count_waiting` (nobody uses it)
    # staying at 0 is **the correct picture.** It is not missing data — verify.py checks
    # these zeros for real.
    windows = [
        {**w, "calls": sum(r["calls"] for r in rows if r["tool"] == w["tool"]),
         "called_by_agent": w["tool"] in called}
        for w in stores.BOARD_WINDOWS
    ]
    return {"rows": rows, "windows": windows}


def _feed(core: dict[str, Any]) -> list[dict[str, Any]]:
    """The newest tool calls, newest first, for the feed panel.

    Three things are deliberate here and each is visible on screen rather than silent:

    1. **Both paths.** Like `_access` and unlike the scene, this uses
       `stage_of_agent_any`. The supervisor path did most of the tool calls historically,
       so a board-only feed would understate the system roughly fivefold.
    2. **Every run, not the selected one.** Only create_task/claim_task/submit_result
       carry a run_tag at all (queries.TASK_TOUCHES), so filtering by the run the
       selector shows would drop most of the feed — a curator's okf_read would simply
       never appear. The panel is labelled "All runs".
    3. **An unrecognised agent is kept, not dropped.** `_build_scene` drops them because
       a line has nowhere to be drawn, but a feed row always has somewhere to go, and a
       call the viewer cannot name is exactly what someone would want to see.

    `key` is built here rather than on the screen: `step_id` alone is not unique once a
    step holds a batch, so the SQL's per-step `seq` is folded in.

    Nothing is merged here, unlike the cost table and the access map: a feed row is one
    call at one moment, and two of them are two rows however they are labelled. The fold
    only changes which agent the row is attributed to.
    """
    names = [stores.reported_as(r["name"]) for r in core["feed"]]
    return [{
        "key": f"{r['step_id']}-{r['seq']}",
        "name": name,
        "agent": stores.stage_of_agent_any(name),
        "label": stores.label_of(name),
        "path": stores.path_of_agent(name),
        "server": stores.normalise_server(r["server"]),
        "tool": r["tool"],
        "store": stores.store_of(r["tool"]),
        "at": _iso(r["started_at"]),
    } for r, name in zip(core["feed"], names, strict=True)]


async def snapshot(run_tag: str | None) -> dict[str, Any]:
    """★ The entry point. One object, everything the six screens need.

    Called once per poll tick (every 2 seconds).

    The reason there is one endpoint is not performance but **consistency.** Fetch
    separately per screen and one screen can be showing the state before an update
    while another shows the state after it.

    **Why this is cached and single-flighted.** Every open tab asks for the same object
    on the same cadence. The lock collapses concurrent callers onto one computation and
    the TTL keeps a second tab from doubling the work. Neither changes a displayed value:
    the screen already shows data up to one poll old, and the TTL is under the interval.

    **Why both waits are bounded, and why a stale answer beats no answer.** This function
    is the last thing between a slow database and a blank screen, so it must not be
    capable of hanging. It was: `async with lock` had no timeout, so one slow computation
    held every other tab on the same run until nginx returned 504 to all of them at once.
    A screen a few seconds behind is worth far more than an error, and the previous
    answer is already sitting in `_snapshot_cache` — so when either wait runs out, that is
    what goes back, flagged `stale` so the screen can say so rather than quietly lie about
    how fresh it is. Only a caller that has no previous answer at all sees a failure.
    """
    lock = _snapshot_locks.setdefault(run_tag, asyncio.Lock())
    try:
        await asyncio.wait_for(lock.acquire(), LOCK_WAIT)
    except TimeoutError:
        # Someone else is computing this and is taking too long. Their result would have
        # been ours; the previous one is close enough and is here now.
        stale = _stale(run_tag)
        if stale is None:
            raise
        return stale
    try:
        hit = _snapshot_cache.get(run_tag)
        if hit is not None and (time.monotonic() - hit[0]) < SNAPSHOT_TTL:
            return hit[1]
        try:
            fresh = await asyncio.wait_for(_snapshot_uncached(run_tag), SNAPSHOT_DEADLINE)
        except TimeoutError:
            stale = _stale(run_tag)
            if stale is None:
                raise
            return stale
        if pools.hiccup():
            # A store dropped exactly one read while this was computed, so `fresh` is
            # partly made of empty fallbacks. Empty does not read as "unknown" on the
            # screen — it reads as an empty board and six idle agents, which is a claim
            # nothing here is entitled to make. The previous picture is a truer account
            # of the pipeline than a fabricated one, and `_stale` labels it as old. It
            # is deliberately not cached: the next tick must compute afresh, and if the
            # store is genuinely gone that tick is no longer a hiccup and the degraded
            # snapshot goes out with health down and the agents drawn `unknown`.
            stale = _stale(run_tag)
            if stale is not None:
                return stale
        _snapshot_cache[run_tag] = (time.monotonic(), fresh)
        return fresh
    finally:
        lock.release()


def _stale(run_tag: str | None) -> dict[str, Any] | None:
    """The last snapshot for *run_tag* marked stale, or None if there has never been one.

    Shallow-copied so the flag is never written into the cached object: the next caller
    to arrive in time deserves an answer that does not claim to be stale. Returning None
    rather than raising keeps the decision to give up at the two call sites, where the
    exception that prompted it is still the live one.
    """
    hit = _snapshot_cache.get(run_tag)
    return None if hit is None else {**hit[1], "stale": True}


async def _snapshot_uncached(run_tag: str | None) -> dict[str, Any]:
    """The real work. Call `snapshot` instead — it is the one that bounds the load."""
    runs = await list_runs()
    tag = run_tag or (runs[0]["run_tag"] if runs else "")

    board = await _board(tag)
    results = await _results(tag)
    core = await _core_facts()
    core_up = pools.health.core
    # There is an order to this: first fetch the run list and settle the tag (the most
    # recent one if none was given), then read the board and results with that tag, then
    # read the core facts.
    # `core_up` has to be read **after _core_facts has been called,** because guarded
    # updates health in the course of that call. Read it first and a value one tick
    # stale is used.

    lanes: dict[str, int] = {}
    # The task count per status (ready / in_progress / done ...) — the numbers at the
    # head of the kanban columns. The board has been read in full already, so they are
    # counted here rather than asked of the DB again.
    for t in board:
        lanes[t["status"]] = lanes.get(t["status"], 0) + 1

    return {
        "run_tag": tag,
        "runs": runs,
        # Always present, so the screen never has to read "key missing" as "fresh".
        # `snapshot` flips it on the copy it hands back when it gave up waiting; see
        # `_stale`.
        "stale": False,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "health": pools.health.as_dict(),
        "scene": _build_scene(core, core_up),
        "board": {"lanes": lanes, "tasks": board},
        "agents": _agent_totals(core),
        "access": _access(core),
        "feed": _feed(core),
        "results": results,
    }
