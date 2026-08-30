#!/usr/bin/env python3
"""The shared work board — table definitions and creation.

The 2026-08-12 alignment settled that this is a **table**, living in **Memstara's own
database** — its own Postgres server, its own volume, its own account. See
``docker-compose.yml`` next to this file; nothing here touches core's database.

That independence is the point, and it is worth being blunt about why. These tables
first lived inside core's `agentic_core` database, separated only by an `memstara_` name
prefix. Everything worked, but the arrangement was wrong: Memstara is meant to be an
application that owns its store, not a guest in core's. Sharing a server means core's
container going down takes Memstara's results with it, a `docker volume rm` aimed at
core destroys data that has nothing to do with core, and backing up one backs up the
other. A prefix is a naming convention, not a boundary.

↑ 왜 데이터베이스를 따로 쓰는가 — 처음에는 이 표들이 core 의 `agentic_core`
  데이터베이스 안에 있었고, `memstara_` 라는 이름 앞머리로만 구분됐다. 동작에는
  문제가 없었지만 배치가 틀렸다. Memstara 는 제 저장소를 소유하는 응용이지 core 의
  셋방살이가 아니다. 서버를 같이 쓰면 이런 일이 생긴다.

    * core 컨테이너가 내려가면 Memstara 의 결과도 같이 못 쓰게 된다.
    * core 를 정리하려고 `docker volume rm` 을 하면 core 와 아무 상관 없는
      데이터까지 지워진다.
    * 하나를 백업하면 다른 하나도 딸려 백업된다.

  이름 앞머리는 **관례**이지 **경계**가 아니다. 그래서 서버·볼륨·계정을 통째로
  분리했다. 자세한 것은 옆의 `docker-compose.yml` 을 볼 것. core 의 마이그레이션은
  건드리지 않는다 — 애초에 다른 서버를 향해 도니 건드릴 수도 없다.

**core's migrations are not touched** — they cannot be, since they run against a
different server entirely.

Two tables, deliberately separate:

- ``memstara_blackboard`` — work that is not finished yet, and its state. Changes
  constantly while a run is going.
- ``memstara_results``   — what the interpretation stage produced. Only accumulates.

Keeping them apart means "what is left to do" never gets mixed with "what we have
found", which is what that separation was for.

↑ 표 두 개를 일부러 갈라 놨다.

    memstara_blackboard  아직 안 끝난 일과 그 상태를 적는 **작업대**. 실행 중에는
                         쉴 새 없이 바뀌고, 다 쓰면 치워도 되는 것.
    memstara_results     해석 단계가 만들어 낸 **기록**. 쌓이기만 하고 줄지 않는다.

  이렇게 나눠 두면 "아직 할 일" 과 "우리가 알아낸 것" 이 섞이지 않는다. 그게
  나눠 놓은 이유의 전부다.

Usage::

    python blackboard.py --create      # idempotent
    python blackboard.py --show
    python blackboard.py --drop        # asks first
    python blackboard.py --drop-questions   # the bank, which --drop leaves alone

↑ 쓰는 법:
    python blackboard.py --create    표를 만든다. 이미 있으면 아무 일도 없다.
    python blackboard.py --show      무엇이 있고 판이 어떤 상태인지 보여 준다.
    python blackboard.py --drop      판과 결과표를 지운다. 먼저 물어본다.
    python blackboard.py --drop-questions
                                     질문 은행을 지운다. --drop 은 이걸 건드리지 않는다.

==============================================================================
 이 파일을 읽는 법
==============================================================================

 이 파일은 **판(blackboard)과 결과표의 설계도**다. 표를 어떤 칸으로 만들지 적어
 두고(SQL), 데이터베이스에 접속하는 주소를 정하고, 만들기·보기·지우기를 명령줄에서
 할 수 있게 한다. 여기서 실제로 일을 하지는 않는다 — 일할 자리를 마련할 뿐이다.

 주요 이름
 ---------
 STATUSES / TASK_TYPES  한 작업이 가질 수 있는 상태 넷과 단계 넷.
 SCHEMA                 두 표의 정의(SQL) 전문. 여러 번 실행해도 안전하게 썼다.
 dsn()                  Memstara 자기 데이터베이스의 주소. core 것이 아니다.
 BoardBusy              같은 run_tag 를 다른 실행이 이미 쥐고 있을 때 나는 예외.
 run_lock(run_tag)      한 run_tag 는 한 번에 한 실행만 — 자문 잠금(advisory lock).
 create / drop / show   표 만들기 / 지우기 / 현황 보기.
 main()                 명령줄 인자를 읽어 위 셋 중 하나를 부른다.

 놓치기 쉬운 것
 --------------
 1. 표는 둘이다. `memstara_blackboard` 는 작업대라 **치우면 사라져도 되는 것**이고,
    `memstara_results` 는 기록이라 **남아야 하는 것**이다.
 2. 결과표가 판을 가리키는 연결은 `ON DELETE SET NULL` 이다. 즉 **판을 지워도
    결과는 안 지워진다** — 연결만 끊긴다. 예전에 CASCADE 였을 때는 판을 청소하면
    결과가 같이 날아갔고, 그러면 표를 둘로 나눈 의미가 사라진다.
 3. `run_lock` 은 PostgreSQL 의 자문 잠금이라 **연결에 매여 있다.** 프로세스를
    `kill -9` 해도 연결이 끊기면서 잠금이 같이 풀린다. pid 파일이었다면 죽은
    프로세스가 남긴 파일이 이후 모든 실행을 막았을 것이다.
"""

