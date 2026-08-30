#!/usr/bin/env python3
"""Retrace a board run that already happened — what the agent asked the tools, and got back.

Why this is separate
--------------------
`03_board_pipeline.py` now leaves `runs.json` and `trace/` behind at the end of a
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
    python trace_board.py --run-tag example          # runs inside that run's time window
    python trace_board.py --run-tag example --out /tmp/t   # to files instead of the screen
    python trace_board.py --last 10                  # the 10 most recent runs
    python trace_board.py --run-id 04f6812d-...      # just one
    python trace_board.py --run-tag example --summary  # headers only, bodies omitted

Read-only. Nothing is modified, neither the board nor core's database.

이미 지나간 판 실행을 되짚어 본다 — 에이전트가 도구에 무엇을 묻고 무엇을 받았나.

왜 따로 필요한가
----------------
`03_board_pipeline.py` 는 이제 실행이 끝날 때 `runs.json` 과 `trace/` 를 남긴다.
하지만 그건 **앞으로의 실행** 이야기다. 그 전에 돌린 것들(`conda1` · `example` …)은
run_id 를 안 남겼다.

그런데 기록 자체는 다 있다. core 는 실행의 모든 단계를 `run_steps` 에 저장하고,
거기에는 **도구 호출의 인자와 결과가 통째로** 들어 있다. 다만 "어느 실행이 그
run_tag 의 것이었나" 를 잇는 고리가 없을 뿐이다.

그 고리를 **시각**으로 잇는다. 판의 그 run_tag 행들이 만들어지고 마지막으로 바뀐
시각을 구하고, core 의 `agent_runs` 에서 그 창에 든 실행을 고른다.

정확하지 않을 수 있다
---------------------
같은 시각에 다른 실행이 돌았다면 그것도 섞인다. 확실히 하려면 앞으로는
`runs.json` 을 쓰면 된다 — 이 스크립트는 **그 이전 것들을 위한 것**이다.
섞였는지 알 수 있게 각 실행의 입력 문장을 같이 찍는다.

쓰는 법
-------
    python trace_board.py --run-tag example          # 그 실행의 시간 창 안 실행들
    python trace_board.py --run-tag example --out /tmp/t   # 화면 대신 파일로
    python trace_board.py --last 10                  # 최근 실행 10건
    python trace_board.py --run-id 04f6812d-...      # 하나만
    python trace_board.py --run-tag example --summary  # 머리말만, 본문 생략

읽기 전용이다. 판도 core DB 도 아무것도 고치지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import asyncpg

from blackboard import dsn
from settings import Settings
from trace_run import render

from agentic_core import configure

#: How far the board's time window is widened at each end. An agent run starts
#: **before** its rows are written to the board and finishes **after**, so cutting
#: exactly at the boundaries clips both ends off.
#:
#: 판의 시간 창 앞뒤로 이만큼 넓힌다. 에이전트 실행은 판에 줄이 적히기 **전에**
#: 시작하고 적힌 **뒤에** 끝나므로, 딱 맞게 자르면 앞뒤가 잘려 나간다.
MARGIN = timedelta(minutes=3)


async def window_for(run_tag: str) -> tuple[object, object]:
    """The time window in which that run_tag was alive on the board. Exits if absent.

    그 run_tag 가 판에 살아 있던 시간 창. 없으면 종료한다.
    """
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
        sys.exit(f"판에 run_tag '{run_tag}' 이 없다.")
    return row["lo"] - MARGIN, row["hi"] + MARGIN


async def runs_between(lo: object, hi: object) -> list[tuple[str, uuid.UUID]]:
    """The runs inside that window, from core's database, in time order.

    Core uses SQLAlchemy for its own database, but only a listing is needed here, so
    asyncpg reads it directly — which leans on core's internal schema, meaning a
    renamed column breaks this first. That is why a failure prints its reason instead
    of being swallowed.

    core 의 DB 에서 그 창에 든 실행을 시간 순으로.

    core 는 자기 DB 를 SQLAlchemy 로 쓰지만, 여기서는 목록만 필요하므로 asyncpg 로
    직접 읽는다 — core 의 내부 스키마에 기대는 부분이라 컬럼 이름이 바뀌면 여기가
    먼저 깨진다. 그래서 실패하면 조용히 넘어가지 않고 이유를 찍는다.
    """
    import os
    import re

    url = os.environ.get("AGENTIC_DATABASE_URL", "").strip()
    if not url:
        sys.exit("AGENTIC_DATABASE_URL 이 없다 — core 의 DB 주소가 필요하다.")
    # asyncpg does not understand the "postgresql+asyncpg://" form.
    # asyncpg 는 "postgresql+asyncpg://" 형식을 모른다.
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
    """The n most recent runs, straight from core and independent of the board.

    최근 실행 n 건. 판과 무관하게 core 에서 바로.
    """
    lo = hi = None
    import os
    import re

    url = re.sub(r"^postgresql\+\w+://", "postgresql://",
                 os.environ.get("AGENTIC_DATABASE_URL", "").strip())
    if not url:
        sys.exit("AGENTIC_DATABASE_URL 이 없다.")
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
    # 최근 것부터 받았으니 읽기 좋게 시간 순으로 뒤집는다.
    return [
        (f"{r['created_at']:%m-%d %H:%M:%S} {r['status']:<9} {r['head']}",
         r["id"] if isinstance(r["id"], uuid.UUID) else uuid.UUID(str(r["id"])))
        for r in reversed(rows)
    ]


async def main() -> int:
    """Pick the runs asked for on the command line and render each one.

    명령줄이 가리키는 실행들을 골라 하나씩 풀어 보여 준다.
    """
    ap = argparse.ArgumentParser(description="지나간 판 실행을 되짚어 본다")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-tag", help="판의 실행 이름. 그 시간 창에 든 실행을 모두 보여준다")
    g.add_argument("--last", type=int, help="최근 실행 N 건")
    g.add_argument("--run-id", help="실행 하나만")
    ap.add_argument("--out", help="화면 대신 이 폴더에 파일로 쓴다")
    ap.add_argument("--summary", action="store_true", help="머리말만. 단계 본문은 생략")
    ap.add_argument("--clip", action="store_true", help="긴 값을 자른다 (기본은 자르지 않음)")
    args = ap.parse_args()

    configure(Settings())   # hand core its database URL and the rest / core 에 DB 주소 등을 알려 준다

    if args.run_id:
        picked = [("run", uuid.UUID(args.run_id))]
    elif args.last:
        picked = await latest(args.last)
    else:
        lo, hi = await window_for(args.run_tag)
        picked = await runs_between(lo, hi)
        print(f"'{args.run_tag}' 의 시간 창: {lo:%m-%d %H:%M:%S} ~ {hi:%m-%d %H:%M:%S} "
              f"(앞뒤 {MARGIN.seconds // 60}분 여유)")
        print(f"그 안의 실행 {len(picked)}건 — 같은 시각의 다른 실행이 섞일 수 있다\n")

    if not picked:
        print("해당하는 실행이 없다.")
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
        print(f"\n{len(picked)}개 파일: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
