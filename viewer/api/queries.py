"""The SQL. Kept in one file so the three record shapes are handled in exactly one place.

`run_steps.tool_call` comes in three shapes, and getting this wrong produces numbers
that look plausible and are not:

1. The column is `json`, and many rows hold the JSON literal `null` rather than SQL
   NULL. `tool_call IS NOT NULL` is therefore true for 424 rows that contain no call at
   all. Filter on `::text <> 'null'`.
2. A step may hold **one** call `{server,tool,arguments,result}` or a **batch**
   `{"calls":[…]}`. Reading only the first shape reports `search_concepts` as 0 calls
   when the real figure is 458 — the knowledge-source searches all arrive batched.
3. Rows written before the 2026-08-18 rename carry `ecoxai-*` server names. Left alone,
   the access map lists one server twice.

`llm_call` has the same JSON-null problem: 1,622 rows are `IS NOT NULL`, only 700 hold
a value.

↑ SQL 모음. **세 가지 레코드 모양을 딱 한 군데서만 다루려고** 한 파일에 모아 뒀다.

  `run_steps.tool_call` 은 세 가지 모양으로 들어온다. 이걸 잘못 다루면
  **그럴듯해 보이는데 틀린 숫자**가 나온다:

  1. 이 칼럼은 `json` 타입이고, **SQL NULL 이 아니라 JSON 리터럴 `null`** 을 담은
     행이 많다. 그래서 `tool_call IS NOT NULL` 은 호출이 전혀 없는 424개 행에 대해
     참이 된다. `::text <> 'null'` 로 걸러야 한다.
  2. 한 스텝이 **호출 하나** `{server,tool,arguments,result}` 를 담을 수도 있고
     **묶음** `{"calls":[…]}` 을 담을 수도 있다. 첫 번째 모양만 읽으면
     `search_concepts` 가 0회로 보고된다 — 실제는 458회다. 지식원 검색은 전부
     묶음으로 오기 때문이다.
  3. 2026-08-18 이름 변경 이전에 쓰인 행은 서버 이름이 `ecoxai-*` 다. 그냥 두면
     접근 지도에 **같은 서버가 두 번** 나온다.

  `llm_call` 도 같은 JSON-null 문제가 있다: `IS NOT NULL` 인 행이 1,622개인데
  실제로 값이 든 행은 700개뿐이다.

==============================================================================
 이 파일을 읽는 법
==============================================================================

 무엇을 하는 파일인가
   실행되는 코드가 거의 없다. 전부 **문자열 상수(SQL)** 다. scene.py 가 이 상수들을
   conn.fetch() 에 넣어 쓴다. 위쪽 세 개는 Memstara DB(판·결과표)용, 아래쪽은
   core DB(에이전트·실행이력)용이다.

 상수 목록
   FLAT_CALLS    ★ 두 가지 호출 모양을 한 관계로 펴 주는 CTE. 아래 네 질의의 토대
   --- Memstara DB ---
   RUNS          실행(run_tag)별 과제 수·완료 수·처음/마지막 시각
   BOARD         판 한 판의 모든 과제 행
   RESULTS       결과 표
   --- core DB ---
   AGENT_TOTALS  에이전트별 실행 수·토큰·비용
   OPEN_RUNS     ★ 지금 실제로 돌고 있는 실행 (심장박동 기준)
   ACCESS        에이전트 × 도구별 호출 수 = 접근 지도
   TASK_TOUCHES  ★ 판과 실행을 이어 주는 다리
   LAST_CALL     에이전트별 가장 최근 호출 = 캐릭터가 서 있는 위치
   RECENT_CALLS  최근 몇 초 안의 호출 = 반짝이는 선

 놓치기 쉬운 핵심
   1. 도구 호출을 세는 것은 전부 **FLAT_CALLS 위에** 지어져 있다. 함정 세 개를
      한 번만 처리하기 위해서다. 새 집계를 만들 때도 반드시 이걸 깔고 시작하라.
   2. `$1` 은 asyncpg 의 위치 인자다. 시간 창 값은 파이썬 쪽(scene.py)에서
      문자열로 넘어와 `::interval` 로 바뀐다.
   3. `WHERE ($1 = '' OR run_tag = $1)` 은 "빈 문자열이면 전체"라는 뜻이다.
   4. verify.py 가 **여기와 별개로 쓴 SQL** 로 같은 숫자를 다시 계산해 대조한다.
      이 파일이 퇴보하면 그쪽에서 잡힌다.
==============================================================================
"""

