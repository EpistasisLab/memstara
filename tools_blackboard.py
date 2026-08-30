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
 이 파일을 읽는 법
==============================================================================

 판(blackboard)을 만지는 **유일한 창구**. 에이전트는 DB 를 직접 보지 않는다.

 표가 둘이다. 이 구분이 이 파일의 핵심이다.

   memstara_blackboard   작업대. 아직 움직이는 일이 놓인다. 치우면 사라진다
   memstara_results      기록. 끝난 것만 남는다. 판을 치워도 남는다

 한 과제가 지나가는 길:

   create_task      가설 단계가 새 줄을 만든다        status=ready · type=data
        ↓
   claim_task       데이터 단계가 집어 간다            status=in_progress
        ↓
   submit_result    결과를 적고 다음 단계로 넘긴다     status=ready · type=ml
        ↓           (같은 일이 ml → interpret 로 반복)
        ↓
   submit_result    마지막 단계가 끝내면              status=done
                    **그때 결과표에 한 줄이 복사된다**

 읽는 도구 셋:
   count_waiting    몇 개가 기다리나 (파이프라인용, 에이전트용 아님)
   read_board       판 전체 — 안 끝난 것 포함
   read_results     끝난 것만 — 보고 단계가 이걸 읽는다

 사람이 직접 불러 보려면: `python debug_harness.py board`
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import asyncpg                            # PostgreSQL 비동기 드라이버
from mcp.server.fastmcp import FastMCP

# 자식 프로세스라 부모 디버거가 안 닿는다. MEMSTARA_DEBUGPY 에 이 서버 이름이
# 들어 있을 때만 디버거를 기다린다 — 없으면 아무 일도 하지 않는다. debug_hook.py 참고.
from debug_hook import quiet_child, wait_for_debugger

quiet_child()          # 자식이 켜질 때 찍는 잡음 세 가지를 끈다
wait_for_debugger('memstara-blackboard')

mcp = FastMCP("memstara-blackboard")

# 한 단계가 끝나면 다음은 누구인가. 여기 없는 단계(interpret)가 마지막이라는 뜻이다.
# submit_result 가 이 표를 보고 status 를 'ready'(다음이 있음) 또는 'done' 으로 정한다.
NEXT_STAGE = {"hypothesis": "data", "data": "ml", "ml": "interpret"}


# 환경변수가 없을 때 쓸 주소. docker-compose.yml 이 띄우는 컨테이너를 가리킨다.
# 포트 5463 — core 의 5453 과 **다른 DB** 다.
DEFAULT_DSN = "postgresql://memstara:memstara@localhost:5463/memstara"


