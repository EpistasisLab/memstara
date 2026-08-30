#!/usr/bin/env python3
"""End-to-end checks for the viewer. Run with the viewer up (docker compose up -d).

Every number the screens show is compared against the databases directly, because a
viewer that is merely self-consistent is worth nothing — the whole point is that it can
be trusted about what actually happened.

↑ 뷰어 전체를 끝에서 끝까지 확인하는 검사기. **뷰어를 띄운 상태**에서 돌린다
  (docker compose up -d).

  화면이 보여 주는 모든 숫자를 데이터베이스에 직접 물어서 대조한다. 자기 자신과만
  아귀가 맞는 뷰어는 아무 가치가 없기 때문이다 — 이 프로젝트의 목적은 **실제로
  무슨 일이 있었는지에 대해 믿을 수 있는 화면**을 만드는 것이다.

==============================================================================
 이 파일을 읽는 법
==============================================================================

 무엇을 하는 파일인가
   `/api/snapshot` 을 HTTP 로 한 번 받아 오고, 같은 숫자를 `docker exec psql` 로
   DB 에서 직접 뽑아 와서 하나씩 비교한다. 어긋난 게 있으면 종료 코드 1.
   화면(뷰어)과 진실(DB) 사이에 심판을 하나 두는 셈이다.

 주요 상수·함수
   BASE                    뷰어 웹 주소 (:8070, nginx 가 API 도 같이 서빙)
   EXPECTED_BY_AGENT_SQL   ★ api/queries.py 와 **따로 쓴** 정답 계산용 SQL
   NAIVE_SQL               일부러 **틀리게** 쓴 SQL. 함정이 진짜 처리되는지 증명용
   psql()                  docker exec 로 컨테이너 안에서 psql 실행
   get()                   뷰어 API 를 HTTP 로 호출
   main()                  검사 1~6번을 순서대로 실행

 검사 항목
   1  읽기 전용이 **권한으로** 막혀 있는가 (UPDATE 를 실제로 시도해 본다)
   2  도구별 호출 수가 DB 와 일치하는가 + 아무도 안 쓰는 창문 두 개가 0인가
   3  세 함정(JSON-null / 묶음 호출)이 **진짜로** 처리되고 있는가
   4  옛 `ecoxai-*` 서버 이름이 정규화됐는가
   5  판 행수·AUC·결과 행수가 DB 와 일치하는가
   6  표를 든 캐릭터가 실제 in_progress 인가 + 죽은 실행이 살아 보이지 않는가

 놓치기 쉬운 핵심
   ★ **정답을 파일에 얼려 두지 않는다.** 예전 판본은 기대 숫자를 하드코딩했다가,
     파이프라인이 한 번 더 돌자 열 개 검사가 깨졌다 — **멀쩡한 뷰어를 고장 났다고
     보고한 것이다.** 그래서 기대값을 그때그때 SQL 로 계산한다.
   ★ 그 SQL 은 api/queries.py 와 **독립적으로 따로 썼다.** 같은 함정 세 개를 다루되
     표현이 다르다. API 쪽이 퇴보하면 두 계산이 어긋나면서 잡힌다.
     (같은 SQL 을 복사해 왔다면 둘이 똑같이 틀려도 통과했을 것이다.)
   ★ 3번 검사는 특이하다. **"순진한 집계와 결과가 달라야" 통과한다.** 같으면
     함정 처리가 아무 일도 안 하고 있다는 뜻이고, 그러면 나중에 퇴보해도 못 잡는다.
==============================================================================
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

BASE = "http://localhost:8070"
# ↑ 8070 은 웹(nginx) 쪽. nginx 가 /api 를 8071 의 API 컨테이너로 넘겨 주므로,
#   여기 하나만 알면 화면이 실제로 받는 것과 똑같은 경로로 검사할 수 있다.

# Deliberately no frozen expected totals. They go stale the moment the pipeline runs
# again — an earlier version of this file hardcoded them and then failed ten checks
# because a run had happened, reporting a correct viewer as broken.
#
# Instead the expected numbers are computed here with SQL written independently of
# api/queries.py. Same three traps handled, different expression: if the API's version
# regresses, the two disagree.
# The same count restricted to the agents the viewer shows, joined the long way round.
#
# ↑ **기대 정답을 파일에 얼려 두지 않는 이유.**
#   파이프라인이 한 번 더 돌면 그 순간 낡아 버린다. 예전 판본은 실제로 총계를
#   하드코딩했다가 검사 열 개가 깨졌다 — 실행이 한 번 더 있었다는 이유만으로
#   **멀쩡한 뷰어를 고장 났다고 보고**했다.
#
#   대신 기대 숫자를 여기서 SQL 로 계산한다. 그런데 그 SQL 은 api/queries.py 와
#   **독립적으로 따로 쓴 것**이다. 같은 함정 세 개를 다루되 표현이 다르다:
#   API 쪽이 퇴보하면 두 계산이 어긋나면서 드러난다.
#   (여기서 queries.FLAT_CALLS 를 import 해서 썼다면, 둘이 똑같이 틀려도 통과한다.)
#
#   아래 SQL: 뷰어가 보여 주는 에이전트로 범위를 좁히되, 조인을 빙 둘러서 간다
#   (run_steps → agent_runs → agents).
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
# ↑ **일부러 틀리게 쓴 SQL.** 순진한 독자가 짰을 법한 버전이다:
#   json-null 필터도 없고, 묶음(calls) 모양도 안 본다.
#
#   왜 이런 걸 남겨 두나? 함정 처리가 **진짜로 일하고 있는지 증명**하기 위해서다.
#   이 순진한 집계 결과가 올바른 결과와 **달라야** 검사를 통과한다. 만약 둘이
#   같다면, 함정 처리 코드가 아무 효과도 못 내고 있다는 뜻이고 — 그러면 나중에
#   그 코드가 사라져도 아무도 눈치채지 못한다.
#   `coalesce(..., '(없음)')` 은 JSON-null 행이 몇 개나 잘못 세어지는지 드러낸다.
NAIVE_SQL = """
SELECT tool || '=' || n FROM (
    SELECT coalesce(r.tool_call->>'tool', '(없음)') AS tool, count(*) AS n
    FROM run_steps r
    JOIN agent_runs ar ON ar.id = r.run_id
    JOIN agents a ON a.id = ar.agent_id
    WHERE r.tool_call IS NOT NULL AND a.name LIKE 'memstara%'
    GROUP BY 1
) x ORDER BY tool
"""


def psql(container: str, user: str, db: str, q: str) -> str:
    # ↑ 컨테이너 안에서 psql 을 돌려 결과를 문자열로 받는다.
    #   `-tAc` = 헤더 없이(-t), 정렬 안 하고(-A), 명령 하나만(-c). 그래서 출력이
    #   파싱하기 쉬운 순수 값이 된다.
    #   **주의:** 실패해도 예외를 던지지 않고 빈 문자열이 돌아온다(stdout 만 본다).
    #   그러면 비교가 어긋나면서 검사가 실패하므로 결과적으로는 드러난다.
    #   뷰어와 달리 여기서는 **관리자 계정**으로 붙는다 — 진실을 봐야 하기 때문이다.
    return subprocess.run(
        ["docker", "exec", container, "psql", "-U", user, "-d", db, "-tAc", q],
        capture_output=True, text=True,
    ).stdout.strip()


def get(path: str) -> dict:
    # ↑ 뷰어 API 를 HTTP 로 부른다. 브라우저와 완전히 같은 경로로 받아야
    #   "화면이 실제로 보는 것"을 검사하는 것이 된다.
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.load(r)


def main() -> int:
    # ↑ 검사 1~6번을 차례로 돈다. **처음 실패에서 멈추지 않는다** — 어긋난 것을
    #   전부 모아서 마지막에 한꺼번에 보여 준다.
    ok: list[str] = []
    bad: list[str] = []

    def chk(label: str, cond: bool, detail: str = "") -> None:
        # ↑ 조건이 참이면 ok 목록에, 거짓이면 bad 목록에 넣는다. detail 은 **어긋났을
        #   때 무엇을 봐야 하는지**를 담는다 (화면 값 / DB 값을 나란히).
        (ok if cond else bad).append(f"{label}  {detail}")

    snap = get("/api/snapshot")
    # ↑ 스냅샷을 **한 번만** 받아서 아래 모든 검사가 그 하나를 쓴다.
    #   검사마다 새로 받으면 그 사이에 파이프라인이 움직여서, 뷰어는 멀쩡한데
    #   검사끼리 어긋나는 헛소동이 난다.
    tag = snap["run_tag"]

    # 1 — read-only is a permission, not a promise.
    #
    # ↑ 1번 — 읽기 전용은 **약속이 아니라 권한**이다.
    #   "우리 코드는 UPDATE 를 안 씁니다"는 증명이 아니다. 그래서 실제로 UPDATE 를
    #   쏴 보고 **거부당하는지** 확인한다. 뷰어 계정(memstara_viewer)으로 직접 붙어서.
    denied = subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD=viewer", "memstara-postgres", "psql",
         "-U", "memstara_viewer", "-d", "memstara", "-c",
         "UPDATE memstara_blackboard SET status='ready'"],
        capture_output=True, text=True,
    ).stderr
    chk("1 읽기 전용", "permission denied" in denied, denied.strip()[:60])
    # ↑ stderr 에 "permission denied" 가 있어야 통과. 성공했다면 큰일이다.

    # 2/3/4 — the flattening, checked against independently written SQL.
    #
    # ↑ 2/3/4번 — 호출 펴기(flattening)를, **따로 쓴 SQL** 로 검산한다.
    #   먼저 화면 쪽 숫자를 도구별로 합산해 totals 를 만든다. 접근 지도의 행은
    #   에이전트 × 도구 단위라서, 도구 단위로 다시 더해야 DB 집계와 결이 맞는다.
    totals: dict[str, int] = {}
    for row in snap["access"]["rows"]:
        totals[row["tool"]] = totals.get(row["tool"], 0) + row["calls"]

    raw = psql("agentic-core-postgres", "agentic", "agentic_core", EXPECTED_BY_AGENT_SQL)
    # ↑ psql 출력이 `도구이름=숫자` 한 줄씩이라 `split("=")` 로 바로 dict 이 된다.
    #   먼저 **도구 목록 자체**가 같은지 보고(집합 비교), 그 다음 개수를 하나씩 본다.
    #   목록이 어긋나면 "화면에만 있는 것 / DB에만 있는 것"을 양쪽으로 찍어 준다.
    expected = dict(
        (k, int(v)) for k, v in (line.split("=") for line in raw.splitlines() if "=" in line)
    )
    chk("2 도구 종류 수", set(totals) == set(expected),
        f"화면만 {set(totals) - set(expected)} / DB만 {set(expected) - set(totals)}")
    for tool, want in sorted(expected.items()):
        chk(f"2 도구 {tool}", totals.get(tool) == want, f"화면 {totals.get(tool)} / DB {want}")

    # 3 — prove the traps are handled: a naive count must NOT agree, or the fixes are
    # doing nothing and would not catch a regression either.
    #
    # ↑ 3번 — 함정 처리가 **실제로 효과가 있는지** 증명한다.
    #   순진한 집계가 정답과 **일치하면 안 된다.** 일치한다면 처리 코드가 아무
    #   일도 안 하고 있다는 뜻이고, 그렇다면 그 코드가 나중에 사라져도 못 잡는다.
    #   - JSON-null: 순진한 쪽에는 "(없음)" 항목이 나오고 화면에는 없어야 한다.
    #   - 묶음 호출: 순진한 search_concepts 개수가 정답보다 **작아야** 한다.
    naive_raw = psql("agentic-core-postgres", "agentic", "agentic_core", NAIVE_SQL)
    naive = dict(
        (k, int(v)) for k, v in (line.split("=") for line in naive_raw.splitlines() if "=" in line)
    )
    chk("3 JSON-null 이 호출로 안 세어짐", "(없음)" in naive and "(없음)" not in totals,
        f"순진한 집계의 빈 항목 {naive.get('(없음)')}건")
    chk("3 묶음 호출을 놓치지 않음", naive.get("search_concepts", 0) < expected.get("search_concepts", 0),
        f"순진 {naive.get('search_concepts', 0)} < 올바름 {expected.get('search_concepts')}")
    servers = {r["server"] for r in snap["access"]["rows"]}
    # ↑ 4번 — 옛 이름 정규화. `ecoxai` 로 시작하는 서버가 하나도 남아 있으면 안 된다.
    #   남아 있으면 접근 지도에 같은 서버가 두 줄로 나뉘어 나온다.
    chk("4 옛 이름 정규화", not any(s.startswith("ecoxai") for s in servers), str(sorted(servers)))

    # The two windows no agent holds. Empty here is the correct picture, not a gap.
    #
    # ↑ 아무 에이전트도 잡지 않는 창문 두 개. **여기가 0인 것이 옳은 그림이지,
    #   빠진 데이터가 아니다.** `read_board` 는 구동 스크립트 몫이고 `count_waiting`
    #   은 아무도 안 쓴다. 이걸 검사해 두면 나중에 "왜 0이지?" 하고 없는 버그를
    #   쫓는 일이 없어진다.
    windows = {w["tool"]: w for w in snap["access"]["windows"]}
    chk("2 read_board 은 스크립트 몫", windows["read_board"]["calls"] == 0)
    chk("2 count_waiting 은 아무도 안 씀", windows["count_waiting"]["calls"] == 0)

    # 5 — the board matches the database it came from.
    #
    # ↑ 5번 — 판이 그 판을 가져온 DB 와 일치하는가.
    #   행 수만 보지 않고 **AUC 값들을 task_id 순으로 이어 붙여 통째로 비교**한다.
    #   행 수만 맞으면 값이 어긋나거나 순서가 섞인 것을 놓치기 때문이다.
    #   (`string_agg(... ORDER BY task_id)` 와 화면 쪽 join 이 같은 순서를 쓴다.)
    n = psql("memstara-postgres", "memstara", "memstara",
             f"SELECT count(*) FROM memstara_blackboard WHERE run_tag='{tag}'")
    chk("5 판 행수", str(len(snap["board"]["tasks"])) == n, f"화면 {len(snap['board']['tasks'])} / DB {n}")
    aucs = psql("memstara-postgres", "memstara", "memstara",
                f"SELECT string_agg(auc::text, ',' ORDER BY task_id) FROM memstara_blackboard "
                f"WHERE run_tag='{tag}'")
    chk("5 AUC", ",".join(str(t["auc"]) for t in snap["board"]["tasks"]) == aucs, aucs)
    r = psql("memstara-postgres", "memstara", "memstara",
             f"SELECT count(*) FROM memstara_results WHERE run_tag='{tag}'")
    chk("5 결과 행수", str(len(snap["results"])) == r)

    # 6 — a character holding a card must be holding a card the board agrees is held.
    #
    # ↑ 6번 — 표를 들고 있는 캐릭터는, **판도 들려 있다고 인정하는** 표를 들고 있어야 한다.
    #   장면의 carrying 은 도구 호출 기록을 재생해서 얻은 값이고(scene._carrying),
    #   판의 in_progress 는 DB 가 직접 아는 값이다. 두 경로가 만나야 한다.
    #   부분집합(⊆)으로 비교하는 것이 맞다 — 판에 in_progress 인데 아직 아무 캐릭터도
    #   못 그린 경우는 있을 수 있지만, 그 반대는 있으면 안 된다.
    #   아무도 안 들고 있으면 그냥 통과다 (파이프라인이 안 돌고 있으면 정상).
    held = {a["carrying"] for a in snap["scene"]["agents"] if a["carrying"] is not None}
    if held:
        inprog = psql("memstara-postgres", "memstara", "memstara",
                      f"SELECT string_agg(task_id::text, ',' ORDER BY task_id) "
                      f"FROM memstara_blackboard WHERE run_tag='{tag}' AND status='in_progress'")
        db = set(inprog.split(",")) if inprog else set()
        chk("6 표 든 캐릭터", {str(h) for h in held} <= db, f"장면 {held} / DB {db}")
    else:
        chk("6 표 든 캐릭터", True, "지금 아무도 안 들고 있음 (실행 중이 아니면 정상)")

    # A dead run must not leave a character permanently "working".
    #
    # ↑ 죽은 실행이 캐릭터를 **영원히 "일하는 중"으로 남겨 두면 안 된다.**
    #   한 시간 넘게 pending 인 실행이 실제로 있는 상태에서(= 함정이 존재하는 상태),
    #   화면에 working 인 캐릭터가 하나도 없어야 통과다.
    #   이게 scene.RUN_ALIVE_SECONDS / queries.OPEN_RUNS 의 시간 창이 일하고 있다는 증거다.
    #   (오래된 pending 이 0건이면 이 검사는 증명력이 없어 실패로 잡히도록 되어 있다.)
    stale = psql("agentic-core-postgres", "agentic", "agentic_core",
                 "SELECT count(*) FROM agent_runs WHERE completed_at IS NULL "
                 "AND status='pending' AND created_at < now() - interval '1 hour'")
    working = [a["label"] for a in snap["scene"]["agents"] if a["state"] == "working"]
    chk("6 죽은 실행이 살아 보이지 않음", int(stale) > 0 and not working,
        f"오래된 pending {stale}건인데 working {working}")

    chk("장소 5곳", len(snap["scene"]["places"]) == 5)
    # ↑ 장면의 뼈대. 장소 5곳·캐릭터 5명이 항상 나와야 한다. 단계가 늘었는데
    #   stores.PLACES/HOME 에 자리를 안 만들면 여기서 걸린다.
    chk("캐릭터 5명", len(snap["scene"]["agents"]) == 5)
    chk("두 DB 응답", snap["health"]["memstara"]["up"] and snap["health"]["core"]["up"])

    print(f"  통과 {len(ok)} / 어긋남 {len(bad)}")
    # ↑ 통과한 것은 개수만, 어긋난 것은 이유까지 전부 출력한다.
    #   종료 코드 1 이면 CI 나 셸에서 그대로 실패로 잡힌다.
    for b in bad:
        print("   ✗", b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