# Flatten both call shapes into one relation. Everything that counts tool calls builds
# on this, so the three traps are dealt with once.
#
# ↑ ★ 이 파일의 심장. 호출의 **두 가지 모양을 하나의 관계로 펴 준다.**
#
#   UNION ALL 위쪽 = 스텝 하나에 호출이 **하나** 든 경우 (`tool_call->>'server'` 가 있음)
#   UNION ALL 아래쪽 = 스텝 하나에 호출이 **여러 개** 든 경우
#                      (`tool_call->'calls'` 배열을 `json_array_elements` 로 풀어헤친다)
#
#   양쪽 모두 `s.tool_call::text <> 'null'` 로 **JSON 리터럴 null 을 먼저 버린다.**
#   `IS NOT NULL` 로는 이게 안 걸러진다 (함정 1번).
#   그리고 `replace(..., 'ecoxai-', 'memstara-')` 로 옛 서버 이름을 접는다 (함정 3번).
#
#   도구 호출을 세는 질의는 전부 이 CTE 를 앞에 붙여 쓴다(`FLAT_CALLS + """..."""`).
#   그래야 함정 세 개를 **한 번만** 처리하고 끝난다.
FLAT_CALLS = """
WITH flat AS (
    SELECT s.run_id,
           s.id                                              AS step_id,
           s.started_at,
           replace(s.tool_call->>'server', 'ecoxai-', 'memstara-') AS server,
           s.tool_call->>'tool'                              AS tool,
           s.tool_call->'arguments'                          AS arguments,
           s.tool_call->>'result'                            AS result
    FROM run_steps s
    WHERE s.tool_call::text <> 'null'
      AND s.tool_call->>'server' IS NOT NULL
    UNION ALL
    SELECT s.run_id,
           s.id,
           s.started_at,
           replace(c->>'server', 'ecoxai-', 'memstara-'),
           c->>'tool',
           c->'arguments',
           c->>'result'
    FROM run_steps s,
         json_array_elements(s.tool_call->'calls') c
    WHERE s.tool_call::text <> 'null'
      AND s.tool_call->'calls' IS NOT NULL
)
"""

# --- Memstara's database ---------------------------------------------------- #

# ↑ 여기부터 세 개(RUNS·BOARD·RESULTS)는 판이 사는 memstara DB 로 나간다.
#   아래 core DB 쪽과 **연결이 완전히 따로**라는 점을 기억할 것 (db.py 참고).

# RUNS — 화면 위쪽 "실행 선택기"에 들어갈 목록.
#   `count(*) FILTER (WHERE status = 'done')` 은 "전체 중 몇 개 끝났나"를 한 번의
#   스캔으로 센다. 마지막 갱신 시각 역순이라 **가장 최근 실행이 맨 위**에 온다 —
#   scene.snapshot 이 run_tag 를 안 받았을 때 [0] 번을 고르는 것이 이 정렬 덕분이다.
RUNS = """
SELECT run_tag,
       count(*)                                    AS tasks,
       count(*) FILTER (WHERE status = 'done')      AS done,
       min(created_at)                             AS first_seen,
       max(updated_at)                             AS last_seen
FROM memstara_blackboard
GROUP BY run_tag
ORDER BY max(updated_at) DESC
"""

# BOARD — 판 한 판의 모든 과제 행. 화면의 카드들이 여기서 나온다.
#   `($1 = '' OR run_tag = $1)` → **빈 문자열을 주면 실행 구분 없이 전부** 가져온다.
#   (/api/task/{id} 가 이 방식을 쓴다. 어느 실행의 과제든 링크로 바로 열려야 하므로.)
#   task_id 순 정렬이라 화면에 뜨는 순서가 매번 같다.
BOARD = """
SELECT task_id, run_tag, trial, perspective, status, task_type, attempts,
       hypothesis, columns, y_column, columns_used, columns_missing, auc,
       feature_importance, interpretation, error,
       claimed_at, created_at, updated_at
FROM memstara_blackboard
WHERE ($1 = '' OR run_tag = $1)
ORDER BY task_id
"""

