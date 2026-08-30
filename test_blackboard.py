#!/usr/bin/env python3
"""Prove that two agents cannot take the same task.

This is the gate the design document put before everything else. If claiming is not
atomic, two data agents eventually work the same row, and every strange result after
that is ambiguous — was it the race, or the prompt? Settling it here means later
failures have one fewer explanation.

The tools are called as plain functions, not over MCP. The question is whether the
database statement is safe under concurrency; a server round trip would only add noise.

Usage::

    set -a && . ./.env && set +a          # in the core repo
    python test_blackboard.py


==============================================================================
 이 파일을 읽는 법
==============================================================================

 **판 테이블**(blackboard)이 제대로 동작하는지 확인하는 검사 스크립트다. 판이란
 할 일을 적어 두는 데이터베이스 표이고, 여러 에이전트가 여기서 일을 하나씩
 집어 간다. 이 파일은 그 집어 가기가 안전한지를 실제로 돌려 본다.

 함수는 셋이다.

   cleanup()               검사용 표시(run_tag)가 붙은 줄을 지운다. 앞뒤로 두 번 부른다
   ok(passed, label, ...)  한 항목의 통과 여부를 한 줄로 찍고 그 결과를 돌려준다
   main()                  검사 본체. 아래 순서대로 흐른다

 main() 이 확인하는 것, 순서대로:

   ⓪ 질문 은행에 질문을 담는다 — 태그 없는 것은 거절되고, 같은 것은 한 번만 담긴다
   ① 대기 중인 일 8개를 만든다 (⓪ 에서 담은 질문 번호를 달고)
   ② **관문** — 12명이 동시에 집으러 달려들었을 때 겹치지 않는가
   ③ 집어 간 일에 앞 단계가 남긴 것(결과변수·컬럼)이 실려 있는가
   ④ 집기 → 써넣기 → 다음 단계로 넘어가기가 이어지는가
   ⑤ 안 집고 써넣으려 하면 막히는가
   ⑥ 다 끝난 것이 결과 표에 쌓이는가, 남은 개수를 정확히 세는가
   ⑦ 성적이 질문 은행으로 되먹여지는가, 판을 치워도 은행이 남는가

 놓치기 쉬운 것:

   · **②가 이 파일의 존재 이유다.** 집어 가기가 원자적이지 않으면 데이터 담당
     에이전트 둘이 언젠가 같은 줄을 잡고, 그 뒤에 나오는 이상한 결과는 전부
     설명이 둘이 된다 — 경합 때문인가, 프롬프트 때문인가. 여기서 매듭지어 두면
     나중의 실패에 설명 하나가 줄어든다.
   · 도구를 MCP 서버 너머가 아니라 **그냥 파이썬 함수로** 부른다. 묻는 것은
     데이터베이스 문장이 동시성 아래서 안전한가이지 서버 왕복이 아니라서,
     서버를 끼우면 잡음만 는다.
   · 이 검사는 **진짜 데이터베이스에 쓴다.** 그래서 시작과 끝에서 cleanup() 이 제 것만
     골라 지운다.
   · **질문 은행(memstara_questions)은 판과 달리 실행을 넘어 쌓인다.** 그래서 cleanup()
     은 이 표에서도 run_tag 가 아니라 origin_run 이 제 것인 줄만 골라 지운다. 통째로
     지우면 다른 실행이 쌓아 둔 질문까지 없어진다.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter

import tools_blackboard as bb   # 판을 다루는 도구들 — 서버 없이 직접 부른다

# 이 검사가 만든 줄에만 붙이는 표시. 같은 표에 들어 있는 진짜 실행 기록을
# 건드리지 않고 이 검사 것만 골라 지울 수 있게 해 준다.
RUN_TAG = "test_atomicity"


async def cleanup() -> None:
    """이 검사가 만든 줄만 지운다. 시작할 때와 끝날 때 각각 한 번씩 부른다.

    시작할 때도 지우는 이유: 앞선 검사가 중간에 죽었으면 찌꺼기가 남아 있고,
    그러면 "대기 8개" 를 세는 항목이 8이 아닌 수를 보게 된다. 검사는 언제 돌려도
    같은 자리에서 출발해야 한다.

    질문 은행만 조건이 다르다. 그 표에는 run_tag 가 없다 — 실행을 넘어 쌓이는
    전역 표라서 일부러 안 두었다. 그래서 "누가 냈나"(origin_run) 로 골라 지운다.
    통째로 지우면 다른 실행이 쌓아 둔 질문까지 같이 없어진다.
    """
    import asyncpg

    conn = await asyncpg.connect(bb._dsn())
    try:
        await conn.execute("DELETE FROM memstara_results WHERE run_tag = $1", RUN_TAG)
        await conn.execute("DELETE FROM memstara_blackboard WHERE run_tag = $1", RUN_TAG)
        await conn.execute("DELETE FROM memstara_questions WHERE origin_run = $1", RUN_TAG)
    finally:
        await conn.close()


def ok(passed: bool, label: str, detail: str = "") -> bool:
    """한 항목의 결과를 한 줄로 찍고, 그 통과 여부를 그대로 돌려준다.

    돌려주는 값을 main() 이 목록에 쌓아 두었다가 마지막에 "몇 개 중 몇 개 통과"
    를 낸다. 찍기와 세기를 한 함수로 묶어 둔 것이라, 찍었는데 세는 것을 잊는 일이
    생기지 않는다.
    """
    print(f"  {'OK  ' if passed else 'FAIL'} {label}" + (f"  — {detail}" if detail else ""))
    return passed


async def main() -> int:
    """검사 본체. 위 「이 파일을 읽는 법」의 ①~⑥ 이 여기 순서대로 있다."""
    results: list[bool] = []   # 항목별 통과 여부를 쌓아 둔다
    await cleanup()            # 앞선 검사의 찌꺼기를 먼저 치운다

    # ---- 질문 은행에 먼저 담는다 ---------------------------------------
    #
    # 판보다 이것이 앞이다. 시행이 생기려면 먼저 물어볼 것이 있어야 하기 때문이다.
    # 지금까지는 물어볼 것이 코드에 20개 박혀 있었고(`pipeline_core.PERSPECTIVES`),
    # 그래서 "왜 이 시행이 존재했는가" 를 나중에 되물을 곳이 없었다.
    QTEXT = f"from a psychiatric-comorbidity perspective ({RUN_TAG})"
    QTAGS = ["psychiatric", "sud"]
    # 한 번에 둘을 낸다 — 태그가 있는 것과 없는 것. 없는 쪽이 거절되어야 한다.
    #
    # 이것이 형식 검사가 아닌 이유: 코퍼스가 답할 수 없는 질문을 받아도 가설 담당은
    # 답을 낸다. 근거를 못 찾았다는 결말이 그 단계에 없기 때문이다. 그래서 근거를
    # 지어낸다. 태그를 여기서 강제하는 것이 그것을 **불가능하게** 만드는 자리다.
    p1 = json.loads(await bb.propose_questions(json.dumps([
        {"text": QTEXT, "okf_tags": QTAGS, "rationale": "코퍼스 333편이 이 갈래에 몰려 있다"},
        {"text": f"태그 없이 낸 질문 ({RUN_TAG})", "okf_tags": [], "rationale": ""},
    ], ensure_ascii=False), origin_run=RUN_TAG, origin_wave=0))
    results.append(ok(len(p1.get("added", [])) == 1 and len(p1.get("rejected", [])) == 1,
                      "태그 있는 질문만 은행에 담긴다 (근거 없는 질문은 거절)",
                      f"담김 {len(p1.get('added', []))} · 거절 {len(p1.get('rejected', []))}"))
    QID = p1["added"][0]["question_id"]

    # 같은 질문을 대소문자와 앞뒤 공백만 바꿔 다시 낸다. 사람이 보기에 같은 질문은
    # 은행에도 같은 질문이어야 한다 — 안 그러면 다음 실행이 이미 물어본 것을
    # 못 알아보고 계속 다시 묻는다. 그것은 진전처럼 보이지만 진전이 아니다.
    p2 = json.loads(await bb.propose_questions(json.dumps([
        {"text": "  " + QTEXT.upper() + "  ", "okf_tags": QTAGS},
    ], ensure_ascii=False), origin_run=RUN_TAG, origin_wave=1))
    results.append(ok(not p2.get("added") and len(p2.get("duplicates", [])) == 1,
                      "이미 물어본 질문은 다시 담기지 않는다 (대소문자·공백 무시)",
                      f"담김 {len(p2.get('added', []))} · 중복 {len(p2.get('duplicates', []))}"))

    # 낸 것이 그대로 돌아오는가. 태그와 근거가 왕복하지 못하면 질문 담당은 다음
    # 파도에서 "무엇을 근거로 물었는지" 를 못 보고, 되먹임이 거기서 끊긴다.
    bank = json.loads(await bb.read_questions(limit=200)).get("questions", [])
    mine = next((q for q in bank if q.get("question_id") == QID), None)
    results.append(ok(mine is not None
                      and mine.get("okf_tags") == QTAGS
                      and mine.get("rationale", "").startswith("코퍼스")
                      and mine.get("times_used") == 0,
                      "질문 은행이 태그와 근거를 그대로 돌려준다",
                      f"태그 {(mine or {}).get('okf_tags')} · 쓰인 횟수 {(mine or {}).get('times_used')}"))

    # ---- 판을 채운다 -------------------------------------------------
    #
    # 관점과 가설은 내용이 중요하지 않아 번호만 붙인다. 확인하려는 것은 판의
    # 동작이지 가설의 품질이 아니다. 컬럼과 결과변수는 실제 이름을 쓴다 — 뒤에서
    # 그것이 그대로 실려 돌아오는지 확인하기 때문이다.
    N = 8
    # One of these two carries a comma INSIDE the name — 158 of the cohort's 1,393
    # columns do. It is here so the board's round trip is checked against the case
    # that used to break it, not only against names a split would survive.
    COLUMNS = ["CURRENT_AGE", "LAB__HDL CHOLESTEROL, DIRECT"]
    # 왜 이 컬럼을 골랐는지의 근거. 이것이 끝까지 살아남는지가 아래 두 항목이다.
    OKF_IDS = ["anchors/hiv", "mechanisms/comorbidity/mp010-comorbidity-psychiatric"]
    for i in range(N):
        r = json.loads(await bb.create_task(RUN_TAG, i, f"관점 {i}", f"가설 {i}",
                                            COLUMNS, "HIV_DETECTABLE",
                                            okf_concept_ids=OKF_IDS,
                                            question_id=QID))
        assert "task_id" in r, r
    results.append(ok(True, f"대기 중인 일 {N}개를 만들었다"))

    # ---- ⭐ 관문: 동시에 집어도 겹치지 않는가 --------------------------
    #
    # More claimers than tasks on purpose: the surplus must come back empty rather
    # than duplicate somebody else's row.
    #
    # ↑ 일보다 집는 쪽을 **일부러 더 많이** 던진다(8개에 12명). 남는 4명은 빈 손으로
    #   돌아와야지, 남의 줄을 하나 더 집어서는 안 된다. 딱 맞게 던지면 겹침이
    #   있어도 숫자상 들키지 않을 수 있다.
    #
    #   asyncio.gather 는 12번의 집기를 **동시에** 띄운다. 하나씩 차례로 부르면
    #   경합 자체가 일어나지 않아 이 검사는 아무것도 확인하지 못한다.
    claims = await asyncio.gather(*[bb.claim_task("data") for _ in range(N + 4)])
    got = [json.loads(c) for c in claims]
    ids = [g["task_id"] for g in got if g.get("task_id") is not None]   # 집힌 것
    empty = [g for g in got if g.get("task_id") is None]                # 빈 손
    dupes = [i for i, n in Counter(ids).items() if n > 1]               # 둘이 집은 것

    results.append(ok(not dupes, "동시 claim 에서 같은 일을 둘이 집지 않았다",
                      f"{len(ids)}개 집힘, 중복 {len(dupes)}"))
    results.append(ok(len(ids) == N, f"대기 {N}개가 모두 정확히 한 번씩 집혔다", f"{len(ids)}/{N}"))
    results.append(ok(len(empty) == 4, "대기보다 많이 던진 4개는 빈 손으로 돌아왔다",
                      f"{len(empty)}개가 task_id=null"))

    # ---- 집힌 일에는 앞 단계가 남긴 것이 실려 있는가 --------------------
    first = next(g for g in got if g.get("task_id") is not None)   # 집힌 것 중 아무거나 하나
    # The outcome column has to come back with the task, or a stage would have to be
    # told it separately and the board would not be the source of truth it claims to be.
    #
    # ↑ 결과변수는 일과 **함께** 딸려 와야 한다. 안 그러면 각 단계에 그것을 따로
    #   알려 줘야 하고, 그 순간 판은 "여기만 보면 된다" 는 유일한 근거이기를
    #   그만둔다. 근거가 둘이 되면 언젠가 둘이 어긋난다.
    results.append(ok(first.get("y_column") == "HIV_DETECTABLE",
                      "집어간 일에 결과변수가 실려 있다", str(first.get("y_column"))))
    results.append(ok(first.get("columns") == COLUMNS,
                      "집어간 일에 가설이 고른 컬럼이 실려 있다 (이름 속 쉼표 포함)",
                      str(first.get("columns"))))

    # ---- 판을 읽으면 근거가 보이는가 -----------------------------------
    #
    # `read_board` 의 SELECT 가 `okf_concept_ids` 를 빠뜨린 적이 있다. 넣기는
    # 제대로 넣고 있었으므로 표에는 있었고, 창구로만 안 보였다 — 그래서 판을
    # 아무리 들여다봐도 "왜 이 컬럼인가" 를 알 수 없었다. 여기서 확인하는 것은
    # **넣은 것이 그대로 돌아오는가**이다.
    board_now = json.loads(await bb.read_board(RUN_TAG))["tasks"][0]
    results.append(ok(board_now.get("okf_concept_ids") == OKF_IDS,
                      "판을 읽으면 근거 문서가 보인다", str(board_now.get("okf_concept_ids"))))

    # ---- 흐름: 집기 → 써넣기 → 다음 타입으로 --------------------------
    #
    # 데이터 단계가 결과를 써넣으면, 그 줄은 저절로 "학습 차례" 로 바뀌고 다시
    # 대기 상태가 되어야 한다. 다음 단계에게 따로 알릴 사람이 없기 때문이다 —
    # 판이 스스로 넘겨야 흐름이 이어진다.
    tid = first["task_id"]

    # 매처가 무엇을 보고 무엇을 골랐는지. 구동 프로그램이 추적에서 뽑아 붙이는
    # 자리라, 여기서는 그것을 손으로 흉내 낸다. **완료되기 전에** 붙여야 한다 —
    # 완료되는 순간 결과표로 복사되기 때문이다.
    TRACE = [{"tool": "match_concepts",
              "arguments": {"concepts": ["age"]},
              "result": {"results": [{"concept": "age", "candidates": [
                  {"feature_name": "CURRENT_AGE", "similarity_score": 0.93},
                  {"feature_name": "LAB__AGE_ADJ", "similarity_score": 0.91}]}]}}]
    at = json.loads(await bb.attach_match_trace(tid, json.dumps(TRACE)))
    results.append(ok(at.get("calls") == 1, "매처 기록을 판에 붙인다", str(at.get("calls"))))

    r = json.loads(await bb.submit_result(tid, subset_path="outputs/sub_x.csv",
                                          columns_used=COLUMNS))
    results.append(ok(r.get("task_type") == "ml" and r.get("status") == "ready",
                      "데이터 단계가 써넣자 다음이 학습으로 넘어갔다", f"{r.get('status')} · {r.get('task_type')}"))

    # 안 집고 써넣으려 하면 막히는가
    #
    # 방금 tid 는 이미 써넣기가 끝나 진행 중이 아니다. 여기에 또 써넣으려 하면
    # 오류가 나야 한다. 이것이 막히지 않으면, 늦게 도착한 응답 하나가 이미 끝난
    # 줄을 덮어써서 결과가 조용히 바뀔 수 있다.
    r2 = json.loads(await bb.submit_result(tid))
    results.append(ok("error" in r2, "집지 않은 일에는 써넣을 수 없다", r2.get("error", "")[:48]))

    # 학습 → 해석 → 완료
    #
    # 남은 두 단계를 그대로 밟아 본다. 값(auc 0.71 등)은 아무 숫자여도 된다.
    # 확인하는 것은 마지막 단계가 끝났을 때 상태가 "done" 이 되는가이다.
    c = json.loads(await bb.claim_task("ml"))
    await bb.submit_result(c["task_id"], auc=0.71, feature_importance='{"CURRENT_AGE": 0.4}')
    c = json.loads(await bb.claim_task("interpret"))
    r3 = json.loads(await bb.submit_result(c["task_id"], interpretation="지지됨"))
    results.append(ok(r3.get("status") == "done", "해석까지 끝나면 완료가 된다", str(r3.get("status"))))

    # ---- results 표에 쌓였는가 ---------------------------------------
    #
    # 판(memstara_blackboard)은 진행 상황을 들고 있고, 끝난 것은 결과 표
    # (memstara_results)로 넘어가야 한다. 여기서는 데이터베이스에 직접 물어본다 —
    # 도구를 통해 확인하면 도구와 표가 함께 틀려 있어도 통과할 수 있다.
    board = json.loads(await bb.read_board(RUN_TAG))
    import asyncpg

    conn = await asyncpg.connect(bb._dsn())
    try:
        n_res = await conn.fetchval("SELECT count(*) FROM memstara_results WHERE run_tag=$1", RUN_TAG)
    finally:
        await conn.close()
    results.append(ok(n_res == 1, "완료된 것이 results 표에 쌓였다", f"{n_res}행"))

    # ---- 결과표로 근거까지 넘어갔는가 ----------------------------------
    #
    # 오래 남는 표는 결과표다. 예전에는 여기로 아홉 칸만 넘어갔고, 그 아홉 칸은
    # 전부 **결론** 이었다 — 가설 · 쓴 컬럼 · AUC · 해석. 왜 그 컬럼이었는지
    # (okf_concept_ids · match_trace) 와 그것이 값을 했는지(feature_importance) 는
    # 치워도 되는 표에 남아 있었다. 그래서 오래 남는 기록이 하필 **확인할 수 없는
    # 부분**이었다.
    res = json.loads(await bb.read_results(RUN_TAG, include_match_trace=True))["results"][0]
    carried = (res.get("okf_concept_ids") == OKF_IDS
               and len(res.get("match_trace") or []) == 1
               and (res.get("feature_importance") or {}).get("CURRENT_AGE") == 0.4
               and res.get("columns") == COLUMNS)
    results.append(ok(carried, "결과표가 결론과 함께 근거도 들고 있다",
                      f"근거 {len(res.get('okf_concept_ids') or [])}개 · "
                      f"후보기록 {len(res.get('match_trace') or [])}건 · "
                      f"기여도 {len(res.get('feature_importance') or {})}개"))

    # ---- 결과가 "무엇을 물었나" 까지 들고 갔는가 ------------------------
    #
    # 결과표는 지금까지 **답만** 들고 있었다. 어떤 질문에 대한 답인지는 판의
    # perspective 칸에만 있었고, 판은 치우면 사라진다. 그래서 실행이 끝나면 답은
    # 남고 질문은 없어졌다 — 성적을 질문에 되먹일 방법이 그 순간 사라진다.
    results.append(ok(res.get("question_id") == QID,
                      "결과표에 어떤 질문에서 나온 답인지가 남는다",
                      f"question_id={res.get('question_id')} (기대 {QID})"))

    # ---- 성적을 질문 은행으로 되먹인다 ---------------------------------
    #
    # 이걸 부르는 것은 에이전트가 아니라 구동 프로그램이다. 파도가 끝났다는 사실을
    # 아는 쪽이 거기뿐이기 때문이다. 이것이 없으면 은행은 "무엇을 물었나" 의 목록일
    # 뿐, "물어서 무엇이 나왔나" 의 기록이 되지 못한다.
    fed = json.loads(await bb.record_question_outcomes(RUN_TAG))
    scored = next((q for q in json.loads(await bb.read_questions(limit=200))["questions"]
                   if q.get("question_id") == QID), {})
    # 한 번 더 불러도 같은 자리에 있어야 한다. times_used 를 더하는 게 아니라 결과표에서
    # 다시 세기 때문이다 — 재시도나 중복 호출이 횟수를 부풀리면 안 된다.
    await bb.record_question_outcomes(RUN_TAG)
    again = next((q for q in json.loads(await bb.read_questions(limit=200))["questions"]
                  if q.get("question_id") == QID), {})
    results.append(ok(fed.get("ok") is True
                      and scored.get("times_used") == 1
                      and scored.get("best_auc") == 0.71
                      and again.get("times_used") == 1,
                      "성적이 질문 은행으로 되먹여진다 (두 번 불러도 같다)",
                      f"쓰인 횟수 {scored.get('times_used')} · 최고 AUC {scored.get('best_auc')}"))

    # ---- 세기 --------------------------------------------------------
    #
    # 8개 중 1개만 끝까지 갔고, 나머지 7개는 아까 집힌 채 그대로 있다. 그래서
    # 대기 0 · 진행 중 7(= N-1) 이 맞는 답이다. 이 숫자가 어긋나면 어딘가에서
    # 상태가 두 번 바뀌었다는 뜻이다.
    cnt = json.loads(await bb.count_waiting())
    results.append(ok(cnt["ready"] == 0 and cnt["in_progress"] == N - 1,
                      "남은 것을 정확히 센다", f"대기 {cnt['ready']} · 진행중 {cnt['in_progress']}"))
    results.append(ok(board["count"] == N, "판 전체를 읽는다", f"{board['count']}개"))

    # ---- ⭐ 관문: 판을 치워도 근거가 남는가 -----------------------------
    #
    # 표를 둘로 나눈 이유가 이것이므로, 이 항목이 이 파일에서 가장 중요한 축에
    # 든다. 판은 작업대라 언제든 치울 수 있고(`blackboard.py --drop`), 치우고 나면
    # 남는 것은 결과표뿐이다. 근거가 판에만 있었다면 이 시점에 사라진다.
    #
    # 마지막에 두는 이유 — 여기서 판의 줄을 지우므로, 위의 개수 세기 항목들이
    # 먼저 끝나 있어야 한다.
    conn = await asyncpg.connect(bb._dsn())
    try:
        await conn.execute("DELETE FROM memstara_blackboard WHERE run_tag=$1", RUN_TAG)
    finally:
        await conn.close()
    # 기본값으로 읽으면 후보 기록은 건수만 온다 — 보고 프롬프트가 부풀지 않도록.
    brief = json.loads(await bb.read_results(RUN_TAG))["results"][0]
    # 달라고 하면 내용까지 온다. 관문이 증명할 것은 내용 쪽이다.
    after = json.loads(await bb.read_results(RUN_TAG, include_match_trace=True))["results"][0]
    survived = (after.get("task_id") is None            # 연결은 끊기고
                and after.get("okf_concept_ids") == OKF_IDS   # 내용은 남는다
                and "match_trace" not in brief and brief.get("match_trace_calls") == 1
                and len(after.get("match_trace") or []) == 1
                and (after.get("feature_importance") or {}).get("CURRENT_AGE") == 0.4)
    results.append(ok(survived, "판을 치워도 결과표의 근거는 남는다",
                      f"task_id={after.get('task_id')} · "
                      f"근거 {len(after.get('okf_concept_ids') or [])}개 · "
                      f"후보기록 {len(after.get('match_trace') or [])}건"))

    # ---- ⭐ 관문: 판을 치워도 질문 은행은 남는가 -------------------------
    #
    # 질문을 판의 perspective 칸에만 두지 않고 별도 표로 뺀 이유가 이것이다. 방금
    # 판의 줄을 통째로 지웠는데, 그래도 은행의 질문과 결과표의 question_id 가 함께
    # 살아 있어야 한다. 둘 중 하나라도 없어지면 다음 실행은 "이건 이미 물어봤고
    # AUC 0.71 이 나왔다" 를 알 길이 없어, 같은 질문을 처음처럼 다시 묻는다.
    #
    # 은행이 판을 향한 외래키를 갖고 있지 않은 것도 이 항목이 지키는 것이다.
    # 외래키가 있었다면 오래 남을 표가 먼저 사라질 표를 가리키게 된다.
    bank_after = next((q for q in json.loads(await bb.read_questions(limit=200))["questions"]
                       if q.get("question_id") == QID), None)
    results.append(ok(bank_after is not None
                      and bank_after.get("times_used") == 1
                      and after.get("question_id") == QID,
                      "판을 치워도 질문 은행과 그 연결은 남는다",
                      f"은행 {'있음' if bank_after else '없음'} · "
                      f"결과표 question_id={after.get('question_id')}"))

    # 검사가 만든 것은 남기지 않는다.
    await cleanup()
    # sum(results) — True 는 1, False 는 0 이라 그대로 더하면 통과 개수가 된다.
    print(f"\n  {sum(results)}/{len(results)} 통과")
    # 하나라도 실패하면 0 이 아닌 값으로 끝낸다. CI 나 셸이 실패를 알아챌 수 있게.
    return 0 if all(results) else 1


if __name__ == "__main__":
    # 이 파일이 있는 폴더를 찾는 경로 맨 앞에 넣는다. 어느 위치에서 실행해도
    # 옆에 있는 tools_blackboard 를 찾을 수 있게 하려는 것이다.
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    raise SystemExit(asyncio.run(main()))
