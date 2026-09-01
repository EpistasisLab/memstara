#!/usr/bin/env python3
"""End-to-end checks for the viewer. Run with the viewer up (docker compose up -d).

Every number the screens show is compared against the databases directly, because a
viewer that is merely self-consistent is worth nothing — the whole point is that it can
be trusted about what actually happened.

==============================================================================
 How to read this file
==============================================================================

 What this file does
   It fetches `/api/snapshot` once over HTTP, pulls the same numbers straight out of
   the DBs with `docker exec psql`, and compares them one by one. Anything that does
   not line up gives exit code 1. It amounts to placing a referee between the screen
   (the viewer) and the truth (the DB).

 The main constants and functions
   BASE                    the viewer's web address (:8070, nginx serves the API too)
   EXPECTED_BY_AGENT_SQL   ★ the SQL for the right answer, **written separately from**
                           api/queries.py
   NAIVE_SQL               SQL written **wrong on purpose.** For proving the traps are
                           really handled
   psql()                  runs psql inside the container with docker exec
   get()                   calls the viewer API over HTTP
   main()                  runs checks 1 to 6 in order

 What is checked
   1  is read-only blocked **by permission** (an UPDATE is actually attempted)
   2  do the per-tool call counts match the DB + are the two windows nobody uses at 0
   3  are the three traps (JSON-null / batched calls) **really** being handled
   4  have the old `ecoxai-*` server names been normalised
   5  do the board row count, the AUCs and the results row count match the DB
   6  is a character holding a card really in_progress + does a dead run not look alive

 Easy things to miss
   ★ **The right answers are not frozen into the file.** An earlier version hardcoded
     the expected numbers, and then ten checks broke the moment the pipeline ran once
     more — **it reported a perfectly good viewer as broken.** So the expected values
     are computed with SQL each time instead.
   ★ That SQL was **written separately, independently of** api/queries.py. It handles
     the same three traps but expresses them differently. If the API side regresses,
     the two computations disagree and it is caught.
     (Had the same SQL been copied over, both would be wrong together and it would
     have passed.)
   ★ Check 3 is the odd one. **It passes only when the naive aggregate differs from
     the result.** If they agree it means the trap handling is doing nothing at all,
     and then a later regression would not be caught either.
==============================================================================
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

# 8070 is the web (nginx) side. nginx hands /api on to the API container at 8071, so
# knowing this one address is enough to check by exactly the same route the screen
# actually receives on.
BASE = "http://localhost:8070"

# Deliberately no frozen expected totals. They go stale the moment the pipeline runs
# again — an earlier version of this file hardcoded them and then failed ten checks
# because a run had happened, reporting a correct viewer as broken.
#
# Instead the expected numbers are computed here with SQL written independently of
# api/queries.py. Same three traps handled, different expression: if the API's version
# regresses, the two disagree.
# (Had queries.FLAT_CALLS been imported and used here, both would be wrong together and
# it would pass.)
#
# The SQL below: the same count restricted to the agents the viewer shows, joined the
# long way round (run_steps -> agent_runs -> agents).
EXPECTED_BY_AGENT_SQL = """
WITH flat AS (
    SELECT s.run_id, s.tool_call->>'tool' AS tool
    FROM run_steps s
    WHERE s.tool_call::text <> 'null' AND s.tool_call->>'tool' IS NOT NULL
    UNION ALL
    SELECT s.run_id, c->>'tool'
    FROM run_steps s, json_array_elements(s.tool_call->'calls') c
    WHERE s.tool_call::text <> 'null' AND s.tool_call->'calls' IS NOT NULL
)
SELECT f.tool || '=' || count(*)
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE a.name LIKE 'memstara%'
GROUP BY f.tool ORDER BY f.tool
"""

# What a naive reader would get: no json-null filter, no batch shape. Kept so the test
# can prove the traps are actually being handled rather than absent by luck.
#
# This naive aggregate has to **differ** from the correct result for the check to pass.
# If the two agree it means the trap-handling code is having no effect at all — and then
# nobody would notice if that code disappeared later.
# `coalesce(..., '(none)')` exposes how many JSON-null rows get miscounted.
NAIVE_SQL = """
SELECT tool || '=' || n FROM (
    SELECT coalesce(r.tool_call->>'tool', '(none)') AS tool, count(*) AS n
    FROM run_steps r
    JOIN agent_runs ar ON ar.id = r.run_id
    JOIN agents a ON a.id = ar.agent_id
    WHERE r.tool_call IS NOT NULL AND a.name LIKE 'memstara%'
    GROUP BY 1
) x ORDER BY tool
"""


def psql(container: str, user: str, db: str, q: str) -> str:
    # Run psql inside the container and take the result back as a string.
    # `-tAc` = no header (-t), unaligned (-A), one command only (-c). That makes the
    # output a plain value that is easy to parse.
    # **Careful:** on failure it does not raise, it returns an empty string (only stdout
    # is looked at). The comparison then fails to line up and the check fails, so it
    # does come out in the end.
    # Unlike the viewer, this connects with the **administrator account** — because it
    # has to see the truth.
    return subprocess.run(
        ["docker", "exec", container, "psql", "-U", user, "-d", db, "-tAc", q],
        capture_output=True, text=True,
    ).stdout.strip()


def get(path: str) -> dict:
    # Call the viewer API over HTTP. It has to be fetched by exactly the same route the
    # browser uses for this to be checking "what the screen actually sees".
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.load(r)


def main() -> int:
    # Runs checks 1 to 6 in order. **It does not stop at the first failure** — it
    # collects everything that did not line up and shows the lot at the end.
    ok: list[str] = []
    bad: list[str] = []

    def chk(label: str, cond: bool, detail: str = "") -> None:
        # True goes on the ok list, false on the bad list. detail holds **what to look
        # at when it did not line up** (the screen value and the DB value side by side).
        (ok if cond else bad).append(f"{label}  {detail}")

    snap = get("/api/snapshot")
    # The snapshot is fetched **once only** and every check below uses that one.
    # Fetch afresh per check and the pipeline moves in between, which sets off a false
    # alarm where the checks disagree with each other while the viewer is fine.
    tag = snap["run_tag"]

    # 1 — read-only is a permission, not a promise.
    # "Our code does not issue UPDATEs" is not a proof. So an UPDATE is actually fired
    # and it is checked that it **is refused** — connecting directly with the viewer
    # account (memstara_viewer).
    denied = subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD=viewer", "memstara-postgres", "psql",
         "-U", "memstara_viewer", "-d", "memstara", "-c",
         "UPDATE memstara_blackboard SET status='ready'"],
        capture_output=True, text=True,
    ).stderr
    # It passes only if stderr holds "permission denied". If it succeeded, that is bad.
    chk("1 read-only", "permission denied" in denied, denied.strip()[:60])

    # 2/3/4 — the flattening, checked against independently written SQL.
    # First the screen's numbers are summed per tool into totals. The access map's rows
    # are per agent × tool, so they have to be added up per tool again to be of the same
    # grain as the DB aggregate.
    totals: dict[str, int] = {}
    for row in snap["access"]["rows"]:
        totals[row["tool"]] = totals.get(row["tool"], 0) + row["calls"]

    raw = psql("motoro-postgres", "agentic", "motoro", EXPECTED_BY_AGENT_SQL)
    # The psql output is one `toolname=number` per line, so `split("=")` turns it
    # straight into a dict.
    # First **the tool list itself** is compared (as sets), then the counts one by one.
    # If the lists do not line up, "only on the screen / only in the DB" is printed for
    # both sides.
    expected = dict(
        (k, int(v)) for k, v in (line.split("=") for line in raw.splitlines() if "=" in line)
    )
    chk("2 number of tool kinds", set(totals) == set(expected),
        f"screen only {set(totals) - set(expected)} / DB only {set(expected) - set(totals)}")
    for tool, want in sorted(expected.items()):
        chk(f"2 tool {tool}", totals.get(tool) == want, f"screen {totals.get(tool)} / DB {want}")

    # 3 — prove the traps are handled: a naive count must NOT agree, or the fixes are
    # doing nothing and would not catch a regression either.
    #   - JSON-null: the naive side must show a "(none)" entry and the screen must not.
    #   - batched calls: the naive search_concepts count must be **smaller** than the
    #     right answer.
    naive_raw = psql("motoro-postgres", "agentic", "motoro", NAIVE_SQL)
    naive = dict(
        (k, int(v)) for k, v in (line.split("=") for line in naive_raw.splitlines() if "=" in line)
    )
    chk("3 JSON-null not counted as a call", "(none)" in naive and "(none)" not in totals,
        f"{naive.get('(none)')} empty entries in the naive aggregate")
    chk("3 batched calls not missed", naive.get("search_concepts", 0) < expected.get("search_concepts", 0),
        f"naive {naive.get('search_concepts', 0)} < correct {expected.get('search_concepts')}")
    servers = {r["server"] for r in snap["access"]["rows"]}
    # 4 — the old names normalised. Not one server beginning with `ecoxai` may be left.
    # If one is, the access map shows the same server split across two rows.
    chk("4 old names normalised", not any(s.startswith("ecoxai") for s in servers), str(sorted(servers)))

    # The two windows no agent holds. Empty here is the correct picture, not a gap.
    # `read_board` is the driving script's business and `count_waiting` is used by
    # nobody. Checking this means nobody later chases a bug that is not there asking
    # "why is this 0?".
    windows = {w["tool"]: w for w in snap["access"]["windows"]}
    chk("2 read_board is the script's business", windows["read_board"]["calls"] == 0)
    chk("2 count_waiting is used by nobody", windows["count_waiting"]["calls"] == 0)

    # 5 — the board matches the database it came from.
    # Not just the row count: **the AUC values are strung together in task_id order and
    # compared whole.** With the row count alone, a value that is off or an order that
    # got shuffled would be missed.
    # (`string_agg(... ORDER BY task_id)` and the join on the screen side use the same
    # order.)
    n = psql("memstara-postgres", "memstara", "memstara",
             f"SELECT count(*) FROM memstara_blackboard WHERE run_tag='{tag}'")
    chk("5 board row count", str(len(snap["board"]["tasks"])) == n, f"screen {len(snap['board']['tasks'])} / DB {n}")
    aucs = psql("memstara-postgres", "memstara", "memstara",
                f"SELECT string_agg(auc::text, ',' ORDER BY task_id) FROM memstara_blackboard "
                f"WHERE run_tag='{tag}'")
    chk("5 AUC", ",".join(str(t["auc"]) for t in snap["board"]["tasks"]) == aucs, aucs)
    r = psql("memstara-postgres", "memstara", "memstara",
             f"SELECT count(*) FROM memstara_results WHERE run_tag='{tag}'")
    chk("5 results row count", str(len(snap["results"])) == r)

    # 6 — a character holding a card must be holding a card the board agrees is held.
    # The scene's carrying is a value obtained by replaying the record of tool calls
    # (scene._carrying); the board's in_progress is what the DB knows directly. The two
    # routes have to meet.
    # Comparing as a subset (⊆) is the right call — a task can be in_progress on the
    # board while no character has been drawn holding it yet, but the reverse must not
    # happen.
    # If nobody is holding anything it simply passes (which is normal when the pipeline
    # is not running).
    held = {a["carrying"] for a in snap["scene"]["agents"] if a["carrying"] is not None}
    if held:
        inprog = psql("memstara-postgres", "memstara", "memstara",
                      f"SELECT string_agg(task_id::text, ',' ORDER BY task_id) "
                      f"FROM memstara_blackboard WHERE run_tag='{tag}' AND status='in_progress'")
        db = set(inprog.split(",")) if inprog else set()
        chk("6 character holding a card", {str(h) for h in held} <= db, f"scene {held} / DB {db}")
    else:
        chk("6 character holding a card", True, "nobody is holding one right now (normal when not running)")

    # A dead run must not leave a character permanently "working".
    # It passes when, with a run that has actually been pending for over an hour (= the
    # trap really being present), not one character on screen is working.
    # That is the evidence that the time window of scene.RUN_ALIVE_SECONDS /
    # queries.OPEN_RUNS is doing its job.
    # (If there are 0 old pending runs this check proves nothing, so it is set up to be
    # caught as a failure.)
    stale = psql("motoro-postgres", "agentic", "motoro",
                 "SELECT count(*) FROM agent_runs WHERE completed_at IS NULL "
                 "AND status='pending' AND created_at < now() - interval '1 hour'")
    working = [a["label"] for a in snap["scene"]["agents"] if a["state"] == "working"]
    chk("6 dead run does not look alive", int(stale) > 0 and not working,
        f"{stale} old pending runs yet working {working}")

    # The skeleton of the scene. 5 places and 5 characters must always come out. Add a
    # stage without making room for it in stores.PLACES/HOME and it is caught here.
    chk("5 places", len(snap["scene"]["places"]) == 5)
    chk("5 characters", len(snap["scene"]["agents"]) == 5)
    chk("both DBs answered", snap["health"]["memstara"]["up"] and snap["health"]["core"]["up"])

    # Only the count for what passed; for what did not, the reason in full.
    # Exit code 1 is picked up as a failure by CI or the shell as it stands.
    print(f"  passed {len(ok)} / mismatched {len(bad)}")
    for b in bad:
        print("   ✗", b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
