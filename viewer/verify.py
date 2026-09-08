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
   FEED_SQL                ★ the feed's rows, also **written separately from**
                           api/queries.py — a LATERAL join where the API uses a comma
   FEED_LIMIT              queries.FEED's LIMIT, written out here on purpose
   psql()                  runs psql inside the container with docker exec
   get()                   calls the viewer API over HTTP
   main()                  runs checks 1 to 7 in order

 What is checked
   1  is read-only blocked **by permission** (an UPDATE is actually attempted)
   2  do the per-tool call counts match the DB + are the two windows nobody uses at 0
   3  are the three traps (JSON-null / batched calls) **really** being handled
   4  have the old `ecoxai-*` server names been normalised
   5  do the board row count, the AUCs and the results row count match the DB
   6  is a character holding a card really in_progress + does a dead run not look alive
      + does only the hypothesis station show more than one figure
   7  does the feed hold the newest calls the DB holds — and is it non-empty at all

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
from collections import Counter
from datetime import datetime

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


# queries.FEED's LIMIT, written out rather than imported — the same reason the scene's
# "6 places" is written out. Change the limit on the API side and forget to say so here
# and this fails, which is the point.
FEED_LIMIT = 60

# stores.DRAWN_AS: which stages the scene draws as one character. Written out for the
# same reason as FEED_LIMIT — a referee that imports the player's answer sheet is not
# refereeing. Fold the grouping on the API side without saying so here and check 7 fails.
#
# `curator` is a retired stage: the pipeline stopped naming it on 2026-09-07 and the
# question step became the hypothesis agent's other job. The entry stays because the
# databases this file reads still hold hundreds of runs recorded against it, and this
# file's whole purpose is to be right about the databases. Check 7 below therefore asks
# whether a name the feed used **arrives somewhere** on the floor, not whether the two
# sets are equal.
DRAWN_AS = {"curator": "hypothesis"}

# stores.HOME's keys: the stations on the floor, one per stage the pipeline still runs.
# Written out for the same reason as the two above.
#
# This is the number that stayed fixed when the character count stopped being fixed. The
# scene has drawn one figure per **worker** since 2026-09-08, so `--data-agents 3` puts
# seven figures on the floor and any check written as `== 5` would fail on a run that was
# working perfectly. Five *stations* is still a promise the viewer makes, and it is the
# one worth checking: every figure stands at one of these, and every one of these has at
# least one figure, because a stage with nothing running still puts its resting figure
# down. See check 6 below.
STATIONS = {"hypothesis", "data", "ml", "interpreter", "report"}

