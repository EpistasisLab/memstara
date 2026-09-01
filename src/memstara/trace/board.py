#!/usr/bin/env python3
"""Retrace a board run that already happened — what the agent asked the tools, and got back.

Why this is separate
--------------------
`src/memstara/pipeline/board.py` now leaves `runs.json` and `trace/` behind at the end of a
run. But that is a story about **future runs**. The earlier ones (`conda1`,
`example`, …) recorded no run_id.

The record itself is all there, though. Core stores every phase of every run in
`run_steps`, and that includes **each tool call's arguments and result in full**.
What is missing is only the link saying "which run belonged to that run_tag".

That link is rebuilt from **time**. Take the window in which the board rows for that
run_tag were created and last updated, then pick the runs from core's `agent_runs`
that fall inside it.

It may not be exact
-------------------
Another run happening at the same time is swept in too. For certainty, use
`runs.json` going forward — this script exists **for the runs that came before it**.
Each run's input text is printed alongside so a mix-up is visible.

Usage
-----
    python -m memstara.trace.board --run-tag example          # runs inside that run's time window
    python -m memstara.trace.board --run-tag example --out /tmp/t   # to files instead of the screen
    python -m memstara.trace.board --last 10                  # the 10 most recent runs
    python -m memstara.trace.board --run-id 04f6812d-...      # just one
    python -m memstara.trace.board --run-tag example --summary  # headers only, bodies omitted

Read-only. Nothing is modified, neither the board nor core's database.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import asyncpg

from memstara.blackboard import dsn
from memstara.config import Settings
from memstara.trace.run import render

from motoro import configure

#: How far the board's time window is widened at each end. An agent run starts
#: **before** its rows are written to the board and finishes **after**, so cutting
#: exactly at the boundaries clips both ends off.
MARGIN = timedelta(minutes=3)


async def window_for(run_tag: str) -> tuple[object, object]:
    """The time window in which that run_tag was alive on the board. Exits if absent."""
    conn = await asyncpg.connect(dsn())
    try:
        row = await conn.fetchrow(
            "SELECT min(created_at) AS lo, max(updated_at) AS hi "
            "FROM memstara_blackboard WHERE run_tag = $1",
            run_tag,
        )
    finally:
        await conn.close()

    if row is None or row["lo"] is None:
        sys.exit(f"the board has no run_tag '{run_tag}'.")
    return row["lo"] - MARGIN, row["hi"] + MARGIN


async def runs_between(lo: object, hi: object) -> list[tuple[str, uuid.UUID]]:
    """The runs inside that window, from core's database, in time order.

    Core uses SQLAlchemy for its own database, but only a listing is needed here, so
    asyncpg reads it directly — which leans on core's internal schema, meaning a
    renamed column breaks this first. That is why a failure prints its reason instead
    of being swallowed.
    """
    import os
    import re

    url = os.environ.get("MOTORO_DATABASE_URL", "").strip()
    if not url:
        sys.exit("no MOTORO_DATABASE_URL — core's database address is needed.")
    # asyncpg does not understand the "postgresql+asyncpg://" form.
    url = re.sub(r"^postgresql\+\w+://", "postgresql://", url)

    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT id, status, left(coalesce(input,''), 70) AS head, created_at "
            "FROM agent_runs WHERE created_at BETWEEN $1 AND $2 ORDER BY created_at",
            lo, hi,
        )
    finally:
        await conn.close()

    out = []
    for r in rows:
        label = f"{r['created_at']:%H:%M:%S} {r['status']:<9} {r['head']}"
        out.append((label, r["id"] if isinstance(r["id"], uuid.UUID) else uuid.UUID(str(r["id"]))))
    return out


async def latest(n: int) -> list[tuple[str, uuid.UUID]]:
    """The n most recent runs, straight from core and independent of the board."""
    lo = hi = None
    import os
    import re

    url = re.sub(r"^postgresql\+\w+://", "postgresql://",
                 os.environ.get("MOTORO_DATABASE_URL", "").strip())
    if not url:
        sys.exit("no MOTORO_DATABASE_URL.")
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT id, status, left(coalesce(input,''), 70) AS head, created_at "
            "FROM agent_runs ORDER BY created_at DESC LIMIT $1",
            n,
        )
    finally:
        await conn.close()
    # They arrive newest-first; reverse into time order so they read naturally.
    return [
        (f"{r['created_at']:%m-%d %H:%M:%S} {r['status']:<9} {r['head']}",
         r["id"] if isinstance(r["id"], uuid.UUID) else uuid.UUID(str(r["id"])))
        for r in reversed(rows)
    ]


async def main() -> int:
    """Pick the runs asked for on the command line and render each one."""
    ap = argparse.ArgumentParser(description="retrace a board run that already happened")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-tag", help="the board's run name. Shows every run inside its time window")
    g.add_argument("--last", type=int, help="the N most recent runs")
    g.add_argument("--run-id", help="just one run")
    ap.add_argument("--out", help="write files into this folder instead of to the screen")
    ap.add_argument("--summary", action="store_true", help="headers only. Step bodies omitted")
    ap.add_argument("--clip", action="store_true", help="cut long values (by default nothing is cut)")
    args = ap.parse_args()

    configure(Settings())   # hand core its database URL and the rest

    if args.run_id:
        picked = [("run", uuid.UUID(args.run_id))]
    elif args.last:
        picked = await latest(args.last)
    else:
        lo, hi = await window_for(args.run_tag)
        picked = await runs_between(lo, hi)
        print(f"time window of '{args.run_tag}': {lo:%m-%d %H:%M:%S} ~ {hi:%m-%d %H:%M:%S} "
              f"({MARGIN.seconds // 60} min of slack at each end)")
        print(f"{len(picked)} runs inside it — another run from the same time may be mixed in\n")

    if not picked:
        print("no matching run.")
        return 0

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for i, (label, rid) in enumerate(picked):
        if out_dir:
            path = out_dir / f"{i:02d}_{rid.hex[:8]}.txt"
            with path.open("w", encoding="utf-8") as fh:
                await render(label, rid, full=not args.clip, summary=args.summary, stream=fh)
        else:
            await render(label, rid, full=not args.clip, summary=args.summary)

    if out_dir:
        print(f"\n{len(picked)} files: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
