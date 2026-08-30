"""Memstara Viewer — read-only HTTP surface over the two databases.

One polling endpoint on purpose. Six screens each fetching their own slice would send
six requests every two seconds and could show mutually inconsistent states; `/api/
snapshot` returns one coherent object and the frontend selects from it.

Nothing here writes. The account it connects with (`memstara_viewer`) holds SELECT and
nothing else, so read-only is enforced by the database rather than by this code being
careful — verified: UPDATE and DELETE are refused.

↑ Memstara 뷰어 — 두 데이터베이스 위에 얹은 **읽기 전용 HTTP 창구**.

  폴링 엔드포인트를 **일부러 하나만** 뒀다. 화면 여섯 개가 각자 자기 몫만 가져가면
  2초마다 요청이 여섯 번 나가고, 게다가 **서로 어긋난 상태**를 동시에 보여 줄 수
  있다 (한 요청은 갱신 전, 다른 요청은 갱신 후 데이터를 받는 식). `/api/snapshot`
  은 **한 덩어리의 일관된 객체**를 돌려주고, 프론트엔드는 거기서 골라 쓴다.

  여기서는 아무것도 쓰지 않는다. 접속 계정 `memstara_viewer` 는 SELECT 권한만
  갖고 있으므로, 읽기 전용은 **이 코드가 조심해서가 아니라 DB 가 막아서** 지켜진다.
  실제로 확인했다 — UPDATE·DELETE 는 거부된다.

==============================================================================
 이 파일을 읽는 법
==============================================================================

 무엇을 하는 파일인가
   FastAPI 진입점. 실제 계산은 전부 scene.py 가 하고, 이 파일은 HTTP 껍데기만
   담당한다 — 경로 네 개, CORS 설정, 그리고 종료할 때 풀 닫기.
   Docker 로 뜰 때 `memstara-viewer-api` 컨테이너의 :8071 이 이 앱이다.

 엔드포인트 네 개
   GET /api/health          두 DB 중 어디가 응답하는지. 컨테이너 헬스체크로도 쓴다
   GET /api/runs            실행(run_tag) 목록. 화면 위쪽 선택기용
   GET /api/snapshot        ★ 주력. 2초마다 불리며 여섯 화면이 쓸 것을 전부 담는다
   GET /api/task/{task_id}  과제 하나 + 그 과제를 건드린 에이전트 실행 이력

 놓치기 쉬운 핵심
   1. **lifespan 에서 풀을 미리 만들지 않는다.** DB 하나가 죽어 있어도 뷰어는 떠야
      하기 때문이다. 종료할 때 닫기만 한다.
   2. 화면이 여섯인데 엔드포인트가 하나인 이유는 성능이 아니라 **일관성**이다.
   3. `allow_methods=["GET"]` — 읽기 전용이라는 사실이 CORS 설정에도 한 번 더 적혀 있다.
   4. `/api/task` 의 이력(trail)은 판에서 못 읽는다. 판에는 run id 가 없기 때문에
      도구 호출 기록을 되짚어 재구성한다.
==============================================================================
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent))
# ↑ 이 디렉터리를 import 경로에 넣어서 `import queries` 처럼 **평평하게** 쓸 수 있게
#   한다. 아래 import 들에 붙은 `# noqa: E402` 는 "이 줄 다음에 import 가 오는 건
#   알고 있고 의도한 것"이라는 표시다 (이 sys.path 조작이 먼저여야 하므로).

import queries  # noqa: E402
import scene  # noqa: E402
import stores  # noqa: E402
from db import pools  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    # ↑ 앱의 수명 주기. `yield` 앞이 시작할 때, 뒤가 끝날 때 하는 일이다.
    # Pools are created on first use, not here: the viewer has to start even when a
    # database is down. That is the whole point of keeping the two stores apart.
    #
    # ↑ 풀은 **여기서 만들지 않는다.** 처음 질의할 때 만들어진다. DB 하나가 죽어
    #   있어도 뷰어는 떠야 하기 때문이다 — 두 저장소를 갈라 놓은 이유가 그것이다.
    #   여기서 미리 붙이면 core DB 가 꺼져 있을 때 컨테이너가 부팅에 실패한다.
    #   그래서 시작할 때 할 일은 없고(바로 yield), 끝날 때 닫기만 한다.
    yield
    await pools.close()


app = FastAPI(title="Memstara Viewer", lifespan=lifespan)
# ↑ 앱 본체. 이 아래로는 전부 GET 뿐이다.

# The dev server runs on another port; in Docker nginx serves both from one origin and
# this becomes a no-op.
#
# ↑ 개발 중에는 Vite 개발 서버(5173)가 다른 포트에서 돌기 때문에 CORS 허용이 필요하다.
#   Docker 로 띄우면 nginx 가 웹과 API 를 **같은 출처**로 서빙하므로 이 설정은
#   아무 일도 하지 않게 된다. 환경변수 `VIEWER_CORS` 로 목록을 갈아끼울 수 있다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("VIEWER_CORS", "http://localhost:5173").split(",") if o],
    allow_methods=["GET"],
    # ↑ GET 만 허용. 읽기 전용이라는 사실이 DB 권한, 계정, 그리고 여기까지
    #   **세 겹으로** 적혀 있는 셈이다.
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Which stores answered. Cheap enough to be the container healthcheck."""
    # ↑ 어느 저장소가 응답했는가. 컨테이너 헬스체크로 써도 될 만큼 가볍다.
    #
    #   가짜로 True 를 돌려주지 않고 **양쪽에 실제로 질의를 한 번씩 날려 본다.**
    #   그래야 "떠 있긴 한데 DB 를 못 읽는" 상태가 건강함으로 둔갑하지 않는다.
    #   `definitions_from_pipeline` 은 stores.py 가 진짜 파이프라인 정의를 import
    #   했는지(True), 아니면 베껴 둔 대체 표를 쓰고 있는지(False)를 알려 준다.
    await scene.list_runs()  # touches memstara
    await scene._core_facts()  # touches core
    return {
        "health": pools.health.as_dict(),
        "definitions_from_pipeline": stores.IMPORTED_FROM_PIPELINE,
    }