# The feed's rows, computed independently of api/queries.py. Same three traps, expressed
# differently again: a CROSS JOIN LATERAL where FLAT_CALLS uses the comma form, and the
# two shapes named as separate CTEs rather than one UNION inside a single `flat`.
#
# `{where}` is filled with a boundary condition rather than an ORDER BY + LIMIT, because
# the feed's ordering is genuinely ambiguous at the boundary: every call inside one
# batched step shares a started_at *and* a step_id, so which of them lands on row 60 is
# not defined by either side. Comparing everything **strictly newer than the feed's
# oldest row** is tie-safe and still catches a dropped or mistyped call.
FEED_SQL = """
WITH one AS (
    SELECT s.run_id, s.started_at, s.tool_call->>'tool' AS tool
    FROM run_steps s
    WHERE s.tool_call::text <> 'null' AND s.tool_call->>'server' IS NOT NULL
), many AS (
    SELECT s.run_id, s.started_at, c->>'tool' AS tool
    FROM run_steps s
    CROSS JOIN LATERAL json_array_elements(s.tool_call->'calls') c
    WHERE s.tool_call::text <> 'null' AND s.tool_call->'calls' IS NOT NULL
), every_call AS (
    -- Not named `both`: that is a reserved word in Postgres (trim(BOTH ...)) and the
    -- CTE fails to parse. psql's error goes to stderr, which psql() does not read, so
    -- it would surface only as an empty result — "the DB has 0 calls".
    SELECT * FROM one UNION ALL SELECT * FROM many
)
SELECT b.tool || '=' || count(*)
FROM every_call b
JOIN agent_runs r ON r.id = b.run_id
JOIN agents a ON a.id = r.agent_id
{where}
GROUP BY b.tool ORDER BY b.tool
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
    # Runs checks 1 to 7 in order. **It does not stop at the first failure** — it
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
    #
    # **Both sides spell an unfinished task the same way, as the empty string.** A task
    # that has been claimed but not scored has `auc IS NULL`, and the two sides used to
    # disagree about what that looks like: `string_agg` drops NULL rows entirely, while
    # the screen has a row for each and rendered it `str(None)` -> `"None"`. So a board
    # of three claimed-and-unscored tasks compared `"None,None,None"` against `""` and
    # this check failed, while a board where a *scored* AUC had gone missing compared
    # short against short and could pass. `coalesce` on one side and an explicit empty
    # string on the other make the two agree on the absent value without making the
    # check blind to it — the commas stay, so a row that vanishes is still a mismatch.
    n = psql("memstara-postgres", "memstara", "memstara",
             f"SELECT count(*) FROM memstara_blackboard WHERE run_tag='{tag}'")
    chk("5 board row count", str(len(snap["board"]["tasks"])) == n, f"screen {len(snap['board']['tasks'])} / DB {n}")
    aucs = psql("memstara-postgres", "memstara", "memstara",
                f"SELECT string_agg(coalesce(auc::text, ''), ',' ORDER BY task_id) "
                f"FROM memstara_blackboard WHERE run_tag='{tag}'")
    screen_aucs = ",".join("" if t["auc"] is None else str(t["auc"]) for t in snap["board"]["tasks"])
    chk("5 AUC", screen_aucs == aucs, f"screen {screen_aucs!r} / DB {aucs!r}")
    r = psql("memstara-postgres", "memstara", "memstara",
             f"SELECT count(*) FROM memstara_results WHERE run_tag='{tag}'")
    chk("5 results row count", str(len(snap["results"])) == r)

    # The explanation has to arrive with the result, and a row count cannot see whether it
    # did — every result could carry an empty importance map and the count above would
    # still pass. So the same trick as the AUC check: the number of importances per
    # result, strung together in result_id order and compared whole.
    #
    # This is the check that would have caught the panel reading importances off the
    # **board** instead. `memstara_results.task_id` is `ON DELETE SET NULL`, so once a
    # board row is cleaned away that lookup returns nothing while the AUC stays — the
    # result keeps its score and loses the reason for it. Nothing on screen said so.
    imps = psql("memstara-postgres", "memstara", "memstara",
                f"SELECT string_agg(n::text, ',' ORDER BY result_id) FROM ("
                f"SELECT result_id, (SELECT count(*) FROM jsonb_object_keys(feature_importance)) AS n "
                f"FROM memstara_results WHERE run_tag='{tag}') t")
    screen_imps = ",".join(str(len(res["importance"])) for res in snap["results"])
    chk("5 importances per result", screen_imps == imps, f"screen {screen_imps} / DB {imps}")

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

    # The skeleton of the scene. 6 places and 5 stations must always come out. Add a
    # stage without making room for it in stores.PLACES/HOME and it is caught here.
    # Both numbers are written out rather than read from stores, so that adding a stage
    # to the viewer and forgetting to say so here still fails. (They were frozen at 5
    # while PLACES already held 6 and the pipeline already had six stages, so this line
    # was reporting a stale number rather than a real gap.)
    #
    # **The two numbers differ and both are right.** Six places, five stations: the
    # pipeline has five board agents since 2026-09-07, and the sixth it used to have —
    # the curator — is retired rather than deleted, so its runs are still in the database
    # and still reach the floor through stores.DRAWN_AS. This file is the place that
    # counts those runs under their own agent name, which is exactly why it reads the
    # databases directly and never imports from `api/` — the checks below would be worth
    # nothing if they asked the viewer whether the viewer was right.
    #
    # The character count was `== 5` here until 2026-09-08 and is not a constant any
    # more; see STATIONS above for why, and what replaced it. The three checks below are
    # what "5 characters" was actually protecting, said in the terms that survive
    # parallelism: every figure belongs to a station, every station has a figure, and no
    # two figures share an id. The last is not pedantry — React Flow keys its nodes by
    # that string and draws two nodes sharing one id as a single node, silently, so a
    # duplicate would look exactly like the collapse this all exists to stop.
    #
    # The leading digit in each label is the check group, not a count. Do not read
    # "6 characters" as an expected six.
    chk("6 places", len(snap["scene"]["places"]) == 6, str(len(snap["scene"]["places"])))
    figures = snap["scene"]["agents"]
    at_station = [a["stage"] for a in figures]
    chk("6 characters stand at a station", set(at_station) <= STATIONS,
        f"{sorted(set(at_station) - STATIONS)} stand nowhere")
    chk("6 every station has a character", STATIONS <= set(at_station),
        f"{sorted(STATIONS - set(at_station))} have none")
    chk("6 character ids are unique", len({a["id"] for a in figures}) == len(figures),
        f"{len(figures)} figures, {len({a['id'] for a in figures})} ids")

    # **Only the hypothesis station may show more than one figure.** The meeting of
    # 2026-08-26 decided this in the other direction from how it first shipped: the
    # backend may run N of any stage, and the screen shows the hypothesis agents split
    # because that is the parallelism the user chose, while the data agent stays one
    # character — the user does not need to know it is internally run more than once.
    #
    # `"hypothesis"` is written out here rather than read from `stores.SPLITTABLE`, for
    # the same reason this whole file reads the databases instead of the API: a check that
    # asks the implementation what the rule is agrees with the implementation about
    # everything, including what it has backwards. That is not a hypothetical — the first
    # version of this split all five stations and three separate checks passed, because
    # all three had been written from the code.
    per_station = Counter(a["stage"] for a in figures)
    folded = {s: n for s, n in per_station.items() if s != "hypothesis" and n > 1}
    chk("6 only the hypothesis station splits", not folded, f"{folded} drawn more than once")

    # And the fold must not be a disappearance. A station drawn once while two workers run
    # has to say two, or `--data-agents 2` and `--data-agents 1` are the same picture.
    miscounted = [(a["id"], a["state"], a["running"]) for a in figures
                  if (a["state"] in ("working", "moving")) != (a["running"] > 0)]
    chk("6 a busy character counts its workers", not miscounted, f"{miscounted}")
    chk("both DBs answered", snap["health"]["memstara"]["up"] and snap["health"]["core"]["up"])

    # 7 — the feed.
    # A feed that silently returns nothing looks exactly like a quiet system, so the first
    # thing established is that it is empty only when there is genuinely nothing to show.
    feed = snap["feed"]
    all_rows = psql("motoro-postgres", "agentic", "motoro", FEED_SQL.format(where=""))
    total = sum(
        int(v) for _, v in (line.split("=") for line in all_rows.splitlines() if "=" in line)
    )
    chk("7 feed is empty only if the DB is", (len(feed) > 0) == (total > 0),
        f"screen {len(feed)} rows / DB {total} calls")
    chk("7 feed length", len(feed) == min(FEED_LIMIT, total),
        f"screen {len(feed)} / DB min({FEED_LIMIT}, {total})")

    # The feed really holds the newest calls the DB holds. Compared as counts per tool
    # over everything **strictly newer than the feed's oldest row**, which is the widest
    # slice both sides agree on unambiguously — see FEED_SQL on why the boundary row
    # itself cannot be compared.
    if feed:
        t0 = min(datetime.fromisoformat(e["at"]) for e in feed)
        newer = psql("motoro-postgres", "agentic", "motoro",
                     FEED_SQL.format(where=f"WHERE b.started_at > timestamptz '{t0.isoformat()}'"))
        want = dict(
            (k, int(v)) for k, v in (line.split("=") for line in newer.splitlines() if "=" in line)
        )
        got: dict[str, int] = {}
        for e in feed:
            if datetime.fromisoformat(e["at"]) > t0:
                got[e["tool"]] = got.get(e["tool"], 0) + 1
        chk("7 feed holds the newest calls", got == want,
            f"screen {sorted(got.items())} / DB {sorted(want.items())}")

        # The same normalisation check as 4, on the feed's own rows — it builds its
        # servers through stores.normalise_server just as the access map does, and a feed
        # that skipped it would show one server under two names.
        chk("7 feed servers normalised",
            not any(e["server"].startswith("ecoxai") for e in feed),
            str(sorted({e["server"] for e in feed})))

        # A row the viewer cannot name keeps agent=null and is shown anyway. What must
        # not happen is a *named* row naming a stage that reaches no character on screen.
        #
        # The question is whether a name the feed used **arrives somewhere**, which is
        # what folding through DRAWN_AS asks, rather than whether the two sets are equal.
        #
        # Since 2026-09-07 the API folds the feed itself, so `named` no longer holds
        # `curator` and the fold below is an identity on everything it sees. It stays,
        # and deliberately: this file's job is to be right about the databases whatever
        # the API does with them, and the day the API stops folding is the day this line
        # is the only thing standing between a historical curator call and a failed check
        # that blames the wrong thing.
        # `stage` and not `id`: a figure's id is its **worker** name when a stage runs
        # more than one (`hypothesis#2`), and the feed names stages. Left as `id` this
        # check would report every hypothesis call as a stray the moment
        # `--hypothesis-agents 2` was passed — a failure describing the check rather than
        # the data.
        stages = {a["stage"] for a in snap["scene"]["agents"]}
        named = {e["agent"] for e in feed if e["agent"] is not None}
        strays = {DRAWN_AS.get(a, a) for a in named} - stages
        chk("7 feed stages are real stages", not strays, str(sorted(strays)))

    # Only the count for what passed; for what did not, the reason in full.
    # Exit code 1 is picked up as a failure by CI or the shell as it stands.
    print(f"  passed {len(ok)} / mismatched {len(bad)}")
    for b in bad:
        print("   ✗", b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