from __future__ import annotations

import argparse      # 명령줄 인자(--create, --drop, --show)를 읽는다
import asyncio        # asyncpg 가 비동기라, 명령줄에서는 asyncio.run 으로 감싼다
import contextlib     # run_lock 을 `with` 로 쓸 수 있게 만든다
import os             # 환경변수에서 데이터베이스 주소를 읽는다
import re             # postgresql+asyncpg:// 형태를 다듬는다
import sys
import zlib           # run_tag 를 잠금 번호(정수)로 바꾸는 crc32 가 여기 있다
from collections.abc import AsyncIterator

import asyncpg        # PostgreSQL 비동기 드라이버

# Every state a task can be in.
#
# `failed` and the `attempts` column below are present but **not yet used by any
# policy**. What happens to a task whose agent claimed it and then died is still open
# (see the design document, "정해야 할 다섯" §2) — it might be returned to `ready` for
# another attempt, or closed as `failed`. Carrying both now means whichever way that
# lands, the table does not have to be rebuilt. **This is not a decision; it is leaving
# both doors open.**
#
# ↑ 작업 하나가 가질 수 있는 상태 넷:
#     ready        아직 아무도 안 집었다 — 누구든 가져갈 수 있다
#     in_progress  누군가 집어 갔고 지금 하고 있다
#     done         끝났다
#     failed       실패로 닫혔다
#
#   `failed` 와 아래의 `attempts` 칸은 **만들어만 뒀고 아직 아무 규칙도 쓰지 않는다.**
#   작업을 집어 간 에이전트가 도중에 죽었을 때 어떻게 할지가 아직 안 정해졌다 —
#   `ready` 로 되돌려 다시 시켜야 할지, `failed` 로 닫아야 할지. 지금 둘 다 갖고
#   있으면 어느 쪽으로 정해지든 표를 다시 만들 필요가 없다.
#   **이건 결정이 아니라 문 두 개를 다 열어 둔 것이다.**
STATUSES = ("ready", "in_progress", "done", "failed")

# The four stages. A task carries the stage that should pick it up next, which is how
# an agent answers "is this mine?" without anyone telling it.
#
# ↑ 네 단계: 가설 세우기 → 데이터 추리기 → 학습하기 → 해석하기.
#   한 작업 행이 "다음에 나를 집어 갈 단계" 를 스스로 달고 있다. 그래서 에이전트가
#   "이게 내 일인가?" 를 누가 알려 주지 않아도 판만 보고 판단할 수 있다.
TASK_TYPES = ("hypothesis", "data", "ml", "interpret")

