"""Turns database rows into the one snapshot every screen reads.

All interpretation happens here, on purpose. If each screen worked out for itself what
"this agent is carrying task 27" means, two screens would eventually disagree about the
same run — and the viewer's only job is to be trusted.

Two stores are read independently (see db.guarded). If core's database is down the board
and results still come back and `health.core.up` is false; the scene then shows
characters at rest rather than pretending to know what they are doing.

↑ 데이터베이스의 행들을 **모든 화면이 공유하는 단 하나의 스냅샷**으로 바꾼다.

  해석은 **전부 여기서** 한다. 이건 의도된 설계다. "이 에이전트가 27번 과제를 들고
  있다"가 무슨 뜻인지 화면마다 알아서 계산한다면, 언젠가 두 화면이 같은 실행을 두고
  **서로 다른 말을 하게 된다** — 그리고 뷰어의 유일한 임무는 믿을 수 있는 것이다.

  두 저장소를 각각 독립적으로 읽는다(db.guarded 참고). core DB 가 죽어 있으면 판과
  결과는 그대로 돌아오고 `health.core.up` 만 false 가 된다. 그때 장면은 캐릭터를
  **쉬는 상태가 아니라 "모름(unknown)" 으로** 그린다 — 뭘 하는지 아는 척하지 않는다.

==============================================================================
 이 파일을 읽는 법
==============================================================================

 무엇을 하는 파일인가
   queries.py 의 SQL 을 돌려 얻은 날것의 행을, 프론트엔드가 그대로 그릴 수 있는
   한 덩어리 JSON("스냅샷")으로 조립한다. 뷰어의 **두뇌**에 해당한다.
   진입점은 맨 아래 `snapshot()` 하나이고, 2초마다 한 번씩 불린다.

 위에서 아래로
   FLASH_SECONDS / RUN_ALIVE_SECONDS / STAGE_INDEX   세 개의 판단 기준값
   _jsonb / _iso / _retried        작은 변환기들
   --- 읽기 (Reads) ---
   list_runs / _board / _results   memstara DB 에서
   _core_facts                     core DB 에서 (여섯 질의를 연결 하나로)
   --- 장면 (The scene) ---
   _carrying     ★ 지금 누가 어느 과제를 들고 있는지 재생해서 복원
   _build_scene  ★ 캐릭터들의 상태·위치·반짝임을 정한다
   _agent_totals / _access         표와 접근 지도
   snapshot()    ★ 위 전부를 모아 한 객체로

 놓치기 쉬운 핵심
   1. **RUN_ALIVE_SECONDS (120초)** — 죽은 실행이 살아 있는 것처럼 보이지 않게
      막는 시간 창. 이게 없으면 프로세스가 죽은 실행 때문에 캐릭터가 영원히
      "일하는 중"으로 서 있는다.
   2. **`attempts` 는 재시도 횟수가 아니다.** 단계가 넘어갈 때마다 새로 claim 되므로
      정상적인 과제도 attempts 가 3이 된다. `_retried()` 가 그 차이를 빼 준다.
   3. **core 가 죽으면 "쉬는 중"이 아니라 "모름"이다.** 쉬는 중이라고 말하는 것은
      할 수 없는 단언을 하는 것이다.
   4. `_carrying` 은 판이 답해 주지 않는 질문에 답한다. 판의 `in_progress` 행은
      "누군가 들고 있다"까지만 말하고 **누가**인지는 말하지 않는다.
   5. 접근 지도는 판 경로 + 감독관 경로 **양쪽**을 센다. 한쪽만 세면 다섯 배쯤
      과소 보고된다.
==============================================================================
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg

import queries
import stores
from db import pools

# How long a tool call keeps lighting up its line. Long enough to notice at a 2s poll,
# short enough that the scene does not look permanently busy.
FLASH_SECONDS = 4
# ↑ 도구 호출 하나가 선을 몇 초 동안 밝혀 두는가.
#   2초 폴링에서 **놓치지 않을 만큼 길고**, 장면이 늘 분주해 보이지 않을 만큼 짧다.
#   이 값은 queries.RECENT_CALLS 의 $1 로 그대로 넘어간다.

# How long a run may go without a heartbeat before it stops counting as in-flight.
# Runs heartbeat every few seconds and a stage takes under a minute, so two minutes of
# silence means the process died — not that the agent is thinking hard.
RUN_ALIVE_SECONDS = 120
# ↑ ★ **죽은 실행을 살아 있는 것으로 보이지 않게 하는 시간 창.**
#   실행은 몇 초마다 심장박동을 남기고 한 단계는 1분 안에 끝난다. 그러니 2분 동안
#   조용하다는 것은 **프로세스가 죽었다**는 뜻이지, 에이전트가 골똘히 생각 중이라는
#   뜻이 아니다.
#   이 값이 없으면 `completed_at IS NULL` 인 채로 남은 유령 실행들(7일 된 것도 있다)
#   때문에 캐릭터가 영원히 "일하는 중"으로 서 있게 된다.
#   queries.OPEN_RUNS 의 $1 로 넘어간다.

# A task's stage order, used to tell a genuine retry from normal progress. `attempts`
# counts *claims*: a task that goes data -> ml -> interpret is claimed three times and
# has failed nothing. Reading it as a retry count reports a clean run as troubled.
STAGE_INDEX = {"data": 1, "ml": 2, "interpret": 3}
# ↑ 과제의 단계 순서. **진짜 재시도**와 **정상적인 진행**을 구별하는 데 쓴다.
#
#   `attempts` 는 재시도 횟수가 아니라 **claim(집어 든) 횟수**다. data → ml →
#   interpret 로 정상 진행한 과제는 세 번 claim 되고, 실패한 것은 하나도 없다.
#   이걸 재시도 횟수로 읽으면 **깨끗한 실행을 문제 있는 실행으로 보고**하게 된다.
#   아래 `_retried()` 가 이 표를 써서 그 차이를 빼 준다.


def _jsonb(value: Any, empty: Any) -> Any:
    # ↑ DB 가 돌려준 JSON 칼럼을 파이썬 값으로 안전하게 편다.
    #   드라이버 설정에 따라 이미 list/dict 로 올 수도 있고 문자열로 올 수도 있어서
    #   양쪽을 다 받는다. 못 읽으면 예외 대신 *empty*(보통 [] 나 {})를 준다 —
    #   칼럼 하나가 깨졌다고 화면 전체가 죽으면 안 되기 때문이다.
    if value in (None, ""):
        return empty
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return empty


def _iso(dt: datetime | None) -> str | None:
    # ↑ 시각을 **UTC ISO 문자열**로 통일한다. 프론트엔드가 시간대를 추측하지 않게
    #   하려는 것이다. None 은 None 그대로 통과시킨다 (아직 없는 시각과 0시를 구별).
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def _retried(task: dict[str, Any]) -> int:
    """Extra claims beyond what a healthy task of this stage would have had."""
    # ↑ 이 단계의 정상적인 과제라면 있었을 claim 횟수를 **넘어선 초과분.**
    #
    #   예: `ml` 단계에서 status 가 'ready' 가 아니면 정상 claim 수는 2회다
    #   (data 에서 한 번, ml 에서 한 번). attempts 가 2면 재시도 0회.
    #   'ready' 면 아직 이번 단계를 집어 들기 전이므로 기대치에서 1을 뺀다.
    #   `max(..., 0)` 두 번은 음수가 나오지 않게 막는다 — 모르는 단계이거나
    #   데이터가 어긋났을 때 "재시도 -1회" 같은 소리를 하지 않기 위해서다.
    expected = STAGE_INDEX.get(task["task_type"], 0) - (1 if task["status"] == "ready" else 0)
    return max((task.get("attempts") or 0) - max(expected, 0), 0)


# --------------------------------------------------------------------------- #
#  Reads
# --------------------------------------------------------------------------- #


async def list_runs() -> list[dict[str, Any]]:
    # ↑ 실행(run_tag) 목록. 안쪽 `q` 를 `pools.guarded` 에 넘기는 이 모양이
    #   이 파일 전체의 공통 패턴이다: **DB 가 죽으면 예외 대신 빈 목록**(fallback)
    #   이 돌아오고, 죽었다는 사실은 pools.health 에 남는다.
    #   queries.RUNS 가 최신순 정렬이므로 [0] 번이 곧 "가장 최근 실행"이다.
    async def q(conn: asyncpg.Connection) -> list[dict[str, Any]]:
        rows = await conn.fetch(queries.RUNS)
        return [
            {"run_tag": r["run_tag"], "tasks": r["tasks"], "done": r["done"],
             "first_seen": _iso(r["first_seen"]), "last_seen": _iso(r["last_seen"])}
            for r in rows
        ]

    return await pools.guarded("memstara", q, [])


async def _board(run_tag: str) -> list[dict[str, Any]]:
    # ↑ 판 한 판의 모든 과제. 화면의 카드 하나하나가 여기 딕셔너리 하나다.
    #   DB 행을 그대로 넘기지 않고 **여기서 한 번 번역**하는 이유: 화면이 DB 칼럼
    #   이름과 타입에 직접 매이지 않게 하고, 해석을 한 군데로 모으기 위해서다.
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
                # ↑ JSON 칼럼들은 전부 `_jsonb` 를 거친다. 빈 값의 모양을 함께
                #   지정하는 것이 중요하다 — 목록 자리엔 [], 사전 자리엔 {}.
                #   None 이 화면으로 새어 나가면 프론트에서 매번 방어해야 한다.
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
            # ↑ **여기서 계산해서 붙인다.** 화면이 attempts 를 보고 직접 판단하면
            #   화면마다 다른 답을 낼 수 있다. 판단은 백엔드에 한 번만 둔다.
            out.append(t)
        return out

    return await pools.guarded("memstara", q, [])


async def _results(run_tag: str) -> list[dict[str, Any]]:
    # ↑ 결과 표. 판과 **다른 테이블**이고 장면에서도 다른 장소다.
    #   판은 진행 중인 것을, 이 표는 확정된 발견을 담는다.
    async def q(conn: asyncpg.Connection) -> list[dict[str, Any]]:
        rows = await conn.fetch(queries.RESULTS, run_tag)
        return [
            {"result_id": r["result_id"], "task_id": r["task_id"], "trial": r["trial"],
             "perspective": r["perspective"], "hypothesis": r["hypothesis"],
             "columns_used": _jsonb(r["columns_used"], []),
             "y_column": r["y_column"], "auc": r["auc"],
             "interpretation": r["interpretation"], "created_at": _iso(r["created_at"])}
            for r in rows
        ]

    return await pools.guarded("memstara", q, [])


async def _core_facts() -> dict[str, Any]:
    """Everything from core's database, in one connection acquisition."""
    # ↑ core DB 에서 필요한 것 **전부를, 연결 한 번 잡아서** 가져온다.
    #
    #   질의가 여섯 개인데 `guarded` 를 여섯 번 부르지 않는 이유:
    #   - 커넥션을 여섯 번 잡았다 놓았다 하지 않아도 되고,
    #   - 무엇보다 **여섯 결과가 같은 순간의 DB 상태**여서 서로 어긋나지 않는다.
    #     (한 질의는 실행 전, 다른 질의는 실행 후를 보는 일이 없다.)
    #   - 그리고 실패해도 **여섯이 함께** 실패한다: 절반만 있는 장면이 안 생긴다.

    async def q(conn: asyncpg.Connection) -> dict[str, Any]:
        return {
            "totals": [dict(r) for r in await conn.fetch(queries.AGENT_TOTALS)],
            "open": [dict(r) for r in await conn.fetch(queries.OPEN_RUNS,
                                                       str(RUN_ALIVE_SECONDS))],
            "access": [dict(r) for r in await conn.fetch(queries.ACCESS)],
            "touches": [dict(r) for r in await conn.fetch(queries.TASK_TOUCHES)],
            "last_call": [dict(r) for r in await conn.fetch(queries.LAST_CALL)],
            "recent": [dict(r) for r in await conn.fetch(queries.RECENT_CALLS,
                                                        str(FLASH_SECONDS))],
        }

    # ↑ core 가 죽었을 때 돌려줄 빈 껍데기. **키 여섯 개가 위와 똑같이** 있어야
    #   한다. 하나라도 빠지면 아래에서 KeyError 가 나면서, "core 가 죽었다"가
    #   "뷰어가 터졌다"로 바뀐다 — guarded 로 막아 놓은 것이 무의미해진다.
    empty: dict[str, Any] = {"totals": [], "open": [], "access": [],
                             "touches": [], "last_call": [], "recent": []}
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

    ↑ 지금 **어느 에이전트가 어느 과제를 들고 있는지**를, 판의 창문 기록을 재생해서 복원한다.

    `claim_task` 는 과제를 에이전트 손에 쥐여 주고, 짝이 되는 `submit_result` 는
    도로 가져간다. 시간순으로 재생하면 **아직 손에 남아 있는 것**만 정확히 남는다.

    왜 이렇게까지 하나: 판의 `in_progress` 행은 "누군가 들고 있다"까지만 말하고
    **누가** 들고 있는지는 말하지 않는다. 그런데 장면이 그려야 하는 것은 바로 그
    "누가"다.
    """
    held: dict[str, int] = {}
    # ↑ 단계 → 들고 있는 과제 번호. 한 단계는 한 번에 하나만 들 수 있다고 본다.
    for t in touches:
        stage = stores.AGENT_BY_NAME.get(t["name"])
        if stage is None or not t.get("task_id"):
            continue
        task_id = int(t["task_id"])
        if t["tool"] == "claim_task":
            # ↑ 집어 들면 넣고, 제출하면 뺀다.
            #   `held.get(stage) == task_id` 로 **자기가 들고 있던 그 과제**일 때만
            #   빼는 것이 중요하다. 그냥 지우면, 늦게 도착한 옛 submit_result 가
            #   방금 집어 든 새 과제를 손에서 떨어뜨려 버린다.
            held[stage] = task_id
        elif t["tool"] == "submit_result" and held.get(stage) == task_id:
            held.pop(stage, None)
    return held


def _build_scene(core: dict[str, Any], core_up: bool) -> dict[str, Any]:
    # ↑ ★ 장면을 조립한다. 캐릭터 다섯 명의 **상태·위치·들고 있는 것**과, 반짝일 선들.
    #
    #   먼저 core 에서 온 행들을 단계별로 색인해 둔다. `if r["name"] in
    #   stores.AGENT_BY_NAME` 이 필터 역할을 한다 — 장면에는 **판 경로 캐릭터만**
    #   나오므로, 감독관 경로 에이전트는 여기서 조용히 걸러진다.
    #   (접근 지도 쪽은 반대로 둘 다 세야 한다. _access 참고.)
    open_by_stage = {
        stores.AGENT_BY_NAME[r["name"]]: r
        for r in core["open"] if r["name"] in stores.AGENT_BY_NAME
    }
    last_by_stage = {
        stores.AGENT_BY_NAME[r["name"]]: r
        for r in core["last_call"] if r["name"] in stores.AGENT_BY_NAME
    }
    held = _carrying(core["touches"])
    # ↑ 세 재료가 모였다: 지금 도는 실행(open) / 마지막 호출(last) / 손에 든 것(held).
    #   아래 for 문이 이 셋을 조합해 캐릭터 하나의 상태를 정한다.

    agents = []
    for stage, label in stores.AGENT_LABELS.items():
        run = open_by_stage.get(stage)
        last = last_by_stage.get(stage)
        carrying = held.get(stage)

        if not core_up:
            # Not "idle" — unknown. Saying idle would be an assertion we cannot make.
            #
            # ↑ "쉬는 중"이 아니라 **"모름"**이다. core DB 를 못 읽는 상황에서
            #   "이 에이전트는 놀고 있다"고 말하는 것은 **할 수 없는 단언**을 하는
            #   것이다. 모르면 모른다고 해야 화면을 믿을 수 있다.
            state, at = "unknown", None
        elif run is not None:
            state = "working"
            at = stores.store_of(last["tool"]) if last else None
        elif carrying is not None:
            # Holds a task but no run is open: it picked the task up and its run ended.
            #
            # ↑ 과제는 들고 있는데 도는 실행이 없다 = 집어 들고 나서 그 실행이
            #   끝나 버린 상태. 죽었다고도, 일한다고도 할 수 없어서 **"이동 중"**
            #   으로 그리고 판 앞에 세워 둔다.
            #
            #   상태 판정 순서가 곧 우선순위다: 모름 → 일하는 중 → 이동 중 → 쉬는 중.
            state, at = "moving", "board"
        else:
            state, at = "idle", None
            # ↑ 도는 실행도 없고 손에 든 것도 없으면 진짜로 쉬는 중이다.

        agents.append({
            "id": stage,
            "label": label,
            "name": stores.BOARD_AGENT_NAMES.get(stage, stage),
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
            "windows": sorted(stores.BOARD_TOOLS.get(stage, set())),
            # ↑ 이 캐릭터가 열 수 있는 창문 목록. set 은 순서가 없어서 그냥 두면
            #   새로 고칠 때마다 순서가 흔들려 화면이 깜빡인다. 그래서 정렬한다.
        })

    # ↑ 아래 flashes: 최근 몇 초 안의 호출들 = 화면에서 **반짝일 선들.**
    #   `place` 는 서버가 아니라 **도구**로 정한다(stores.store_of) — 판 서버 하나가
    #   판과 결과 표 두 곳을 담당하기 때문이다.
    #   여기서도 판 경로 캐릭터만 남긴다. 장면에 없는 캐릭터의 선은 그릴 데가 없다.
    flashes = [
        {"agent": stores.AGENT_BY_NAME[r["name"]],
         "place": stores.store_of(r["tool"]),
         "tool": r["tool"], "server": r["server"], "at": _iso(r["started_at"])}
        for r in core["recent"] if r["name"] in stores.AGENT_BY_NAME
    ]

    return {"places": stores.PLACES, "agents": agents, "flashes": flashes}


def _agent_totals(core: dict[str, Any]) -> list[dict[str, Any]]:
    # ↑ 에이전트별 누적 표(실행 수·토큰·비용). 장면과 달리 **두 경로를 다 보여 준다.**
    #   그래서 `AGENT_BY_NAME` 이 아니라 `AGENT_BY_NAME_ANY` 를 쓰고, `path` 로
    #   판 경로인지 감독관 경로인지 표시한다.
    #   `int()`·`float()` 로 감싸는 이유: PostgreSQL 의 numeric 은 파이썬에서
    #   Decimal 로 오는데, 그대로면 JSON 직렬화에서 걸린다.
    #   `r["cost"] or 0` 은 NULL 과 0 을 함께 처리한다.
    return [{
        "name": r["name"],
        "id": stores.AGENT_BY_NAME_ANY.get(r["name"]),
        "path": stores.AGENT_PATH.get(r["name"], "other"),
        "label": stores.AGENT_LABELS.get(stores.AGENT_BY_NAME_ANY.get(r["name"], ""), r["name"]),
        "runs": r["runs"], "completed": r["completed"], "open_runs": r["open_runs"],
        "tokens": {"prompt": int(r["prompt_tokens"]), "completion": int(r["completion_tokens"])},
        "cost": float(r["cost"] or 0),
        "avg_iterations": round(r["avg_iterations"], 2) if r["avg_iterations"] else None,
        "last_run_at": _iso(r["last_run_at"]),
    } for r in core["totals"]]


def _access(core: dict[str, Any]) -> dict[str, Any]:
    # Both driving paths, not just the board one. The supervisor agents did most of the
    # tool calls historically; filtering them out made this map understate reality
    # roughly fivefold while still looking internally consistent.
    #
    # ↑ **두 경로를 다 넣는다.** 판 경로만이 아니다.
    #   역사적으로 도구 호출의 대부분은 감독관(supervisor) 에이전트들이 했다.
    #   그들을 걸러 냈더니 이 지도가 실제를 **다섯 배쯤 과소 보고**하면서도
    #   내부적으로는 아귀가 맞아 보였다 — 딱 알아채기 어려운 종류의 오류다.
    #
    #   서버 단위로 거르면 가설 단계가 남의 일까지 집을 수 있다. 그래서 **도구
    #   하나하나 단위로** 저장소를 정한다(stores.store_of).
    rows = [{
        "agent": stores.AGENT_BY_NAME_ANY.get(r["name"], r["name"]),
        "agent_label": stores.AGENT_LABELS.get(stores.AGENT_BY_NAME_ANY.get(r["name"], ""), r["name"]),
        "name": r["name"],
        "path": stores.AGENT_PATH.get(r["name"], "other"),
        "server": r["server"], "tool": r["tool"],
        "store": stores.store_of(r["tool"]),
        "calls": r["calls"], "last_at": _iso(r["last_at"]),
    } for r in core["access"] if r["name"] in stores.AGENT_BY_NAME_ANY]

    called = {r["tool"] for r in rows}
    # ↑ 실제로 한 번이라도 불린 도구들의 집합.
    #   아래에서 판 서버의 **모든 창문**을 훑으면서 각 창문의 호출 수와
    #   "에이전트가 부른 적이 있는가"를 붙인다.
    #   `read_board`(구동 스크립트 몫)와 `count_waiting`(아무도 안 씀)이 0으로
    #   남는 것이 **올바른 그림**이다. 빠진 데이터가 아니다 — verify.py 가 이 0 을
    #   실제로 확인한다.
    windows = [
        {**w, "calls": sum(r["calls"] for r in rows if r["tool"] == w["tool"]),
         "called_by_agent": w["tool"] in called}
        for w in stores.BOARD_WINDOWS
    ]
    return {"rows": rows, "windows": windows}


async def snapshot(run_tag: str | None) -> dict[str, Any]:
    """One object, everything the six screens need. Called once per poll tick."""
    # ↑ ★ **진입점.** 화면 여섯 개가 필요로 하는 전부를 담은 객체 하나.
    #   폴링 한 번에 한 번 불린다(2초마다).
    #
    #   엔드포인트를 하나로 둔 이유는 성능이 아니라 **일관성**이다. 화면마다 따로
    #   받아 오면 어떤 화면은 갱신 전, 어떤 화면은 갱신 후를 보여 줄 수 있다.
    runs = await list_runs()
    tag = run_tag or (runs[0]["run_tag"] if runs else "")

    board = await _board(tag)
    results = await _results(tag)
    core = await _core_facts()
    core_up = pools.health.core
    # ↑ 순서가 있다: 먼저 실행 목록을 받아서 태그를 정하고(안 주면 최신 것),
    #   그 태그로 판과 결과를 읽고, core 사실들을 읽는다.
    #   `core_up` 은 **_core_facts 를 부른 뒤에** 읽어야 한다. guarded 가 그 호출
    #   과정에서 health 를 갱신하기 때문이다. 먼저 읽으면 한 틱 늦은 값을 쓴다.

    lanes: dict[str, int] = {}
    # ↑ 상태별 과제 수(ready / in_progress / done ...). 칸반 열 머리의 숫자다.
    #   판을 이미 다 읽어 왔으므로 DB 에 다시 묻지 않고 여기서 센다.
    for t in board:
        lanes[t["status"]] = lanes.get(t["status"], 0) + 1

    return {
        "run_tag": tag,
        "runs": runs,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "health": pools.health.as_dict(),
        "scene": _build_scene(core, core_up),
        "board": {"lanes": lanes, "tasks": board},
        "agents": _agent_totals(core),
        "access": _access(core),
        "results": results,
    }