# RESULTS — 결과 표. 판과 **다른 테이블**이라는 점이 중요하다.
#   판은 *움직이는 것*을, 결과 표는 *찾아낸 것*을 담는다. 그래서 장면에서도
#   서로 다른 장소로 그린다 (stores.py 의 TOOL_STORE 참고).
RESULTS = """
SELECT result_id, task_id, run_tag, trial, perspective, hypothesis,
       columns_used, y_column, auc, interpretation, created_at
FROM memstara_results
WHERE ($1 = '' OR run_tag = $1)
ORDER BY result_id
"""

# --- core's database -------------------------------------------------------- #

# ↑ 여기부터는 core DB (agentic-core-postgres:5453). 에이전트와 실행 이력이 산다.

# AGENT_TOTALS — 에이전트별 누적치.
#   `LEFT JOIN` 이라 **실행이 한 번도 없는 에이전트도 0 으로 나온다** — 목록에서
#   조용히 사라지지 않게 하려는 것이다.
#   `coalesce(..., 0)` 들도 같은 이유: 토큰이나 비용이 NULL 인 실행이 섞여 있어도
#   합계가 통째로 NULL 이 되지 않는다.
#   `a.name LIKE 'memstara%'` 로 이 프로젝트의 에이전트만 남긴다 (판 경로 + 감독관 경로 둘 다).
AGENT_TOTALS = """
SELECT a.name,
       count(r.id)                                                   AS runs,
       count(r.id) FILTER (WHERE r.status = 'completed')             AS completed,
       count(r.id) FILTER (WHERE r.completed_at IS NULL
                             AND r.status NOT IN ('failed'))         AS open_runs,
       coalesce(sum((r.token_usage->>'prompt_tokens')::bigint), 0)   AS prompt_tokens,
       coalesce(sum((r.token_usage->>'completion_tokens')::bigint), 0) AS completion_tokens,
       coalesce(sum(r.cost_estimate), 0)                             AS cost,
       avg((r.pattern_overrides->'reason_act_state'->>'iterations')::float) AS avg_iterations,
       max(r.created_at)                                             AS last_run_at
FROM agents a
LEFT JOIN agent_runs r ON r.agent_id = a.id
WHERE a.name LIKE 'memstara%'
GROUP BY a.name
ORDER BY a.name
"""

# Who is mid-flight right now. This is what makes a character "working".
#
# `completed_at IS NULL` alone is not enough. Six runs sit in `pending` and never
# finished — the oldest is seven days old — because the process that started them was
# killed. Without a freshness bound the ml character stands there "working" forever,
# which is the same trap `reclaim_stalled` fell into: no time condition makes a dead
# thing look alive.
#
# The bound is on the heartbeat, falling back to creation time. Runs heartbeat every
# few seconds (observed: 5s), and a stage takes 20-60s, so $1 seconds of silence means
# the run is gone rather than slow.
#
# ↑ **지금 이 순간 돌고 있는 실행.** 캐릭터를 "일하는 중"으로 만드는 것이 이 질의다.
#
#   `completed_at IS NULL` 만으로는 부족하다. `pending` 상태로 남아 끝나지 않은
#   실행이 여섯 개 있다 — 가장 오래된 것은 7일 전이다 — 그것들을 시작한 프로세스가
#   죽었기 때문이다. 신선도 조건이 없으면 학습 캐릭터가 **영원히 "일하는 중"으로
#   서 있게 된다.** `reclaim_stalled` 가 빠졌던 함정과 똑같다:
#   **시간 조건이 없으면 죽은 것이 살아 보인다.**
#
#   기준은 심장박동(`last_heartbeat_at`)이고, 없으면 생성 시각으로 대신한다.
#   실행은 몇 초마다 심장박동을 남기고(관측값 5초), 한 단계는 20~60초 걸린다.
#   그러니 $1 초 동안 조용하면 느린 게 아니라 **죽은 것**이다.
#   ($1 은 scene.py 의 RUN_ALIVE_SECONDS = 120 이 문자열로 넘어온 값.)
OPEN_RUNS = """
SELECT r.id AS run_id, a.name, r.created_at,
       coalesce(r.last_heartbeat_at, r.created_at) AS alive_at
FROM agent_runs r
JOIN agents a ON a.id = r.agent_id
WHERE r.completed_at IS NULL
  AND r.status NOT IN ('failed')
  AND a.name LIKE 'memstara%'
  AND coalesce(r.last_heartbeat_at, r.created_at)
      > now() - ($1::text || ' seconds')::interval
ORDER BY r.created_at
"""