def _dsn() -> str:
    """Read the address the same way blackboard.py does — Memstara's database, not core's.

    Read lazily rather than at import time: `os.environ[...]` up top kills the server
    during startup, and core reports that only as "tools available: []".
    """
    url = os.environ.get("MEMSTARA_DATABASE_URL", "").strip() or DEFAULT_DSN
    # SQLAlchemy 는 "postgresql+asyncpg://" 처럼 드라이버를 이름에 붙이지만
    # asyncpg 는 그 형식을 모른다. 붙어 있으면 떼어 낸다.
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _err(e: Exception) -> str:
    """예외를 에이전트가 읽을 수 있는 JSON 으로. 종류 이름까지 넣는다.

    도구는 예외를 밖으로 던지지 않는다. 던지면 에이전트에게는 "도구가 고장났다" 로만
    보이고, 무엇을 고쳐야 할지 판단할 재료가 없다.
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
            # 새 줄은 항상 status='ready', task_type='data' 로 시작한다 —
            # 만들어지자마자 데이터 단계가 집어 갈 수 있는 상태다.
            # y_column 을 여기 적는 것이 중요하다. 이후 모든 단계가 이 값을 판에서
            # 읽는다 — 프롬프트로 따로 알려 주지 않는다.
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
async def claim_task(task_type: str) -> str:
    """Take one waiting task of your type, so nobody else can take it.

    Args:
        task_type: one of "data", "ml", "interpret" — the stage you are.

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
            #
            # ↑ 이 서버의 존재 이유가 이 한 문장에 있다.
            #   FOR UPDATE       고른 줄을 잠근다 — 다른 연결이 못 건드린다
            #   SKIP LOCKED      이미 잠긴 줄은 **기다리지 않고 건너뛴다**
            #   두 개를 같이 써야 같은 종류의 에이전트 둘이 한 과제를 집는 일이 없다.
            #   SKIP LOCKED 가 없으면 둘째가 첫째를 기다리다가, 첫째가 끝난 뒤
            #   **같은 줄을** 집는다.
            #
            #   브레이크포인트로는 이 동작이 안 보인다 — 멈춰 있는 동안엔 경쟁이
            #   없기 때문이다. 보려면 psql 두 창을 띄워야 한다.
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
                        ORDER BY task_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING task_id, run_tag, trial, perspective, hypothesis,
                              columns, y_column, okf_concept_ids, subset_path,
                              columns_used, auc, feature_importance
                    """,
                    task_type,
                )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    # 집을 게 없으면 None 이 온다. 이걸 오류로 만들지 않는 것이 중요하다 —
    # "지금 나한테 올 일이 없다" 는 정상 상태이고, 에이전트는 여기서 멈춰야 한다.
    if row is None:
        return json.dumps({"task_id": None})

    out: dict[str, Any] = dict(row)
    # DB 에는 JSON 문자열로 들어 있다. 파이썬 값으로 풀어서 돌려준다 —
    # 안 풀면 에이전트가 문자열 안의 JSON 을 또 파싱해야 한다.
    # 없을 때의 기본값이 다르다: 목록은 [], 중요도는 {}.
    for k in ("columns", "okf_concept_ids", "columns_used", "feature_importance"):
        out[k] = json.loads(out[k]) if out[k] else ([] if k != "feature_importance" else {})
    # default=str — 시각(datetime) 같은 값을 JSON 이 모르므로 문자열로 바꾼다.
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
                # 집지 않은 과제에 결과를 쓰는 것을 막는다. 이 검사가 없으면
                # 남이 하고 있는 일에 자기 결과를 덮어쓸 수 있다.
                if cur["status"] != "in_progress":
                    return json.dumps(
                        {"error": f"task {task_id} is '{cur['status']}', not in_progress — claim it first"}
                    )

                stage = cur["task_type"]          # 지금 이 과제가 있는 단계
                nxt = NEXT_STAGE.get(stage)       # 다음 단계 (없으면 None = 마지막)
                new_status = "ready" if nxt else "done"   # 다음이 있으면 다시 대기
                new_type = nxt or stage                   # 마지막이면 종류는 그대로

                # 단계마다 채우는 칸이 다르다. 그래서 **준 것만 덮어쓰고 나머지는
                # 그대로 둔다.** 그 장치가 아래의 COALESCE / NULLIF / CASE 다.
                #   NULLIF($2, '')  빈 문자열이면 NULL 로
                #   COALESCE(a, b)  a 가 NULL 이면 b (= 원래 값 유지)
                # 이게 없으면 ml 단계가 결과를 낼 때 데이터 단계가 적어 둔 경로가
                # 빈 문자열로 지워진다.
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
                # still moving, this holds what was found.
                #
                # ↑ 결과표가 따로 있는 이유. 판은 작업대라 치우면 사라지지만, 찾아낸
                #   것은 남아야 한다. **마지막 단계가 끝나는 이 순간에만** 한 줄이
                #   복사된다 — 그래서 결과표에는 끝까지 간 것만 있다.
                #   (판의 줄을 지워도 이 줄은 남는다. 외래키가 ON DELETE SET NULL 이라
                #    task_id 만 비고 내용은 그대로다.)
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
async def count_waiting(task_type: str = "") -> str:
    """How many tasks are waiting, and how many are being worked on.

    Args:
        task_type: restrict to one stage; "" counts every stage.

    Returns:
        JSON with counts per stage. The driving script uses this to decide who to
        call next, and to know when everything is finished.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            rows = await conn.fetch(
                """
                SELECT task_type, status, count(*) AS n FROM memstara_blackboard
                WHERE ($1 = '' OR task_type = $1)
                GROUP BY task_type, status
                """,
                task_type,
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


@mcp.tool()
async def read_questions(status: str = "open", limit: int = 50) -> str:
    """What this project has already thought to ask. Read this before proposing more.

    The question bank spans runs. That is the point of reading it: without it every run
    starts from nothing and re-proposes the questions the last run already worked
    through, which looks like progress and is not.

    Args:
        status: "open" for questions still worth using, "exhausted" for ones retired,
            or "" for both.
        limit: how many to return, newest first.

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
        ``{"added": [...], "duplicates": [...], "rejected": [...]}``. Duplicates are
        questions already in the bank and are not an error — they mean the generator
        converged on something already known, which is worth seeing. ``rejected`` is
        questions dropped for having no tags, with the reason.
    """
    try:
        parsed = json.loads(questions or "[]")
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"questions is not valid JSON: {e}"})
    if not isinstance(parsed, list):
        return json.dumps({"error": "questions must be a JSON array"})

    added: list[dict] = []
    duplicates: list[str] = []
    rejected: list[dict] = []
    try:
        conn = await asyncpg.connect(_dsn())
        try:
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
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)

    return json.dumps(
        {"added": added, "duplicates": duplicates, "rejected": rejected},
        ensure_ascii=False,
    )


@mcp.tool()
async def record_question_outcomes(run_tag: str) -> str:
    """Fold a finished run's scores back into the question bank.

    The driver calls this, not an agent — it is bookkeeping about a wave that has ended,
    and no agent is in a position to know a wave has ended. It is also why the bank can
    say anything about which questions were worth asking: without this the bank is a
    list of what was asked and never a record of what came of it.

    Safe to call twice for the same run: ``times_used`` is recomputed from the results
    table rather than incremented, so a repeat lands on the same number.

    Args:
        run_tag: the run whose results should be folded in.

    Returns:
        ``{"ok": true, "questions_updated": N}``.
    """
    try:
        conn = await asyncpg.connect(_dsn())
        try:
            updated = await conn.fetch(
                """
                UPDATE memstara_questions q
                   SET times_used = s.n,
                       best_auc   = GREATEST(q.best_auc, s.mx)
                  FROM (SELECT question_id, count(*) AS n, max(auc) AS mx
                          FROM memstara_results
                         WHERE question_id IS NOT NULL
                         GROUP BY question_id) s
                 WHERE q.question_id = s.question_id
                   AND EXISTS (SELECT 1 FROM memstara_results r
                                WHERE r.question_id = q.question_id
                                  AND ($1 = '' OR r.run_tag = $1))
                RETURNING q.question_id
                """,
                run_tag,
            )
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        return _err(e)
    return json.dumps({"ok": True, "questions_updated": len(updated)})


if __name__ == "__main__":
    mcp.run()
