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
             "interpretation": r["interpretation"], "created_at": _iso(r["created_at"])}
            for r in rows
        ]

    return await pools.guarded("memstara", q, [])


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
            "recent": [dict(r) for r in await conn.fetch(queries.RECENT_CALLS,
                                                        str(FLASH_SECONDS))],
            "feed": [dict(r) for r in await conn.fetch(queries.FEED)],
        }

    # The empty shell to return when core is down. It has to carry **the same seven keys**
    # as above. Leave even one out and a KeyError comes up below, turning "core is down"
    # into "the viewer crashed" — which makes everything guarded holds off pointless.
    empty: dict[str, Any] = {"totals": [], "open": [], "access": [],
                             "touches": [], "last_call": [], "recent": [], "feed": []}
    return await pools.guarded("core", q, empty)


# --------------------------------------------------------------------------- #
#  The scene
# --------------------------------------------------------------------------- #


def _carrying(touches: list[dict[str, Any]]) -> dict[str, int]:
    """Which agent currently holds which task, replayed from the board windows.

    A `claim_task` puts a task in an agent's hands; the matching `submit_result` takes
    it back. Replaying in time order leaves exactly what is still held — the board's own
    `in_progress` rows say a task is held but not by whom, and "by whom" is the thing
    the scene needs to draw.
    """
    held: dict[str, int] = {}
    # Stage -> the number of the task it is holding. One stage is taken to be able to
    # hold only one thing at a time.
    for t in touches:
        stage = stores.AGENT_BY_NAME.get(t["name"])
        if stage is None or not t.get("task_id"):
            continue
        task_id = int(t["task_id"])
        if t["tool"] == "claim_task":
            # Picked up, it goes in; submitted, it comes out.
            # Taking it out only when `held.get(stage) == task_id` — **the very task it
            # was holding** — matters. Simply clearing instead would let an old
            # submit_result that arrived late drop the new task just picked up.
            held[stage] = task_id
        elif t["tool"] == "submit_result" and held.get(stage) == task_id:
            held.pop(stage, None)
    return held


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
    # ★ Assembles the scene: the five characters' **state, position and what they are
    # holding,** and the lines that will flash.
    #
    # First the rows that came from core are indexed by stage. `if r["name"] in
    # stores.AGENT_BY_NAME` is what does the filtering — only **board-path characters**
    # appear in the scene, so supervisor-path agents are quietly dropped here.
    # (The access map is the opposite: it has to count both. See _access.)
    open_by_stage = {
        stores.AGENT_BY_NAME[r["name"]]: r
        for r in core["open"] if r["name"] in stores.AGENT_BY_NAME
    }
    last_by_stage = {
        stores.AGENT_BY_NAME[r["name"]]: r
        for r in core["last_call"] if r["name"] in stores.AGENT_BY_NAME
    }
    held = _carrying(core["touches"])
    # The three ingredients are now gathered: the runs going right now (open), the last
    # call (last), and what is in hand (held). The for loop below combines the three to
    # settle one character's state.
    #
    # They are keyed by **stage**, and the loop walks **characters**, so each ingredient
    # is chosen from the stages that character stands for. For four of the five that is
    # a list of one and the choosing does nothing.
    members = _members_of_each_character()

    agents = []
    for stage in stores.HOME:
        # The character's own name, and only its own: a merged character is labelled for
        # the stage it is drawn as, not for every stage folded into it. The loop walks
        # `HOME`, which has five keys, so a folded-away stage is never looked up here —
        # `AGENT_LABELS` still holds the retired `curator` because
        # `check_definitions.py:154` requires a label for every stage the viewer knows,
        # not because anything on screen reads it.
        label = stores.AGENT_LABELS.get(stage, stage)
        mine = members.get(stage, [stage])

        # Both members can be busy at once — on a pre-2026-09-07 run the curator could
        # be writing wave n+1's questions while a hypothesis worker was still on wave n —
        # so pick the run that started most recently: that is what the character is doing
        # *now*. A single-member character takes the same branch and gets its own run.
        running = [(open_by_stage[s], s) for s in mine if s in open_by_stage]
        run, run_stage = (
            max(running, key=lambda pair: pair[0]["created_at"]) if running else (None, None)
        )
        calls = [(last_by_stage[s], s) for s in mine if s in last_by_stage]
        last, last_stage = (
            max(calls, key=lambda pair: pair[0]["started_at"]) if calls else (None, None)
        )
        # `carrying` needs no tie-break: only stages granted `claim_task` can hold one,
        # and of the two folded together only the hypothesis stage has it
        # (`src/memstara/pipeline/core.py:354-428`). Written for the general case anyway,
        # because a grant is a table somebody can edit.
        holding = [(held[s], s) for s in mine if s in held]
        carrying = holding[0][0] if holding else None

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
            # Holds a task but no run is open: it picked the task up and its run ended.
            # It cannot be called dead and it cannot be called working, so it is drawn
            # as **"moving"** and stood in front of the board.
            #
            # The order these states are decided in is the priority order:
            # unknown -> working -> moving -> idle.
            state, at = "moving", "board"
        else:
            # No run going and nothing in hand means it really is idle.
            state, at = "idle", None

        # `name` is the agent that produced the state just settled, not the character's
        # own — so replaying a pre-2026-09-07 run, the merged character says
        # `memstara-board-curator` while that agent is the one running, and which of the
        # two is working stays readable from the card.
        agents.append({
            "id": stage,
            "label": label,
            "name": stores.BOARD_AGENT_NAMES_ANY.get(run_stage or last_stage or stage, stage),
            "state": state,
            "at": at,
            "home": stores.HOME[stage],
            "carrying": carrying,
            "run_id": str(run["run_id"]) if run else None,
            "since": _iso(run["created_at"]) if run else None,
            "last_tool": None if not last else {
                "server": last["server"], "tool": last["tool"],
                "store": stores.store_of(last["tool"]), "at": _iso(last["started_at"]),
            },
            "windows": sorted({t for s in mine for t in stores.STAGE_WINDOWS.get(s, set())}),
            # The list of windows this character can open — the **union** over the stages
            # it stands for, because a merged character really can open all of them. A
            # set has no order, so left alone the order shifts on every refresh and the
            # screen flickers. Hence the sort.
            #
            # `STAGE_WINDOWS` and not `BOARD_TOOLS`: the latter is what one *call* may
            # hold, and the hypothesis agent has two calls with two different lists
            # (`stores.STAGE_WINDOWS`). Reading BOARD_TOOLS here would drop
            # `read_questions`, `read_results` and `propose_questions` from the card
            # while `BOARD_WINDOWS` still names Hypothesis as their holder — two screens
            # disagreeing, with neither saying so.
        })

    # flashes below: the calls of the last few seconds = **the lines that will flash**
    # on screen.
    # `place` is settled by the **tool**, not the server (stores.store_of) — because the
    # one board server is responsible for two places, the board and the results table.
    # Here too only board-path characters are kept. A line for a character that is not
    # in the scene has nowhere to be drawn — which is why `drawn_as` has to be applied
    # here as well as above. `ScenePanel.tsx` builds each edge as `source: agent-${agent}`
    # against the node ids it got from `agents`, so a flash still keyed `curator` would
    # name a node that no longer exists and the line would simply not appear.
    flashes = [
        {"agent": stores.drawn_as(stores.AGENT_BY_NAME[r["name"]]),
         "place": stores.store_of(r["tool"]),
         "tool": r["tool"], "server": r["server"], "at": _iso(r["started_at"])}
        for r in core["recent"] if r["name"] in stores.AGENT_BY_NAME
    ]

    return {"places": stores.PLACES, "agents": agents, "flashes": flashes}


def _agent_totals(core: dict[str, Any]) -> list[dict[str, Any]]:
    # The running totals per agent (run count, tokens, cost). Unlike the scene, this
    # **shows both paths.** That is why it uses `AGENT_BY_NAME_ANY` rather than
    # `AGENT_BY_NAME`, and marks with `path` whether it is the board path or the
    # supervisor path.
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
                "id": stores.AGENT_BY_NAME_ANY.get(name),
                "path": stores.AGENT_PATH.get(name, "other"),
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
        if r["name"] not in stores.AGENT_BY_NAME_ANY:
            continue
        name = stores.reported_as(r["name"])
        key = (name, r["server"], r["tool"])
        row = merged.get(key)
        if row is None:
            row = merged[key] = {
                "agent": stores.AGENT_BY_NAME_ANY.get(name, name),
                "agent_label": stores.label_of(name),
                "name": name,
                "path": stores.AGENT_PATH.get(name, "other"),
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
       `AGENT_BY_NAME_ANY`. The supervisor path did most of the tool calls historically,
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
        "agent": stores.AGENT_BY_NAME_ANY.get(name),
        "label": stores.label_of(name),
        "path": stores.AGENT_PATH.get(name, "other"),
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