# Per agent, per window: how many calls. The access map.
#
# ↑ 에이전트별·창문별 호출 수 = **접근 지도**.
#   `FLAT_CALLS +` 로 시작한다는 점에 주목. 여기서 세는 숫자가 화면의 접근 지도
#   그대로이므로, 함정 세 개가 여기서 처리되지 않으면 화면 숫자가 통째로 틀린다.
#   `LIKE 'memstara%'` 는 판 경로와 감독관 경로를 **둘 다** 잡는다 — 감독관 쪽을
#   빼면 실제 호출량이 다섯 배쯤 과소 보고된다 (stores.py 참고).
ACCESS = FLAT_CALLS + """
SELECT a.name, f.server, f.tool, count(*) AS calls,
       max(f.started_at) AS last_at
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE a.name LIKE 'memstara%'
GROUP BY a.name, f.server, f.tool
ORDER BY a.name, count(*) DESC
"""

# The board-to-run bridge. The board carries no run id, but claim_task's *result* does
# carry the task id, and submit_result's *arguments* do. Parsing these is the only way
# to say which agent run handled which task.
#
# ↑ **판과 실행을 이어 주는 다리.** 판에는 run id 가 없다. 하지만
#   `claim_task` 의 *결과(result)* 에 task id 가 실려 있고, `submit_result` 의
#   *인자(arguments)* 에도 실려 있다. 그 둘을 파싱하는 것이 "어느 에이전트 실행이
#   어느 과제를 처리했는가"를 알아낼 **유일한 방법**이다.
#
#   `coalesce(result 쪽, arguments 쪽)` 이 두 자리를 한 칼럼으로 합친다.
#   `ORDER BY f.started_at` 으로 시간순이라, scene._carrying 이 이 목록을 그대로
#   재생하면서 "지금 누가 무엇을 들고 있는지"를 복원할 수 있다 — 다시 정렬할 필요가 없다.
TASK_TOUCHES = FLAT_CALLS + """
SELECT a.name,
       f.run_id,
       f.tool,
       f.started_at,
       coalesce(
           (f.result::json)->>'task_id',
           f.arguments->>'task_id'
       ) AS task_id,
       (f.result::json)->>'run_tag' AS run_tag
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE f.tool IN ('create_task', 'claim_task', 'submit_result')
ORDER BY f.started_at
"""

# The most recent tool call per agent, for "where is this character standing".
#
# ↑ 에이전트별 **가장 최근 호출 하나**. "이 캐릭터가 지금 어디에 서 있나"를 정한다.
#   `DISTINCT ON (a.name)` 은 PostgreSQL 전용 문법으로, ORDER BY 의 앞부분과
#   짝을 이뤄 "이름별 첫 행"만 남긴다. 그래서 `ORDER BY a.name, f.started_at DESC`
#   가 곧 "이름별 가장 최근 것"이 된다. 순서를 바꾸면 조용히 엉뚱한 행이 남는다.
LAST_CALL = FLAT_CALLS + """
SELECT DISTINCT ON (a.name)
       a.name, f.server, f.tool, f.started_at, f.run_id
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE a.name LIKE 'memstara%'
ORDER BY a.name, f.started_at DESC
"""

# Recent calls, for the flashing lines. Window is applied in Python so the value lives
# next to the animation that depends on it.
#
# ↑ 최근 호출들 = 화면에서 **반짝이는 선**.
#   시간 창($1)을 SQL 에 상수로 박지 않고 파이썬에서 넘기는 이유: 그 값이
#   애니메이션 길이(scene.FLASH_SECONDS = 4)와 같아야 하므로, **값을 그것에
#   의존하는 코드 바로 옆에 두려는 것**이다.
#   `LIMIT 40` 은 한꺼번에 폭주해도 화면이 감당할 만큼만 그리려는 안전장치다.
RECENT_CALLS = FLAT_CALLS + """
SELECT a.name, f.server, f.tool, f.started_at
FROM flat f
JOIN agent_runs r ON r.id = f.run_id
JOIN agents a ON a.id = r.agent_id
WHERE f.started_at > now() - ($1::text || ' seconds')::interval
ORDER BY f.started_at DESC
LIMIT 40
"""