@app.get("/api/runs")
async def runs() -> dict[str, Any]:
    # ↑ 실행 태그 목록만. 화면 위쪽의 실행 선택기가 이걸 쓴다.
    #   snapshot 안에도 같은 목록이 들어 있지만, 선택기만 새로 고치고 싶을 때를 위해
    #   따로 열어 뒀다.
    return {"runs": await scene.list_runs()}


@app.get("/api/snapshot")
async def snapshot(run_tag: str | None = Query(default=None)) -> dict[str, Any]:
    # ↑ ★ 주력 엔드포인트. 프론트엔드가 2초마다 이것 하나만 부른다.
    #   `run_tag` 를 안 주면 scene 이 가장 최근 실행을 알아서 고른다.
    #   계산은 전부 scene.snapshot 안에 있고 여기는 그냥 넘겨주기만 한다 —
    #   해석이 한 군데에만 있어야 화면끼리 말이 어긋나지 않는다.
    return await scene.snapshot(run_tag)


@app.get("/api/task/{task_id}")
async def task(task_id: int) -> dict[str, Any]:
    """One task with the agent runs that touched it, in order.

    The board holds no run ids, so the trail is rebuilt from the board windows —
    create_task / claim_task / submit_result carry the task id in their payloads.

    ↑ 과제 하나와, 그 과제를 건드린 에이전트 실행들을 시간순으로.

    판에는 run id 가 아예 없다. 그래서 이력(trail)은 **판의 창문들**로부터 되짚어
    재구성한다 — create_task / claim_task / submit_result 가 자기 payload 안에
    task id 를 싣고 다니기 때문에 그것으로 이어 붙일 수 있다.
    """
    board = await scene._board("")
    # ↑ 빈 문자열은 "모든 실행"을 뜻한다(queries.BOARD 의 `$1 = '' OR ...`).
    #   특정 실행으로 좁히지 않는 이유: 과제 상세는 어느 실행 것이든 링크로 바로
    #   열릴 수 있어야 하기 때문이다.
    found = next((t for t in board if t["task_id"] == task_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} is not on the board")
    # ↑ 없는 과제는 빈 껍데기가 아니라 **404** 로 명확히 알린다.
    #   빈 화면을 보여 주면 "데이터가 아직 안 왔나?"와 구분이 안 된다.

    core = await scene._core_facts()
    trail = [{
        "agent": stores.AGENT_BY_NAME.get(t["name"], t["name"]),
        "agent_label": stores.AGENT_LABELS.get(stores.AGENT_BY_NAME.get(t["name"], ""), t["name"]),
        "tool": t["tool"],
        "run_id": str(t["run_id"]),
        "at": scene._iso(t["started_at"]),
    } for t in core["touches"] if t.get("task_id") and int(t["task_id"]) == task_id]
    # ↑ 위 trail: core["touches"] 는 이미 시간순(queries.TASK_TOUCHES 의 ORDER BY)이라
    #   여기서 다시 정렬하지 않는다. task_id 는 JSON 에서 나와 문자열일 수 있으므로
    #   `int()` 로 맞춰서 비교한다 — 이걸 빼면 이력이 통째로 비어 보인다.
    #
    # ↑ 아래 return 이 health 를 같이 실어 보내는 이유: core DB 가 죽어서 이력이
    #   비었을 때, 화면이 "이력 없음"과 "core 를 못 읽음"을 구별할 수 있어야 한다.

    return {"task": found, "trail": trail, "health": pools.health.as_dict()}