# ↑ 아래는 f-문자열이다. {STATUSES} 와 {TASK_TYPES} 자리에 위에서 정한 튜플이
#   그대로 들어가, SQL 의 IN 목록이 된다. 상태 이름을 파이썬과 SQL 두 군데에
#   따로 적어 두면 언젠가 어긋나므로, 한 곳에서만 적고 끼워 넣는다.
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS memstara_blackboard (
    -- 판(작업대). 아직 안 끝난 일과 그 상태가 여기 있다. 실행이 끝나면 치워도 되는 표.
    -- task_id 는 BIGSERIAL — 행을 넣을 때마다 1씩 자동으로 붙는 번호.
    task_id            BIGSERIAL PRIMARY KEY,

    -- which pipeline run this row belongs to, and which trial within it
    -- ↑ 이 행이 어느 실행(run_tag)의, 그 안의 몇 번째 시도(trial)에 속하는지.
    --   perspective 는 그 시도가 어떤 관점에서 세워진 것인지 적는 칸.
    run_tag            TEXT        NOT NULL,
    trial              INTEGER     NOT NULL,
    perspective        TEXT        NOT NULL DEFAULT '',

    -- the two columns that turn a ledger into a board
    -- ↑ 이 두 칸이 단순한 장부를 "판" 으로 만든다. status 는 지금 어떤 상태인지,
    --   task_type 은 다음에 누가 집어 가야 하는지를 말한다. 이 둘이 없으면 그냥
    --   기록만 쌓이는 표이고, 있으면 에이전트들이 스스로 일을 나눠 가질 수 있다.
    --   CHECK 는 정해진 값 말고는 아예 못 들어가게 막는 장치다.
    status             TEXT        NOT NULL
                       CHECK (status IN {STATUSES}),
    task_type          TEXT        NOT NULL
                       CHECK (task_type IN {TASK_TYPES}),

    -- filled by the hypothesis stage
    -- ↑ 가설 단계가 채우는 칸들. 무엇을 주장하는지(hypothesis), 어떤 열을 쓸
    --   것인지(columns), 어떤 근거 문서를 봤는지(okf_concept_ids).
    --   JSONB 는 목록이나 표를 통째로 담는 칸 형식이다.
    hypothesis         TEXT        NOT NULL DEFAULT '',
    columns            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    okf_concept_ids    JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- What the matcher was asked and what it offered back, including the candidates
    -- that were not chosen. The driver harvests this from the run trace after the
    -- hypothesis stage; the agent does not report it. Asking the agent would mean
    -- trusting it to hand-copy hundreds of candidate rows with no way to check the
    -- copy, and the trace already holds every call verbatim.
    --
    -- Without this the row records which columns were picked but not what they were
    -- picked over, so "why this column" is answerable only while the run directory
    -- survives.
    match_trace        JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- What the chosen columns are meant to predict. On the board rather than in a
    -- prompt: a task has to carry everything its stage needs, or the board is not the
    -- source of truth it claims to be. Before this, the driving script told each agent
    -- the outcome column in the prompt text, so a finished row recorded an AUC without
    -- recording what it was an AUC *of*.
    --
    -- ↑ 고른 열들로 **무엇을 맞히려는지**. 프롬프트가 아니라 판에 적는다. 작업 하나가
    --   자기 단계에 필요한 것을 전부 지니고 있어야 판이 "믿을 근거" 노릇을 한다.
    --   이게 없던 때에는 실행 스크립트가 결과 열 이름을 프롬프트 글로 알려 줬고,
    --   그래서 다 끝난 행에 AUC 는 있는데 **무엇의 AUC 인지**는 없었다.
    y_column           TEXT        NOT NULL DEFAULT '',

    -- filled by the data stage
    -- ↑ 데이터 단계가 채운다. 잘라 낸 작은 CSV 가 어디 있는지(subset_path),
    --   실제로 쓴 열과(columns_used) 없어서 못 쓴 열(columns_missing).
    --   없는 열을 따로 적어 두는 이유는, 가설이 요구한 것과 실제로 쓴 것이 다를 때
    --   해석 단계가 그 차이를 알고 읽어야 하기 때문이다.
    subset_path        TEXT        NOT NULL DEFAULT '',
    columns_used       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    columns_missing    JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- filled by the ml stage
    -- ↑ 학습 단계가 채운다. 성능 숫자(auc)와 어느 변수가 얼마나 기여했는지
    --   (feature_importance). auc 만 NOT NULL 이 아닌데, 아직 학습을 안 했으면
    --   "0" 이 아니라 "없음" 이어야 맞기 때문이다.
    --   기본값의 중괄호가 두 겹인 것은 이 SCHEMA 가 f-문자열이기 때문이다.
    --   두 겹으로 적어야 실제 SQL 에는 한 겹으로 들어가 빈 JSON 객체가 된다.
    auc                DOUBLE PRECISION,
    feature_importance JSONB       NOT NULL DEFAULT '{{}}'::jsonb,

    -- filled by the interpretation stage
    -- ↑ 해석 단계가 채운다. 숫자를 사람 말로 옮긴 글.
    interpretation     TEXT        NOT NULL DEFAULT '',

    -- see the note on STATUSES above
    -- ↑ 위 STATUSES 설명 참고. 몇 번 시도했는지와 마지막 오류. 만들어 뒀을 뿐
    --   아직 이걸 보고 무언가 결정하는 규칙은 없다.
    attempts           INTEGER     NOT NULL DEFAULT 0,
    error              TEXT        NOT NULL DEFAULT '',

    -- 언제 누가 집어 갔는지 / 언제 만들어졌는지 / 언제 마지막으로 바뀌었는지.
    -- TIMESTAMPTZ 는 시간대까지 같이 저장하는 형식이다.
    claimed_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- claim_task() looks for exactly this: the oldest ready row of one type.
-- ↑ 색인(index)은 찾기를 빠르게 하는 목차다. claim_task() 가 던지는 질문이 늘
--   "이 단계의 ready 행 중 가장 오래된 것" 이라, 그 순서 그대로 목차를 만들어 둔다.
CREATE INDEX IF NOT EXISTS memstara_blackboard_claim_idx
    ON memstara_blackboard (task_type, status, task_id);

-- 한 실행(run_tag)에 속한 행을 모아 볼 때 쓰는 목차.
CREATE INDEX IF NOT EXISTS memstara_blackboard_run_idx
    ON memstara_blackboard (run_tag);

CREATE TABLE IF NOT EXISTS memstara_results (
    -- 결과표(기록). 판과 달리 쌓이기만 하고 줄지 않는다. 보고 단계는 **이 표만** 읽는다.
    result_id      BIGSERIAL PRIMARY KEY,
    -- Nullable, and SET NULL rather than CASCADE. The whole reason this table is
    -- separate from the board is that the board is a work queue you can clean out
    -- while findings stay — and CASCADE made cleaning the board delete the findings
    -- with it, which quietly removed the point of having two tables. SET NULL keeps
    -- the link honest while the task row lives and breaks it cleanly once it is gone.
    -- A result row describes itself without the id: run_tag, trial, perspective,
    -- hypothesis, columns_used, y_column, auc and the write-up are all here.
    --
    -- ↑ **여기가 이 파일에서 가장 중요한 한 줄이다.**
    --   이 칸은 "이 결과가 어느 작업에서 나왔는지" 를 가리키는 연결이다. 비어 있어도
    --   되고(NULL 허용), 가리키던 작업이 지워지면 **연결만 끊기고 결과 행은 남는다**
    --   (ON DELETE SET NULL).
    --
    --   표를 둘로 나눈 이유가 바로 이것이다. 판은 다 쓰면 치우는 작업대이고, 결과는
    --   남아야 하는 기록이다. 예전에는 여기가 CASCADE 였는데, 그러면 판을 청소할 때
    --   결과가 **같이 지워졌다.** 표를 나눈 의미가 조용히 사라진 것이다.
    --
    --   연결이 끊겨도 결과 행은 혼자서 자기를 설명한다 — 실행 이름, 시도 번호, 관점,
    --   가설, 쓴 열, 무엇을 맞히려 했는지, 성능, 해석 글이 전부 이 표 안에 있다.
    task_id        BIGINT      REFERENCES memstara_blackboard (task_id)
                   ON DELETE SET NULL,
    run_tag        TEXT        NOT NULL,
    trial          INTEGER     NOT NULL,
    perspective    TEXT        NOT NULL DEFAULT '',
    hypothesis     TEXT        NOT NULL DEFAULT '',
    columns_used   JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Why those columns, copied over from the board when the task finishes. The board
    -- is a work surface that gets cleared and this table is the record that stays, so
    -- evidence left only on the board is evidence with an expiry date: clearing the
    -- board took "why this column" with it and left a result asserting a conclusion it
    -- could no longer support.
    --
    -- okf_concept_ids is which corpus documents the hypothesis was built from;
    -- match_trace is what the matcher offered, chosen and rejected alike.
    okf_concept_ids JSONB      NOT NULL DEFAULT '[]'::jsonb,
    match_trace     JSONB      NOT NULL DEFAULT '[]'::jsonb,

    -- What was asked for, against columns_used above, which is what arrived. When the
    -- two differ the reason is columns_missing, and without both a reader of this table
    -- cannot tell a column that was never wanted from one that was wanted and absent.
    columns         JSONB      NOT NULL DEFAULT '[]'::jsonb,
    columns_missing JSONB      NOT NULL DEFAULT '[]'::jsonb,

    -- Carried over from the board. The reporting stage reads only this table, so
    -- without it a report would state an AUC without stating what it is an AUC *of* —
    -- exactly the gap that putting y_column on the board was meant to close.
    --
    -- ↑ 판에서 그대로 옮겨 적는다. 보고 단계는 이 표만 읽으므로, 이 칸이 없으면
    --   보고서에 "AUC 0.78" 은 있는데 **무엇의 0.78 인지**는 없게 된다. 판에
    --   y_column 을 넣어 막으려던 바로 그 구멍이 결과표에서 다시 열리는 셈이다.
    y_column       TEXT        NOT NULL DEFAULT '',

    auc            DOUBLE PRECISION,

    -- Which columns actually carried that AUC, copied over from the board. Feedback
    -- needs this and nothing else does: a later run can only avoid what did not work
    -- if the number saying so outlives the run that produced it. While this lived only
    -- on the board, a hypothesis agent reading finished results could see that a trial
    -- scored 0.72 but not which of its columns contributed nothing.
    feature_importance JSONB   NOT NULL DEFAULT '{{}}'::jsonb,

    interpretation TEXT        NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 한 실행의 결과를 모아 볼 때 쓰는 목차.
CREATE INDEX IF NOT EXISTS memstara_results_run_idx
    ON memstara_results (run_tag);

CREATE TABLE IF NOT EXISTS memstara_questions (
    -- The question bank. Neither a board nor a results table: it holds what the
    -- pipeline decided to ASK, where the other two hold what it did and what it found.
    --
    -- There is deliberately no run_tag. A run_tag column would make this a per-run
    -- scratch list, and then the second run would re-ask everything the first run had
    -- already exhausted. The bank spans runs so that "what has this project already
    -- looked at" is a question the database can answer.
    question_id  SERIAL      PRIMARY KEY,

    -- The perspective phrase itself, handed to the hypothesis agent verbatim. text_key
    -- is the same string lowercased and whitespace-collapsed; UNIQUE sits on the key,
    -- not on text, so two proposals differing only in capitalisation collide as they
    -- should while the wording the agent chose is preserved.
    text         TEXT        NOT NULL,
    text_key     TEXT        NOT NULL UNIQUE,

    -- Which corpus branches this question is grounded in. This column is the whole
    -- point of the table: a question that cannot name a tag the corpus actually carries
    -- is a question the knowledge source cannot answer, and asking it anyway is what
    -- forced the agent to invent citations. Empty here means the generator failed.
    okf_tags     JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- Why this question was proposed — which corpus gap, or which prior result. On the
    -- second wave onward this is where the feedback loop becomes readable by a person.
    rationale    TEXT        NOT NULL DEFAULT '',

    origin_run   TEXT        NOT NULL DEFAULT '',
    origin_wave  INTEGER     NOT NULL DEFAULT 0,

    -- Filled in after a wave finishes, by joining the results table on question_id.
    -- times_used counts trials, not runs: one question can seed several trials.
    times_used   INTEGER     NOT NULL DEFAULT 0,
    best_auc     DOUBLE PRECISION,

    status       TEXT        NOT NULL DEFAULT 'open',   -- 'open' | 'exhausted'
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- read_questions() asks for open rows newest-first; this is that order.
CREATE INDEX IF NOT EXISTS memstara_questions_status_idx
    ON memstara_questions (status, question_id DESC);

-- CREATE TABLE IF NOT EXISTS does nothing to a table that already exists, so a column
-- added later has to be stated separately. Two tables and one column do not justify a
-- migration tool; this line is correct both for a fresh database and an existing one.
--
-- ↑ `CREATE TABLE IF NOT EXISTS` 는 표가 **이미 있으면 아무것도 하지 않는다.** 그래서
--   나중에 새로 생긴 칸은 따로 적어 줘야 옛날에 만든 데이터베이스에도 붙는다.
--   표 두 개에 칸 하나 때문에 마이그레이션 도구까지 들일 일은 아니고, 이 줄은
--   새 데이터베이스에서도 기존 데이터베이스에서도 똑같이 맞다.
ALTER TABLE memstara_blackboard ADD COLUMN IF NOT EXISTS y_column TEXT NOT NULL DEFAULT '';
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS y_column TEXT NOT NULL DEFAULT '';

-- The evidence columns, added for the same reason and in the same way. Without these
-- lines the CREATE TABLE above is silently a no-op on any database that already exists,
-- which is every database this code has ever run against — the fix would appear to be
-- applied and change nothing.
ALTER TABLE memstara_blackboard ADD COLUMN IF NOT EXISTS match_trace JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS okf_concept_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS match_trace JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS feature_importance JSONB NOT NULL DEFAULT '{{}}'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS columns JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS columns_missing JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Which bank question seeded this row. A plain INTEGER and deliberately not a foreign
-- key: memstara_questions outlives the board and the results table, and a foreign key
-- would point from the short-lived tables at the long-lived one, so dropping the bank
-- would require dropping them first. The link is nice to have, not load-bearing —
-- `perspective` already carries the question text on both tables, so a row still says
-- what it was asked even if the bank is gone.
ALTER TABLE memstara_blackboard ADD COLUMN IF NOT EXISTS question_id INTEGER;
ALTER TABLE memstara_results    ADD COLUMN IF NOT EXISTS question_id INTEGER;

-- Same reason as the ADD COLUMN above: an existing table keeps whatever constraint it
-- was created with, so the change has to be stated for databases made before it.
--
-- ↑ 위와 같은 이유다. 이미 있는 표는 만들어질 때의 제약을 그대로 갖고 있으므로,
--   CASCADE 를 SET NULL 로 바꾼 변경도 옛 데이터베이스를 위해 따로 적어 준다.
--   순서: NOT NULL 을 풀고 → 옛 외래키를 떼고 → SET NULL 짜리로 다시 단다.
ALTER TABLE memstara_results ALTER COLUMN task_id DROP NOT NULL;
ALTER TABLE memstara_results DROP CONSTRAINT IF EXISTS memstara_results_task_id_fkey;
ALTER TABLE memstara_results ADD CONSTRAINT memstara_results_task_id_fkey
    FOREIGN KEY (task_id) REFERENCES memstara_blackboard (task_id) ON DELETE SET NULL;
"""

#: 이 파일이 책임지는 표 이름들. --drop 이 물어볼 때 이 목록을 보여 준다.
#: `memstara_questions` 는 일부러 빠져 있다 — `--drop` 이 지우지 않는 표이므로,
#: 여기 적으면 "지웁니다" 하고 물어본 뒤 안 지우는 거짓말이 된다(→ drop_questions).
TABLES = ("memstara_blackboard", "memstara_results")


#: 아무것도 설정하지 않았을 때 쓸 주소. 옆의 docker-compose.yml 이 띄우는 컨테이너를
#: 가리킨다. 포트 5463 은 core 의 Postgres(5432 등)와 겹치지 않게 고른 것이다.
MEMSTARA_DATABASE_URL_DEFAULT = "postgresql://memstara:memstara@localhost:5463/memstara"


def dsn() -> str:
    """Postgres address for Memstara's own database.

    Deliberately **not** ``AGENTIC_DATABASE_URL``. Reading core's variable is how the
    board ended up inside core's database in the first place: the address was there, it
    worked, and nothing ever forced the question of whose store this is.

    The default points at the container in ``docker-compose.yml``, so a fresh checkout
    runs after ``docker compose up -d`` with nothing else set. Override with
    ``MEMSTARA_DATABASE_URL`` to point somewhere else.

    SQLAlchemy's ``postgresql+asyncpg://`` form is accepted and reduced, because the
    value often gets copied from a core-style .env and asyncpg rejects the ``+driver``.

    ↑ 요약: 접속할 데이터베이스 주소를 정한다. `MEMSTARA_DATABASE_URL` 이 있으면
      그것을, 없으면 위의 기본값(도커 컨테이너)을 쓴다.

      **일부러 `AGENTIC_DATABASE_URL` 을 읽지 않는다.** 판이 core 의 데이터베이스
      안에 들어가 앉게 된 것이 바로 그 때문이었다 — 주소가 이미 거기 있었고, 잘
      돌아갔고, "이 저장소는 누구 것인가" 를 아무도 묻지 않았다.

      마지막 줄은 `postgresql+asyncpg://` 처럼 드라이버 이름이 붙은 주소를
      `postgresql://` 로 줄인다. core 쪽 .env 에서 값을 복사해 오는 일이 잦은데
      asyncpg 는 `+드라이버` 가 붙은 형태를 거부하기 때문이다.
    """
    url = os.environ.get("MEMSTARA_DATABASE_URL", "").strip() or MEMSTARA_DATABASE_URL_DEFAULT
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


class BoardBusy(RuntimeError):
    """Raised when another driver already holds this run_tag.

    ↑ 같은 run_tag 를 이미 다른 실행이 쥐고 있을 때 나는 예외. 프로그램 오류가
      아니라 "지금은 안 된다" 는 알림이다.
    """


@contextlib.asynccontextmanager
async def run_lock(run_tag: str) -> AsyncIterator[None]:
    """Hold an exclusive claim on *run_tag* for as long as this block runs.

    Only one driver may work a given run_tag at a time. The board itself is safe
    under concurrency — `claim_task` uses FOR UPDATE SKIP LOCKED, so two claimers
    never take the same row — but the *driver* is not. It decides "nothing is
    waiting for me, so anything still in_progress must be abandoned" and returns
    those tasks to the queue. That inference is only sound if it is the only driver.
    With two, one sees an empty queue merely because the other took the work, and
    then reclaims tasks that are actively being worked on.

    This happened, on 2026-08-17: a run believed dead was still alive, and a second
    was started 39 seconds later against the same tag. Nothing broke — the row-level
    locking held — but four interpretation agents and two reporting agents ran, and
    the numbers were unusable.

    A Postgres advisory lock rather than a pid file, because it is tied to the
    connection: kill the process and the lock is gone with it. A pid file left by a
    killed process blocks every later run until someone deletes it by hand.

    Raises:
        BoardBusy: another driver holds this run_tag.

    ↑ 요약: 이 `with` 블록이 도는 동안 해당 run_tag 를 혼자 차지한다. 다른 실행이
      같은 tag 로 들어오면 기다리지 않고 곧바로 BoardBusy 로 튕겨 낸다.

      **왜 필요한가** — 판 자체는 여러 명이 동시에 써도 안전하다. `claim_task` 가
      `FOR UPDATE SKIP LOCKED` 를 쓰기 때문에 두 사람이 같은 행을 집어 가는 일은
      없다. 안전하지 않은 쪽은 **실행을 이끄는 쪽(driver)** 이다.

      드라이버는 "기다리는 일이 하나도 없다 → in_progress 로 남은 건 죽은 작업이다"
      라고 판단하고 그것들을 다시 대기열로 되돌린다. 이 추론은 드라이버가 자기
      하나뿐일 때만 옳다. 둘이면, 다른 쪽이 일을 다 집어 가서 대기열이 비어 보이는
      것뿐인데도 **지금 한창 처리 중인 작업을 빼앗아 되돌린다.**

      2026-08-17 에 실제로 일어났다. 죽은 줄 알았던 실행이 살아 있었고, 39초 뒤에
      같은 tag 로 두 번째 실행이 시작됐다. 무엇도 깨지지는 않았다 — 행 단위 잠금이
      버텨 줬다 — 하지만 해석 에이전트가 넷, 보고 에이전트가 둘 돌았고 나온 숫자는
      쓸 수 없었다.

      **왜 pid 파일이 아니라 자문 잠금(advisory lock)인가** — 자문 잠금은 데이터베이스
      연결에 매여 있다. 프로세스를 `kill -9` 로 죽여도 연결이 끊기면서 잠금이 같이
      사라진다. pid 파일이었다면 죽은 프로세스가 남긴 파일이, 누가 손으로 지워 줄
      때까지 이후 모든 실행을 막았을 것이다.
    """
    # crc32 gives a stable 32-bit key from the tag. hashtext() would also work but is
    # an internal function with no compatibility promise across versions.
    #
    # ↑ 자문 잠금은 이름이 아니라 **숫자**로 건다. crc32 는 같은 글자에 늘 같은
    #   32비트 숫자를 준다. PostgreSQL 의 hashtext() 로도 되지만 그건 내부 함수라
    #   버전이 바뀌어도 같은 값을 준다는 약속이 없다.
    key = zlib.crc32(run_tag.encode("utf-8"))
    # 이 잠금 전용 연결이다. 잠금이 연결에 매여 있으므로, 블록이 끝나거나 프로세스가
    # 죽어 연결이 닫히는 순간 잠금도 풀린다.
    conn = await asyncpg.connect(dsn())
    try:
        # try_ 가 붙은 쪽이라 기다리지 않는다. 이미 누가 쥐고 있으면 곧바로 거짓.
        if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", key):
            raise BoardBusy(
                f"run_tag '{run_tag}' is already being worked by another process.\n"
                "  Two drivers on one tag reclaim each other's tasks — see run_lock().\n"
                "  Use a different --run-tag, or wait for the other run to finish."
            )
        try:
            # 여기서 `with` 블록 안의 일이 벌어진다. 잠금은 그동안 계속 잡혀 있다.
            yield
        finally:
            # 안에서 무슨 일이 나든 잠금은 푼다.
            await conn.execute("SELECT pg_advisory_unlock($1)", key)
    finally:
        # 연결도 반드시 닫는다. 못 닫더라도 연결이 끊기면 잠금은 어차피 풀린다.
        await conn.close()


async def create() -> None:
    """표를 만든다. 이미 있으면 아무 일도 일어나지 않는다(여러 번 실행해도 안전)."""
    conn = await asyncpg.connect(dsn())
    try:
        await conn.execute(SCHEMA)   # 위 SCHEMA 를 통째로 실행한다
    finally:
        await conn.close()


async def drop() -> None:
    """두 표를 지운다. 데이터도 같이 사라진다.

    `memstara_questions` 는 **여기서 지우지 않는다.** 질문 은행은 실행을 넘어 쌓이는
    것이라, 판을 청소할 때 같이 사라지면 "이 프로젝트가 이미 무엇을 물어봤나" 를
    매번 잃는다. 은행을 비우려면 `--drop-questions` 를 따로 써야 한다.
    """
    conn = await asyncpg.connect(dsn())
    try:
        # results first — it references the board.
        # ↑ 결과표를 먼저 적는다. 결과표가 판을 가리키고 있으므로, 가리키는 쪽부터
        #   치워야 순서가 맞다.
        await conn.execute("DROP TABLE IF EXISTS memstara_results, memstara_blackboard CASCADE;")
    finally:
        await conn.close()


async def drop_questions() -> None:
    """질문 은행을 지운다. `drop()` 과 갈라 둔 이유는 그 docstring 에 적혀 있다."""
    conn = await asyncpg.connect(dsn())
    try:
        await conn.execute("DROP TABLE IF EXISTS memstara_questions CASCADE;")
    finally:
        await conn.close()


async def show() -> None:
    """지금 데이터베이스에 무엇이 있고 판이 어떤 상태인지 찍어 본다.

    우리 표와 core 표를 갈라서 보여 준다. 실제로는 서버가 아예 다르므로 core 표는
    보이지 않는 것이 정상이다 — 그래도 갈라 두는 이유는, 혹시 옛날처럼 한 데
    섞여 있는 데이터베이스를 보게 됐을 때 한눈에 알아채기 위해서다.
    """
    conn = await asyncpg.connect(dsn())
    try:
        # pg_tables 는 PostgreSQL 이 스스로 들고 있는 "표 목록" 표다.
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        names = [r["tablename"] for r in rows]
        ours = [n for n in names if n.startswith("memstara_")]
        theirs = [n for n in names if not n.startswith("memstara_")]

        print(f"우리 테이블 {len(ours)}개")
        for n in ours:
            # 표 이름은 값으로 끼워 넣을 수 없어서 문자열로 붙인다. 이름이 위
            # 목록에서 나온 것이라 바깥 입력이 섞일 여지가 없으므로 안전하다
            # (noqa 주석이 검사기에 그 사정을 알려 준다).
            count = await conn.fetchval(f"SELECT count(*) FROM {n}")  # noqa: S608 - fixed names
            print(f"   {n:24} {count}행")
        print(f"\ncore 테이블 {len(theirs)}개 — 건드리지 않는다")
        for n in theirs:
            print(f"   {n}")

        # 판이 있으면 단계×상태로 몇 건씩인지 세어 보여 준다. 실행이 어디까지
        # 갔는지, 어디서 막혔는지를 한눈에 보는 용도다.
        if "memstara_blackboard" in ours:
            by = await conn.fetch(
                "SELECT task_type, status, count(*) AS n FROM memstara_blackboard "
                "GROUP BY task_type, status ORDER BY task_type, status"
            )
            if by:
                print("\n판의 상태")
                for r in by:
                    print(f"   {r['task_type']:10} {r['status']:12} {r['n']}")
    finally:
        await conn.close()


def main() -> int:
    """명령줄에서 부를 때의 입구. 0을 돌려주면 정상, 1이면 취소된 것이다."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # 셋 중 **하나만** 골라야 한다. 하나도 안 고르는 것도 안 된다.
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true", help="create the tables (idempotent)")
    g.add_argument("--drop", action="store_true", help="drop them — asks first")
    g.add_argument("--show", action="store_true", help="what exists and what is on the board")
    g.add_argument("--drop-questions", action="store_true",
                   help="empty the question bank — separate from --drop on purpose")
    ap.add_argument("--yes", action="store_true", help="skip the question on --drop")
    args = ap.parse_args()

    if args.create:
        # 만든 뒤에 곧바로 현황을 보여 준다 — 만들어졌는지 눈으로 확인하라고.
        asyncio.run(create())
        print("created (or already there)")
        asyncio.run(show())
    elif args.drop:
        # 지우기는 되돌릴 수 없으므로 기본적으로 한 번 물어본다. --yes 를 붙이면
        # 묻지 않는다(스크립트에서 부를 때 쓴다). "yes" 를 **정확히** 쳐야 한다.
        if not args.yes:
            print(f"이 표들을 지웁니다: {', '.join(TABLES)}")
            if input("정말 지울까요? (yes) ").strip() != "yes":
                print("취소")
                return 1
        asyncio.run(drop())
        print("dropped")
    elif args.drop_questions:
        # 은행은 실행을 넘어 쌓인 것이라 --drop 보다 잃는 것이 크다. 같은 방식으로 묻는다.
        if not args.yes:
            print("질문 은행(memstara_questions)을 통째로 지웁니다.")
            if input("정말 지울까요? (yes) ").strip() != "yes":
                print("취소")
                return 1
        asyncio.run(drop_questions())
        print("dropped questions")
    else:
        asyncio.run(show())
    return 0


if __name__ == "__main__":
    # 돌려받은 값을 그대로 종료 코드로 쓴다. 취소했으면 1로 끝난다.
    raise SystemExit(main())
