#!/usr/bin/env python3
"""The same four stages, driven by a shared board instead of a supervisor.

In `02_mvp_pipeline.py` a Python function calls the stages in order and carries each
output to the next by variable. Here nobody carries anything: the hypothesis stage puts
work on a board, and the other stages take work off it. Each task says which stage
should pick it up next, so an agent only has to know its own type.

**That file is untouched.** Both paths exist so they can be compared — a board that
produces different answers than the supervisor did would be worth knowing about, and
only one of them can be the reason.

Why a driving script rather than agents that watch the board: core runs an agent once
and returns. There is no pattern that keeps one alive waiting for work, so something
has to look at the board and call whoever is needed. That something is deterministic
and cheap, which is what the 2026-08-12 alignment concluded ("this doesn't have to be
an agent, it could be just a deterministic script").

A task whose agent dies goes back to waiting and is retried, without limit. **That
means a task that always fails keeps the board from draining, and the report never
runs.** It is the chosen behaviour, so this script makes the retry count visible on
every round — a person cannot decide to stop what they cannot see — and leaves the
board consistent when interrupted. `--report-only` writes the report from whatever has
accumulated, for exactly that case.

Setup is the same as 02, plus the board::

    python blackboard.py --create

Run::

    python 03_board_pipeline.py --trials 3
    python 03_board_pipeline.py --report-only --run-tag <tag>


==============================================================================
 이 파일을 읽는 법
==============================================================================

 ■ 연구실 하나라고 생각하면 쉽다

 사람이 다섯 명 있고, 벽에 게시판이 하나 있다.

   가설 담당    논문을 읽고 "이 변수들이 답일 것 같다" 고 제안한다
   데이터 담당  그 변수들만 원본에서 오려낸다
   학습 담당    오려낸 것으로 모델을 돌려 점수를 낸다
   해석 담당    나온 점수를 말로 푼다
   보고 담당    전부 모아 한 장으로 정리한다

 **아무도 다음 사람에게 직접 건네주지 않는다.** 일을 게시판에 붙여 두면 다음
 사람이 알아서 떼어 간다. 종이 한 장에 "다음은 누구 차례" 가 적혀 있어서,
 각자는 자기 종류만 알면 된다.

 그렇게 만든 이유는 셋이다.
   · 누가 무엇을 했는지 **종이에 남는다**
   · 한 명이 죽어도 그 종이는 게시판에 그대로 있다 — 다시 시작하면 이어서 한다
   · 나중에 사람을 늘리기 쉽다


 ■ 이 파일을 켜면 벌어지는 일

   ① 다섯 사람을 부른다        provision_board_agents()
      각자가 무슨 일을 하는 사람인지 적힌 역할 설명서를 꺼내 온다.
      처음이면 새로 쓴다.

   ② 장비 네 대를 켠다          setup_tools()
      사람은 맨손으로 일을 못 한다. 논문 창고 · 데이터 기계 · 학습 기계 ·
      게시판 창구 — 이 넷을 켠다.

   ③ 누가 어느 버튼을 쓸지 정한다   tools_for()
      가설 담당에게는 「오려내기」 버튼을 **안 준다.** 주면 자기가 다 해 버리고,
      그러면 나중에 결과가 누구 판단이었는지 알 수 없어진다.

   ④ 첫 지시서를 게시판에 붙인다     (씨뿌리기)
      가설 담당을 불러 "이런 관점에서 생각해 보고 게시판에 붙여 주세요" 라고
      시킨다. 시행 수만큼 반복한다.

   ⑤ 게시판이 빌 때까지 돌린다      (작업 루프)
      게시판을 보고 → 할 사람이 있으면 부르고 → 없으면 잠깐 기다린다.
      이걸 게시판이 빌 때까지 반복한다.

   ⑥ 마지막에 정리한다              (보고)
      보고 담당이 완료된 것들을 모아 한 장으로 쓴다.

 `--report-only` 로 돌리면 ④⑤를 건너뛰고 **⑥만** 한다. 이미 끝나 있는 실행의
 결과를 모아 정리하는 것이라 사람을 한 명만 부른다 — 그래서 값이 싸다.


 ■ 놓치기 쉬운 것 하나

 **프로그램이 다섯 개 돈다.** 이 파일이 하나이고, ②에서 켜는 장비 네 대가 각각
 별개의 프로그램이다. 그래서 이 파일에 디버거를 붙여도 `tools_*.py` 안에서는
 멈추지 않는다 — 남의 프로그램이기 때문이다.

 그 안에서 멈추려면 두 가지 길이 있다:
   · `python debug_harness.py data`  — 장비를 이 프로그램 안으로 불러들여 쓴다
   · `MEMSTARA_DEBUGPY=data` 로 켜고 디버거를 그 장비에 따로 붙인다




 ■ 코드 구조

   main()             인자를 읽고, 환경을 검사하고, 잠금을 잡고 run() 을 부른다
     └ run()          위 ①~⑥ 이 순서대로 들어 있다
"""

from __future__ import annotations

# ---- 표준 라이브러리 --------------------------------------------------------
import argparse   # 명령줄 인자 (--trials 3 같은 것)
import asyncio    # 비동기 실행. 이 파일의 함수 대부분이 async 다
import csv        # 데이터셋의 첫 줄(컬럼 이름)만 읽는 데 쓴다
import json       # 도구가 돌려주는 JSON 문자열을 파이썬 값으로
import os         # 환경변수 읽기
import re         # 비밀번호 가리기 정규식 하나에만 쓴다
import sys        # sys.executable (지금 이 파이썬의 경로) 과 stderr 출력
import time       # 단계마다 걸린 시간을 재는 데만 쓴다
import uuid       # 추적 파일을 쓸 때 run_id 문자열을 UUID 로 되돌린다
from datetime import datetime
from pathlib import Path
from typing import Any

# ---- 바깥 패키지 ------------------------------------------------------------
import asyncpg    # PostgreSQL 비동기 드라이버. 판을 직접 조회할 때만 쓴다

# ---- 이 폴더의 다른 파일들 --------------------------------------------------
# bootstrap 을 **가장 먼저** 불러온다. 그 안에서 LITELLM_LOG 을 설정하는데, litellm 은
# import 되는 순간 그 값을 읽는다. 아래 pipeline_core 가 litellm 을 끌고 오므로,
# 순서가 뒤바뀌면 LLM 요청 본문이 한 건도 안 남는다 — 아무 오류 없이.
import bootstrap  # noqa: F401  (import 자체가 목적이다)

# blackboard.py — 판 테이블의 정의와 접속 정보
from blackboard import BoardBusy, dsn, run_lock
# logging_setup.py — 실행마다 폴더를 만들고 로그를 파일로도 남긴다
from logging_setup import drain_llm_requests, new_run_dir, setup_logging, tee_console
# pipeline_core.py — 두 파이프라인(02, 03)이 공유하는 부분
from pipeline_core import (
    BOARD_SERVERS,           # 단계별로 접근이 허용된 도구 서버
    BOARD_TOOLS,             # 단계별로 허용된 개별 도구 이름
    PERSPECTIVES,            # 시행마다 다르게 주는 관점 문구
    perspective_for,         # 시행 번호 → 관점 문구
    provision_board_agents,  # 에이전트 다섯을 만들거나 찾아온다
    temperature_for,         # 시행 번호 → 온도
    tools_for,               # 레지스트리에서 쓸 도구만 골라낸다
)
from settings import Settings   # .env 를 읽어 core 에 넘길 설정 객체

# .env 가 둘이라 프로그램이 직접 읽는다 — main() 의 주석 참고.
from dotenv import load_dotenv
# 실행 하나를 사람이 읽을 수 있게 풀어 쓰는 함수. dump_all 이 아니라 render 를 쓴다 —
# dump_all 은 02 경로의 todo_rows.json 모양을 전제하기 때문이다. write_traces() 참고.
from trace_run import render

# ---- agentic-core (옆 저장소, editable 설치) --------------------------------
from agentic_core import configure
from agentic_core.mcp.registry import MCPServerRegistry
from agentic_core.runner import create_run, execute_run
from agentic_core.services.mcp_service import (
    get_server_by_name,
    hydrate_registry,
    register_server,
    update_server,
)

# 이 파일이 있는 폴더. 도구 서버의 경로를 만들 때 쓴다.
HERE = Path(__file__).parent
OUT_DIR = HERE / "outputs"

# The stages that take work off the board, in the order a task passes through them.
#
# ↑ 게시판에서 **일을 떼어 가는** 사람들.
#
#   사람은 다섯인데 여기는 셋뿐이다. 빠진 둘은 이유가 **서로 다르다.**
#
#   ┌ 가설 담당이 빠진 이유
#   │   그 사람은 일을 떼어 가는 게 아니라 **붙이는** 사람이다. 게시판이 비어
#   │   있을 때 첫 종이를 만들어 붙인다. 그러니 "떼어 갈 게 있나" 를 물을 이유가
#   │   없다 — 물어봐야 언제나 없다.
#   │
#   │   그리고 붙이는 시점도 다르다. 가설 담당은 아래 ④ 에서 **미리 정해진 횟수만큼**
#   │   불린다(시행 3회면 세 번). 반면 이 셋은 ⑤ 에서 **게시판 상태를 보고** 필요할
#   │   때만 불린다.
#   │
#   └ 보고 담당이 빠진 이유
#       그 사람은 게시판을 아예 안 본다. **완료 서랍**(끝난 것만 모인 곳)을 읽는다.
#       게시판에 종이가 남아 있든 말든 상관없고, 그래서 맨 마지막에 딱 한 번 불린다.
#       ⑤ 루프가 끝난 뒤 ⑥ 에서 부른다.
#
#   순서도 그냥 나열이 아니다. 종이 한 장이 실제로 지나가는 순서이고, ⑤ 의 루프가
#   **매 바퀴 이 순서대로** 훑는다. 그래서 운이 좋으면 한 바퀴에 종이 한 장이
#   데이터 → 학습 → 해석까지 내리 지나갈 수 있다. 순서를 뒤집으면 그런 일이
#   안 생기고 바퀴 수만 늘어난다.
CLAIMING_STAGES = ("data", "ml", "interpreter")

# How long to wait when every remaining task is in progress and none is stale yet.
#
# ↑ 게시판에 남은 것이 전부 "누군가 하고 있는 중" 일 때 **몇 초 쉴까**.
#   쉬지 않고 계속 게시판만 들여다보면 아무 소득 없이 컴퓨터만 바쁘다.
POLL_SECONDS = 15

# ↑ **사람 이름 → 종이에 적히는 이름.**
#
#   왜 이런 표가 필요한가 — 두 이름이 항상 같지는 않기 때문이다.
#
#       사람 이름        종이에 적히는 이름
#       data          →  data          같다
#       ml            →  ml            같다
#       interpreter   →  interpret     **다르다**  ← 이것 하나 때문에 표가 있다
#
#   마지막 하나만 다르다. 그런데 그 하나 때문에 `counts["interpreter/ready"]` 를
#   찾으면 언제나 0 이 나오고, 해석 담당이 영영 안 불린다. 아무 오류도 없이.
#   그래서 헷갈릴 여지를 없애려고 표로 못박아 둔다.
#
#   여기도 셋뿐인 이유는 위 CLAIMING_STAGES 와 같다 — 가설 담당과 보고 담당은
#   게시판에서 종이를 떼어 가지 않으므로 찾아볼 일이 없다.
#
#   참고로 게시판의 종이에 적힐 수 있는 이름은 넷이다
#   (blackboard.py 의 TASK_TYPES: hypothesis · data · ml · interpret).
#   `hypothesis` 는 종이의 **첫 상태**로만 쓰이고 곧바로 `data` 로 넘어간다.
STAGE_TASK_TYPE = {"data": "data", "ml": "ml", "interpreter": "interpret"}


# --------------------------------------------------------------------------- #
#  화면에 단계를 표시하는 것들
# --------------------------------------------------------------------------- #
#
# 왜 필요한가 — 디버거로 따라갈 때 화면이 로그로 가득 차서, 지금 어느 단계인지
# 눈으로 찾기가 어렵다. 맨 위 「이 파일을 읽는 법」 의 ①~⑥ 이 화면에도 그대로
# 보이게 한다.
#
# stdout 으로 나간다. 이건 부모 프로세스이므로 상관없다 — MCP 프로토콜이 지나가는
# 것은 자식들의 stdout 이다.

_STEP_STARTED: dict[str, float] = {}


def step(number: str, title: str, detail: str = "") -> None:
    """한 단계의 시작을 굵게 표시한다.

    예)
        ══════════════════════════════════════════════════════════
         ② 장비 네 대를 켠다
        ══════════════════════════════════════════════════════════
    """
    print()
    print("=" * 74)
    print(f" {number} {title}" + (f"   —   {detail}" if detail else ""))
    print("=" * 74)
    _STEP_STARTED[number] = time.monotonic()


def done(number: str, result: str = "") -> None:
    """방금 끝난 단계의 결과와 걸린 시간을 한 줄로.

    시간을 같이 찍는 이유 — 어디서 오래 걸리는지가 눈에 보여야 한다. 대개
    LLM 을 부르는 단계가 나머지 전부를 합친 것보다 오래 걸린다.
    """
    took = time.monotonic() - _STEP_STARTED.get(number, time.monotonic())
    print(f"   ✓ {result}" + f"   ({took:.1f}초)" if result else f"   ✓ ({took:.1f}초)")


def note(text: str) -> None:
    """단계 안에서 진행 상황을 한 줄 알린다. 들여쓰기로 단계에 속함을 보인다."""
    print(f"   · {text}")


def _redacted_dsn() -> str:
    """The board's address with the password removed, safe to print in an error."""
    # postgresql://사용자:비밀번호@호스트/디비  →  postgresql://사용자:***@호스트/디비
    # 오류 메시지에 접속 주소를 찍어야 하는데 비밀번호까지 찍히면 안 되기 때문이다.
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn())


# provider 마다 있어야 하는 자격증명. `--provider` 로 고른 것만 검사한다.
#
# 이 표가 없던 동안은 자격증명이 비어도 **첫 LLM 호출까지 가서야** 터졌다. 그때는
# 이미 씨뿌리기 한 번을 쓴 뒤이고, 판에도 줄이 남는다. 시작 전에 멈추는 편이
# 낫다 — 판이 깨끗하게 남고, 무엇을 채워야 하는지도 그 자리에서 알 수 있다.
_PROVIDER_KEYS = {
    "azure_foundry": ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


async def check_environment(provider: str = "", y_column: str = "") -> list[str]:
    """Everything missing, reported at once, before anything starts.

    ↑ **시작하기 전에 준비물을 전부 확인한다.**

      빠진 것을 하나씩 알려 주지 않고 **한꺼번에** 모아 준다. 하나 고치고 다시
      돌렸더니 또 하나가 없더라 — 이걸 없애려는 것이다.

      빈 목록이 돌아오면 "준비 끝" 이라는 뜻이다.

    Args:
        provider: `--provider` 로 고른 값. 그것에 맞는 자격증명만 검사한다.
            빈 문자열이면 자격증명 검사를 건너뛴다.
        y_column: `--y-column` 으로 고른 결과변수. 데이터셋에 그 이름이 실제로
            있는지 확인한다. 빈 문자열이면 건너뛴다.
    """
    problems: list[str] = []   # 여기 담긴 게 하나라도 있으면 실행하지 않는다

    # Two databases, and they are not interchangeable. core keeps its agents and run
    # history in AGENTIC_DATABASE_URL; the board and the results table live in Memstara's
    # own server (MEMSTARA_DATABASE_URL, docker-compose.yml). Only the first is required
    # here — the second has a working default pointing at the compose container.
    #
    # ↑ DB 가 둘이고 서로 바꿔 쓸 수 없다는 뜻이다.
    #   AGENTIC_DATABASE_URL  : core 의 것 — 사람들의 역할 설명서와 실행 이력  (5453)
    #   MEMSTARA_DATABASE_URL : 우리 것   — 게시판과 완료 서랍              (5463)
    for name, hint in (
        ("AGENTIC_OKF_BUNDLE_DIR", "the knowledge source folder"),
        ("MEMSTARA_DATASET_PATH", "the dataset csv"),
        ("MEMSTARA_OUTPUT_DIR", "where sub-datasets go"),
        ("AGENTIC_DATABASE_URL", "core's own database — agents and run history"),
    ):
        value = os.environ.get(name, "").strip()   # 없으면 빈 문자열
        if not value:
            problems.append(f"{name} is not set — {hint}")

    # LLM 자격증명. 이것이 비면 첫 에이전트 호출에서
    # "Azure Anthropic requests require an api_base" 로 죽는다 — 씨뿌리기 한 번을
    # 이미 쓴 뒤다. 여기서 잡으면 아무것도 안 쓰고 멈춘다.
    #
    # 이 값들은 `agentic-core/.env` 에 있다. main() 이 그 파일을 읽어 주므로
    # 여기까지 왔는데도 비어 있다면 그 파일에 진짜로 없는 것이다.
    for name in _PROVIDER_KEYS.get(provider, ()):
        if not os.environ.get(name, "").strip():
            problems.append(
                f"{name} is not set — needed for --provider {provider}. "
                "Check agentic-core/.env."
            )

    # Reachability, not just presence. An unreachable board fails later as an opaque
    # tool error inside an agent, which reads like a prompt problem.
    #
    # ↑ 주소가 적혀 있는지만 보는 게 아니라 **실제로 붙어 보는** 이유다. 안 붙으면
    #   나중에 사람이 일하는 도중에 알 수 없는 오류로 터지는데, 그러면 지시문이
    #   잘못된 것처럼 보인다 — 엉뚱한 곳을 고치게 된다.
    try:
        conn = await asyncpg.connect(dsn())
        await conn.close()
    except Exception as e:  # noqa: BLE001 - any failure to reach it is the same problem
        problems.append(
            f"Memstara's database is not reachable at {_redacted_dsn()} — {type(e).__name__}. "
            "Start it with `docker compose up -d` in this folder."
        )

    # The outcome column has to exist in the dataset, and nothing checked that until
    # now. A wrong `--y-column` was caught in tools_data.py, deep inside the data stage,
    # after every hypothesis agent had already been paid for — and the run still ended
    # "successfully" and wrote a report full of nulls. The default is `outcome`, which
    # is not a column in this cohort, so the default path always went that way.
    #
    # ↑ **결과변수가 데이터에 실제로 있는지 여기서 본다.** 지금까지 아무도 안 봤다.
    #   이름이 틀리면 데이터 단계 한복판에서야 걸리는데, 그때는 가설 담당을 이미
    #   다 부른 뒤다. 그러고도 실행은 "성공" 으로 끝나고 빈 보고서를 쓴다.
    #   기본값 `outcome` 은 이 코호트에 없는 이름이라 기본으로 돌리면 반드시 이 길이다.
    dataset = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if y_column and dataset:
        try:
            # Only the header row is read. The file is large and the answer is on line 1.
            # ↑ 첫 줄만 읽는다. 파일이 크고 답은 첫 줄에 있다.
            with open(dataset, newline="", encoding="utf-8") as fh:
                header = next(csv.reader(fh))
        except Exception as e:  # noqa: BLE001 - unreadable and absent are the same problem here
            problems.append(
                f"MEMSTARA_DATASET_PATH cannot be read at {dataset} — {type(e).__name__}."
            )
        else:
            if y_column not in header:
                # Near-misses only, never the whole column list. tools_data.py hides the
                # outcome column from its error for a reason (an agent that learns the
                # name can use it as a feature); a console message is safer but the same
                # restraint keeps 1,393 names out of the terminal.
                #
                # ↑ 비슷한 이름 몇 개만 준다. 컬럼 1,393개를 다 찍지 않는다.
                near = [c for c in header if y_column.upper() in c.upper()][:5]
                hint = f" Did you mean: {', '.join(near)}?" if near else ""
                problems.append(
                    f"--y-column '{y_column}' is not a column in the dataset."
                    f"{hint} ({len(header)} columns in {Path(dataset).name})"
                )

    return problems


async def setup_tools() -> MCPServerRegistry:
    """Connect the five tool servers, including the board.

    ↑ **장비 다섯 대를 켠다.** 여기서 프로그램이 여섯 개가 된다.

      아래 다섯 줄이 각각 별개의 프로그램을 띄운다. 서로 글자를 주고받으며 대화한다
      — 전화선 같은 것이 아니라, 그냥 한쪽이 쓰면 다른 쪽이 읽는 방식이다.

      **그래서 이 파일에 디버거를 붙여도 저 안에서는 안 멈춘다.** 남의 프로그램이다.
    """
    # 디버거로 돌릴 때 자식마다 나오는 이 경고를 끈다:
    #
    #     Debugger warning: It seems that frozen modules are being used ...
    #
    # **여기서 정해야 한다.** debugpy 는 자식 파이썬이 시작하는 순간 검사하므로,
    # 자식 코드 안에서 끄면 이미 늦다. 부모가 미리 넣어 두고 `settings.py` 의
    # 허용 목록에 있어야 자식에게 도착한다.
    #
    # 경고 내용 자체는 표준 라이브러리 **안쪽** 얘기라 우리 코드와 무관하다.
    os.environ.setdefault("PYDEVD_DISABLE_FILE_VALIDATION", "1")

    registry = MCPServerRegistry()   # 연결된 서버와 그 도구 목록을 들고 있는 그릇

    # ↑ `sys.executable` 은 **지금 이 파일을 돌리고 있는 파이썬 그 자체**를 가리킨다.
    #   그래서 이 파일을 어느 환경에서 띄우든 장비 다섯도 **같은 환경**으로 뜬다.
    #   경로를 손으로 적어 두면 환경을 바꿀 때마다 여기도 고쳐야 한다.
    servers = [
        ("okf", f"{sys.executable} {HERE / 'tools_okf.py'}"),
        ("memstara-data", f"{sys.executable} {HERE / 'tools_data.py'}"),
        ("memstara-ml", f"{sys.executable} {HERE / 'tools_ml.py'}"),
        ("memstara-blackboard", f"{sys.executable} {HERE / 'tools_blackboard.py'}"),
        # The semantic matcher, same server 02 starts. Without it the board's
        # hypothesis agent picks column names by eye off `describe_dataset`, which
        # is the thing the matcher was built to replace — and the two pipelines
        # then choose columns by different means, so their AUCs are not comparable.
        # Needs the cache: `python scripts/build_matcher_cache.py`.
        ("semantic-matcher", f"{sys.executable} {HERE / 'tools_matcher.py'}"),
    ]
    for name, command in servers:
        existing = await get_server_by_name(name)   # core DB 에 이미 등록돼 있나
        if existing is None:
            # 처음 보는 서버 — 새로 등록한다
            await register_server(name=name, transport="stdio", command=command, registry=registry)
        elif existing.command != command:
            # ↑ 이미 등록돼 있는데 **띄우는 명령이 달라졌다** (예: 파이썬 경로가 바뀜).
            #   갱신해 준다. 이 한 줄 덕분에 환경을 바꿔도 알아서 따라온다.
            await update_server(existing.id, command=command, registry=registry)

    # 등록된 서버들에 실제로 접속하고 도구 목록을 받아 온다.
    failed = await hydrate_registry(registry=registry)
    if failed:
        # 하나라도 못 붙으면 알린다. 여기서 멈추지는 않는다 — 나머지로 갈 수 있는
        # 만큼은 가 보는 편이 무엇이 고장났는지 알기에 낫다.
        print(f"!! MCP reconnect failed: {failed}", file=sys.stderr)
    return registry


# 이 실행에서 부른 에이전트를 부른 순서대로 모은다.
#
# 왜 목록이고 왜 시행별이 아닌가 — 02 경로는 한 시행이 네 단계를 차례로 지나므로
# `TodoRow.run_ids[stage]` 로 묶인다(pipeline_core.py:664). 판 경로는 다르다.
# `call_agent(data, ...)` 한 번이 **어느 과제를 집을지는 그 시점의 판이 정한다.**
# 그래서 시행으로 묶을 수가 없고, 부른 순서 그대로 남기는 것이 사실에 맞다.
#
# 여기 모인 run_id 로 실행이 끝날 때 추적 파일을 쓴다. 그 파일에는 에이전트가 도구에
# 무엇을 물었고 무엇이 돌아왔는지가 그대로 들어 있다 — 디버거로는 볼 수 없는 것이다.
# 이걸 안 모으면 core DB 에 기록이 남아도 **어느 실행이 어느 단계였는지 알 수 없다.**
_CALLS: list[dict[str, Any]] = []


async def call_agent(
    agent_id,
    prompt: str,
    *,
    tools,
    registry,
    temperature: float | None = None,
    stage: str = "",
) -> str:
    """Run one agent once and return its text, or "" if the run did not complete.

    ↑ **사람 한 명을 불러 일을 시키고, 그 사람이 한 말을 받아 온다.**

      이 파일에서 **모델을 부르는 곳은 여기 하나뿐**이다. 돈과 시간이 드는 자리도
      여기뿐이다. 나머지는 전부 게시판을 보거나 파일을 쓰는 일이라 공짜다.

    Args:
        stage: 추적 파일 이름에 쓸 딱지 ("hypothesis" · "data" · "report" …).
            비워 두면 순번만 붙는다.
    """
    # 온도를 준 경우에만 덮어쓴다. None 이면 에이전트에 설정된 기본값을 쓴다.
    overrides = {"temperature": temperature} if temperature is not None else None

    # core 는 "실행(run)" 을 먼저 만들고 그 다음 실행한다. 두 단계로 나뉘어 있어서
    # 실행 기록이 DB 에 남고, 나중에 trace_run.py 로 되짚어 볼 수 있다.
    run = await create_run(agent_id=agent_id, user_input=prompt, model_config_overrides=overrides)

    # **실행 전에** 적는다. 실행 도중에 죽어도 그 run_id 는 남아야 하기 때문이다 —
    # 죽은 실행이야말로 되짚어 봐야 하는 것이다.
    _CALLS.append(
        {
            "seq": len(_CALLS),
            "stage": stage or "?",
            "run_id": str(run.id),
            "prompt": prompt,
            "status": "started",
        }
    )

    # ── 여기가 LLM 이 도는 곳이다 ───────────────────────────────────────────
    # `execute_run` 은 agentic-core 의 함수다. 안에서 생각(reason) → 도구 호출(act)
    # → 관찰을 반복한다. **그 안으로는 들어가지 않는다** — launch.json 의
    # `justMyCode: true` 가 F11 을 여기서 넘겨 준다. 우리가 보는 것은 결과뿐이다.
    #
    # 안에서 무슨 일이 있었는지는 아래 _trace_one() 이 파일로 뽑아 준다.
    result = await execute_run(run_id=run.id, registry=registry, available_tools=tools)
    _CALLS[-1]["status"] = getattr(result.status, "value", str(result.status))
    if result.error:
        _CALLS[-1]["error"] = str(result.error)

    # 실행이 끝나자마자 **이 한 건의** 추적 파일을 쓴다.
    #
    # 왜 여기서 쓰나 — 끝에 한꺼번에 쓰면 디버깅 중에는 아무 쓸모가 없다. 파일이
    # 실행이 다 끝나야 생기기 때문이다. 여기서 쓰면 `await call_agent(...)` 다음 줄의
    # 브레이크포인트에 멈춘 그 순간 `trace/00_hypothesis0.txt` 를 열어 방금 무슨
    # 일이 있었는지 읽을 수 있다 — 어떤 도구를 어떤 인자로 불렀고 무엇이 돌아왔는지.
    await _trace_one(_CALLS[-1])

    # 방금 그 사람이 실제로 무엇을 했는지 화면에 풀어 준다. 자르지 않은 판은
    # trace/ 안의 파일에 있다.
    await show_what_agent_did(_CALLS[-1])

    # 실패했으면 빈 문자열. 부르는 쪽은 대개 결과를 판에서 다시 읽으므로,
    # 여기서 예외를 던지기보다 조용히 비우고 다음 바퀴에 맡긴다.
    if result.error or result.status != "completed":
        return ""

    # 에이전트 출력은 보통 {"result": "..."} 모양의 JSON 이다. 아니면 원문 그대로.
    try:
        return str(json.loads(result.output or "").get("result", ""))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return result.output or ""


# 추적 파일이 나갈 폴더. run() 이 시작할 때 정해 준다.
#
# 전역인 이유 — `call_agent` 는 실행 폴더를 모른다. 인자로 넘기면 부르는 쪽 네 군데가
# 전부 그것을 들고 다녀야 하는데, 그건 이 파일이 하려는 일과 상관없는 짐이다.
_TRACE_DIR: Path | None = None


def _short(value: Any, width: int = 88) -> str:
    """값 하나를 한 줄로 줄인다. 줄바꿈은 공백으로 눕힌다."""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= width else s[:width] + " …"


async def show_what_agent_did(call: dict[str, Any]) -> None:
    """방금 부른 사람이 **실제로 무엇을 했는지** 화면에 풀어 준다.

    왜 이게 필요한가 — 화면에 "보고 담당을 불렀다" 만 나오면, 그 사람이 어떤 도구를
    어떤 값으로 부르고 무엇을 받았는지가 안 보인다. 그건 전부 core 안에서 일어나고,
    디버거로도 안 보인다(core 는 블랙박스로 두기로 했다).

    core 가 `run_steps` 에 남긴 것을 읽어 사람이 읽을 수 있게 줄인다. 같은 내용의
    **자르지 않은 판**은 `trace/NN_단계.txt` 에 따로 쓰인다 — 여기는 훑어보는 용도다.

    한 사람의 차례는 이렇게 생겼다:

        sense    받은 지시
        reason   생각 —— "무엇을 하겠다"
        act      행동 —— 도구를 부르거나, 최종 답을 낸다
        reason   다시 생각 (도구 결과를 보고)
        act      ...
    """
    from agentic_core.runner import get_run, get_run_steps

    try:
        rid = uuid.UUID(call["run_id"])
        run = await get_run(rid)
        steps = await get_run_steps(rid)
    except Exception as e:  # noqa: BLE001 - 화면 표시가 실행을 막으면 안 된다
        note(f"(무엇을 했는지 못 읽었다: {type(e).__name__})")
        return

    tokens = (getattr(run, "token_usage", None) or {}) if run else {}
    cost = float(getattr(run, "cost_estimate", 0) or 0) if run else 0.0
    print(f"   ┌─ {call['stage']} 가 한 일 "
          f"(단계 {len(steps)}개 · 토큰 {tokens.get('prompt_tokens', 0)}/"
          f"{tokens.get('completion_tokens', 0)} · ${cost:.4f})")

    for s in steps:
        phase = getattr(s.phase, "value", str(s.phase))
        # 필드 이름은 `output` 이다. DB 컬럼은 `output_data` 인데 파이썬 쪽은
        # `output` 으로 노출된다 — 컬럼 이름을 보고 그대로 쓰면 AttributeError 다.
        out = s.output or {}

        if phase == "reason":
            # 무엇을 하겠다고 마음먹었나.
            thought = out.get("thought") if isinstance(out, dict) else None
            if thought:
                print(f"   │  생각  {_short(thought)}")

        elif phase == "act":
            # 도구를 실제로 불렀으면 그 인자와 결과를 보여 준다. 이것이 핵심이다.
            tc = s.tool_call
            for one in _flatten_calls(tc):
                server = one.get("server", "?")
                tool = one.get("tool", "?")
                args = one.get("arguments", {})
                result = one.get("result", "")
                print(f"   │  도구  {server}.{tool}({_short(args, 70)})")
                print(f"   │        → {_short(result, 86)}")
            # 도구 없이 최종 답만 낸 차례.
            if not _flatten_calls(tc) and isinstance(out, dict):
                for r in (out.get("results") or []):
                    if r.get("action") == "final_answer":
                        print(f"   │  답    {_short(r.get('result', ''), 86)}")

    # 모델에 보낸 요청은 **개수와 크기만** 화면에 낸다. 한 요청이 수만 자라
    # 원문을 여기 찍으면 화면이 못 쓰게 된다 — 원문은 trace 파일에 있다.
    n_req = call.get("llm_requests", 0)
    if n_req:
        print(f"   │  요청  LLM {n_req}회 — 보낸 원문은 "
              f"trace/{call['seq']:02d}_{call['stage']}.llm.txt 에 있다")
    print("   └─")


def _flatten_calls(tool_call: Any) -> list[dict[str, Any]]:
    """`tool_call` 이 올 수 있는 **세 가지 모양**을 하나로 편다.

    core 는 한 차례에 도구를 몇 개 부를 수도 있어서 모양이 갈린다:

        None 또는 JSON 의 null   부른 도구가 없다
        {"server":…, "tool":…}   하나만 불렀다
        {"calls":[{…},{…}]}      여러 개를 불렀다

    이걸 안 맞추면 묶음으로 부른 차례가 통째로 안 보이거나, 반대로 빈 것을
    한 건으로 세게 된다.
    """
    if not tool_call or tool_call == "null":
        return []
    if isinstance(tool_call, str):
        try:
            tool_call = json.loads(tool_call)
        except json.JSONDecodeError:
            return []
    if not isinstance(tool_call, dict):
        return []
    if "calls" in tool_call:
        return [c for c in tool_call["calls"] if isinstance(c, dict)]
    return [tool_call] if tool_call.get("tool") else []


async def _trace_one(call: dict[str, Any]) -> None:
    """실행 한 건의 추적 파일을 쓴다. 실패해도 파이프라인을 멈추지 않는다.

    파일에 들어가는 것: 상태 · 토큰 · 비용 · 단계마다의 생각과 행동 · **도구 호출의
    인자와 결과**. 마지막 것이 핵심이다 — agentic-core 안에서 일어난 일이라
    브레이크포인트로는 볼 수 없다.
    """
    if _TRACE_DIR is None:
        return

    # **이미 쓴 것은 다시 쓰지 않는다.**
    #
    # 끝의 그물(write_traces)이 모든 호출을 한 번 더 훑는데, 그때 다시 쓰면 파일이
    # 새로 만들어지면서 **LLM 요청이 사라진다** — 요청은 꺼내면서 비우는 방식이라
    # 두 번째에는 0건이기 때문이다. 실제로 그렇게 날려 먹고 찾았다.
    if call.get("traced"):
        return

    stem = f"{call['seq']:02d}_{call['stage']}"
    path = _TRACE_DIR / f"{stem}.txt"
    llm_path = _TRACE_DIR / f"{stem}.llm.txt"
    try:
        with path.open("w", encoding="utf-8") as fh:
            # readable=True — 사람이 읽으라고 찍는다. 자르지는 않는다.
            # 빠지는 것은 **다른 줄이 이미 말한 것**뿐이다(trace_run.render 설명 참고).
            await render(call["stage"], uuid.UUID(call["run_id"]),
                         full=True, summary=False, stream=fh, readable=True)

        # 모델에 **보낸 요청**. core 는 이것을 저장하지 않으므로 litellm 의 로그에서
        # 가로챈 것이다(logging_setup 참고). 꺼내면서 비우므로 그 에이전트가 부른
        # 만큼만 들어간다 — 다음 사람 것과 안 섞인다.
        #
        # **왜 옆 파일로 빼나** — 요청은 부를 때마다 그때까지의 대화를 통째로 다시
        # 담는다. 그래서 6번 부르면 같은 내용이 여섯 겹으로 쌓인다(실측 261KB).
        # 위 추적 파일에 이어 붙이면, 정작 읽으려던 본문이 그 뒤에 묻힌다.
        requests = drain_llm_requests()
        call["llm_requests"] = len(requests)
        if requests:
            with llm_path.open("w", encoding="utf-8") as lf:
                print("=" * 100, file=lf)
                print(f"{call['stage']} 가 모델에 보낸 요청 {len(requests)}건", file=lf)
                print("뒤로 갈수록 앞의 대화가 다시 담긴다 — 마지막 것이 가장 크다.", file=lf)
                print("=" * 100, file=lf)
                for i, body in enumerate(requests, 1):
                    print(f"\n[{i}/{len(requests)}] " + "-" * 88, file=lf)
                    print(body, file=lf)
        call["traced"] = True
    except Exception as e:  # noqa: BLE001 - 기록 실패가 실행을 망기면 안 된다
        print(f"  추적 실패 {call['seq']:02d} {call['stage']}: {type(e).__name__}: {e}",
              file=sys.stderr)


async def write_traces(run_dir: Path) -> int:
    """끝에 한 번 더 훑는 그물. 쓴 개수를 돌려준다.

    평소에는 `_trace_one` 이 호출마다 이미 썼고, 이미 쓴 것은 **건너뛴다.**
    남겨 두는 이유는 **중간에 죽은 경우**다 — 실행 중에 예외가 나거나 Ctrl-C 가
    들어오면 마지막 한 건은 `_trace_one` 까지 못 갔을 수 있다.

    건너뛰지 않으면 파일을 새로 쓰면서 LLM 요청이 사라진다(위 주석 참고).

    `trace_run.dump_all` 을 쓰지 않는 이유 — 그 함수는 `todo_rows.json` 의
    시행별 `run_ids` 모양을 전제한다(trace_run.py:161). 판 경로는 그 모양이 아니므로
    한 층 아래인 `render()` 를 직접 부른다.
    """
    if not _CALLS:
        return 0

    out_dir = run_dir / "trace"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 목록 자체도 남긴다. 나중에 trace_board.py 나 손으로 되짚을 때 쓴다.
    (run_dir / "runs.json").write_text(
        json.dumps(_CALLS, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for call in _CALLS:
        await _trace_one(call)
    return len(_CALLS)


async def board_state(registry: MCPServerRegistry, run_tag: str) -> dict:
    """What is on the board right now, straight from the tool the agents use.

    ↑ **게시판을 지금 찍어 본다.**

      데이터베이스를 직접 뒤지지 않고, **사람들이 쓰는 것과 똑같은 창구**로 본다.
      그래야 내가 화면에서 보는 게시판과 그들이 보는 게시판이 어긋나지 않는다.
    """
    server = await get_server_by_name("memstara-blackboard")
    from agentic_core.services.mcp_service import call_server_tool

    raw = await call_server_tool(server.id, "read_board", {"run_tag": run_tag}, registry=registry)
    # 반환이 (메타, 본문) 튜플일 때도 있고 본문만 올 때도 있다.
    text = raw[1] if isinstance(raw, tuple) else raw
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # 못 읽으면 "판이 비었다"로 취급한다. 루프가 이 값을 보고 끝내므로,
        # 읽기에 실패해 무한히 도는 것보다 낫다.
        return {"count": 0, "tasks": []}


#: Matcher tools whose calls are worth keeping. Both live on the semantic-matcher
#: server; nothing else it exposes produces candidate lists.
_MATCHER_TOOLS = ("match_concepts", "match_concept")


def _matcher_call_failed(result: Any) -> bool:
    """Did this matcher call actually answer, or did it come back an error?

    ↑ **이 매처 호출이 진짜 답을 받았는가, 오류를 받았는가.**

      This has to be asked before anything is filed as evidence. The 2026-08-30 run
      filed 27 calls into the results table whose every result was "Not authorized:
      Tool 'match_concepts' is not in this run's allowed tool set" — a dead server
      registration meant the matcher never ran, and the durable table recorded the
      refusals as if they were candidate lists.

      ↑ 8/30 실행이 실패 27건을 후보 목록처럼 결과표에 적었다. 매처 서버 등록이
        죽어 있어 한 번도 실제로 돌지 않았는데, 남는 표에는 그 거절들이 근거로
        남았다. 그것을 막는 판정이다.
    """
    if isinstance(result, dict):
        return "error" in result
    if isinstance(result, str):
        # Core refuses a tool outside the run's allowed set with a plain sentence,
        # not JSON — so it survives the parse above untouched and has to be read here.
        # ↑ core 는 허용목록 밖 도구를 JSON 이 아니라 문장으로 거절한다.
        text = result.strip()
        return text.startswith("Not authorized") or "is not in this run's allowed tool set" in text
    return False


async def harvest_match_trace(
    registry: MCPServerRegistry, call: dict[str, Any]
) -> tuple[int, int]:
    """Lift one agent run's matcher calls out of the trace and file them on the board.

    ↑ **매처가 무엇을 보고 무엇을 골랐는지를 판에 옮겨 적는다.**

      The matcher answers inside the hypothesis agent's turn and writes nothing down.
      Only the chosen columns reach the board, so the candidates that lost — and the
      scores that made them lose — existed nowhere except this run's trace, which is
      deleted whenever the run directory is. That is the gap this closes.

      Why the driver does it rather than the agent or the matcher: the agent would
      have to hand-copy hundreds of candidate rows with nothing checking the copy,
      and the matcher would need board access it is deliberately built without. The
      trace already holds every call verbatim, so nobody has to be trusted.

      Both halves come out of the same run. The matcher calls are the ones worth
      keeping; the ``create_task`` calls in the same turn say which task they belong
      to, because the agent matched and then filed in one continuous turn.

      **Only calls that answered are filed.** `match_trace` is a record of candidates
      the matcher actually returned, never a count of attempts — a refused call proves
      nothing about the cohort and must not sit in the results table looking like it
      does. Refusals are counted and reported instead, because silently dropping them
      would make "the matcher was never called" and "every call was refused" look
      identical, and those need entirely different fixes.

      ↑ **답을 받은 호출만 적는다.** `match_trace` 는 매처가 실제로 돌려준 후보의
        기록이지 시도 횟수가 아니다. 거절된 호출은 코호트에 대해 아무것도 증명하지
        않는다. 그렇다고 조용히 버리지도 않는다 — 버리면 "매처를 안 불렀다" 와
        "부른 것이 전부 거절됐다" 가 똑같이 보이는데, 이 둘은 고칠 곳이 다르다.

    Args:
        registry: the live server registry, used to reach the board tool.
        call: one entry of `_CALLS` — the run whose trace is read.

    Returns:
        `(annotated, refused)` — how many tasks were annotated, and how many matcher
        calls came back an error and were left out. `(0, 0)` is normal for a stage that
        never matched, and also what a failure returns: a missing trace must not stop
        the pipeline, since the pipeline's actual work already succeeded by the time
        this runs.
    """
    from agentic_core.runner import get_run_steps
    from agentic_core.services.mcp_service import call_server_tool

    try:
        steps = await get_run_steps(uuid.UUID(call["run_id"]))
    except Exception as e:  # noqa: BLE001 - bookkeeping must not fail the run
        note(f"(매처 기록을 못 읽었다: {type(e).__name__})")
        return 0, 0

    matcher_calls: list[dict[str, Any]] = []
    task_ids: list[int] = []
    refused = 0                    # 오류로 돌아와 근거에서 뺀 호출 수

    for s in steps:
        for one in _flatten_calls(s.tool_call):
            tool = one.get("tool") or ""
            if tool in _MATCHER_TOOLS:
                # The result is a JSON string on the wire. Parse it so the board holds
                # a real object; a string of JSON inside JSONB is readable only by
                # parsing twice, and whoever reads it later will not know to.
                result = one.get("result") or ""
                try:
                    result = json.loads(result) if isinstance(result, str) else result
                except json.JSONDecodeError:
                    pass
                if _matcher_call_failed(result):
                    refused += 1
                    continue
                matcher_calls.append({
                    "tool": tool,
                    "arguments": one.get("arguments") or {},
                    "result": result,
                })
            elif tool == "create_task":
                # create_task answers {"task_id": N}. That is the only link between a
                # matcher call and the row it ended up justifying.
                try:
                    tid = json.loads(one.get("result") or "{}").get("task_id")
                except (json.JSONDecodeError, AttributeError):
                    tid = None
                if isinstance(tid, int):
                    task_ids.append(tid)

    if not matcher_calls or not task_ids:
        return 0, refused

    server = await get_server_by_name("memstara-blackboard")
    written = 0
    for tid in task_ids:
        try:
            await call_server_tool(
                server.id,
                "attach_match_trace",
                {"task_id": tid, "match_trace": json.dumps(matcher_calls, ensure_ascii=False)},
                registry=registry,
            )
            written += 1
        except Exception as e:  # noqa: BLE001 - same reason as above
            note(f"(과제 {tid} 에 매처 기록을 못 붙였다: {type(e).__name__})")
    return written, refused


async def call_board_tool(registry: MCPServerRegistry, tool: str, args: dict[str, Any]) -> Any:
    """Call one board tool from the driver rather than through an agent.

    Bookkeeping the pipeline knows about and no agent does — that a wave has ended, that
    a trace is ready to file — has to be written by whoever knows it. These tools are
    kept out of BOARD_TOOLS so no agent can reach them.
    """
    from agentic_core.services.mcp_service import call_server_tool

    server = await get_server_by_name("memstara-blackboard")
    raw = await call_server_tool(server.id, tool, args, registry=registry)
    # 반환이 (오류인가, 본문) 튜플일 때도 있고 본문만 올 때도 있다 — read_board_via_tool
    # 이 이미 같은 자리에서 같은 처리를 한다.
    text = raw[1] if isinstance(raw, tuple) else raw
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


async def questions_for_wave(
    registry: MCPServerRegistry,
    agents: dict[str, Any],
    by_stage: dict[str, Any],
    *,
    run_tag: str,
    wave: int,
    want: int,
) -> list[dict[str, Any]]:
    """Ask the curator for this wave's questions, then read back what it banked.

    ↑ **이번 파도에 무엇을 물을지 정한다.**

      Read back rather than trust the return value: the curator answers in prose, and
      what matters is what actually landed in the bank. propose_questions is also the
      only thing that can reject a question, so its verdict is the one to read.

      Returns fewer than `want` without complaint. A curator that can only ground three
      questions in the corpus should propose three; padding to a target is exactly the
      habit that produced questions nothing could answer.

    Returns:
        Bank rows, newest first, at most `want`. An empty list means the caller should
        fall back to the built-in perspective list.
    """
    before = await call_board_tool(registry, "read_questions", {"status": "open", "limit": 200})
    known = {q["question_id"] for q in (before or {}).get("questions", [])}

    ask = (
        f"Propose {want} question(s) for wave {wave} of run '{run_tag}'. "
        f"Call propose_questions once, with origin_run='{run_tag}' and origin_wave={wave}. "
    )
    ask += (
        "This is the first wave, so read_results has nothing yet — work from the corpus."
        if wave == 0
        else f"Call read_results with run_tag='{run_tag}' first and let those results "
             "decide what is worth asking next."
    )
    try:
        await call_agent(
            agents["curator"], ask,
            tools=by_stage["curator"], registry=registry, stage=f"curator{wave}",
        )
    except Exception as e:  # noqa: BLE001 - the fallback below is the point
        note(f"(질문 담당이 실패했다: {type(e).__name__} — 기본 관점 목록으로 간다)")
        return []

    after = await call_board_tool(registry, "read_questions", {"status": "open", "limit": 200})
    rows = (after or {}).get("questions", [])
    fresh = [q for q in rows if q["question_id"] not in known]

    # Falling back to already-banked questions when the curator only produced duplicates
    # keeps the wave running, and a repeat of a known question is still grounded in the
    # corpus — which the built-in list is not.
    if not fresh:
        note("(새 질문이 없다 — 은행에 있던 것을 다시 쓴다)")
        fresh = rows
    return fresh[:want]


def summarise(tasks: list[dict]) -> tuple[dict[str, int], list[tuple[int, int]]]:
    """Counts per (type, status), and which tasks have actually been retried.

    `attempts` counts *claims*, not failures. A task that goes data -> ml -> interpret
    is claimed three times and finishes with attempts=3, having failed nothing. Reading
    that number as a retry count made a clean run print "재시도 최대 3회", which is the
    opposite of the truth.

    That matters more here than it would elsewhere: retries are unlimited by decision,
    so this display is the only thing telling a person whether to stop. A false alarm
    makes it useless.

    A task is being retried when it has been claimed more times than the stages it has
    passed through. `stage_index` gives how many claims a healthy task would have had
    by now.

    ↑ **게시판을 한눈에 요약한다.** 돌려주는 것 둘:

        counts   {"data/ready": 2, ...}   누가 몇 장 기다리고 있나 — 화면에 찍는다
        retried  [(종이번호, 여분), ...]   **되돌아온 종이만.** 막힌 것이 있나 보려고
    """
    # 정상적인 과제가 이 단계까지 왔다면 몇 번 집혔어야 하는가.
    # 정상적으로 여기까지 온 종이라면 **몇 번 떼어졌어야 하는가**.
    # 데이터 담당이 한 번, 학습 담당이 또 한 번, 해석 담당이 또 한 번.
    stage_index = {"data": 1, "ml": 2, "interpret": 3}
    counts: dict[str, int] = {}
    retried: list[tuple[int, int]] = []

    for t in tasks:
        status, ttype = t["status"], t["task_type"]

        # 아직 안 끝난 것만 센다. 끝난 것은 현황에 안 넣는다.
        if status in ("ready", "in_progress"):
            counts[f"{ttype}/{status}"] = counts.get(f"{ttype}/{status}", 0) + 1

        # 'ready' 는 아직 그 사람이 떼어 가기 **전**이므로 한 번 뺀다.
        expected = stage_index.get(ttype, 0) - (1 if status == "ready" else 0)
        # 실제 떼어진 횟수 - 정상이라면 떼어졌을 횟수 = 여분.
        # 0 보다 크면 **누군가 하다가 실패해 되돌아온** 종이다.
        extra = (t.get("attempts") or 0) - max(expected, 0)
        if extra > 0:
            retried.append((t["task_id"], extra))

    return counts, retried


async def run(args: argparse.Namespace, run_dir: Path) -> int:
    """실행의 본체. 맨 위 「이 파일을 읽는 법」의 ①~⑥ 이 여기 순서대로 있다."""
    configure(Settings())   # .env 를 읽어 core 에 넘긴다 (DB 주소, API 키 등)
    log_path = setup_logging(level="DEBUG" if args.verbose else "INFO", log_file=run_dir / "run.jsonl")

    # 추적 파일이 나갈 곳을 먼저 정한다. 첫 에이전트를 부르기 **전에** 만들어 둬야
    # 그 호출이 끝나는 즉시 파일이 나온다 — 디버깅 중에 읽을 수 있는 이유다.
    global _TRACE_DIR
    _TRACE_DIR = run_dir / "trace"
    _TRACE_DIR.mkdir(parents=True, exist_ok=True)
    print()
    print("=" * 74)
    print(f" 판 파이프라인 — 실행 이름 '{args.run_tag}'")
    print("=" * 74)
    print(f"   시행 수     {args.trials if not args.report_only else '(보고만)'}")
    print(f"   결과변수    {args.y_column}")
    print(f"   데이터      {os.environ.get('MEMSTARA_DATASET_PATH','(없음)')}")
    print(f"   지식원      {os.environ.get('AGENTIC_OKF_BUNDLE_DIR','(없음)')}")
    print(f"   기록 폴더   {run_dir}")
    print(f"   추적 파일   {_TRACE_DIR.name}/  (사람을 부를 때마다 한 개씩 쌓인다)")

    # -- ① 다섯 사람을 부른다 --------------------------------------------
    #
    # 각자가 무슨 일을 하는 사람인지 적힌 역할 설명서를 꺼내 온다. 처음이면 새로
    # 쓴다. 여러 번 돌려도 같은 사람을 다시 찾아올 뿐 늘어나지 않는다.
    step("①", "다섯 사람을 부른다", "역할 설명서를 꺼내 온다")
    agents = await provision_board_agents(provider=args.provider, model=args.model)
    done("①", f"{len(agents)}명 준비됨 — {' · '.join(agents)}")

    # -- ② 장비 네 대를 켠다 ---------------------------------------------
    #
    # 여기서 프로그램이 다섯 개가 된다. 이 파일 하나 + 장비 넷.
    step("②", "장비 네 대를 켠다", "여기서 프로그램이 다섯 개가 된다")
    registry = await setup_tools()
    done("②", "논문 창고 · 데이터 기계 · 학습 기계 · 게시판 창구")
    try:
        # -- ③ 누가 어느 버튼을 쓸지 정한다 ------------------------------
        #
        # 사람마다 **쓸 수 있는 버튼만** 골라 준다. 전부 주면 남의 일까지 해 버리고,
        # 그러면 나중에 결과가 누구 판단이었는지 알 수 없어진다.
        by_stage = {
            stage: tools_for(registry, BOARD_SERVERS[stage], only=BOARD_TOOLS[stage])
            for stage in BOARD_TOOLS
        }
        # 누구에게 무엇이 갔는지 화면에 찍어 둔다. 나중에 로그만 봐도 확인된다.
        step("③", "누가 어느 버튼을 쓸지 정한다", "남의 일을 못 하게 자른다")
        _KO = {"hypothesis": "가설 담당", "data": "데이터 담당", "ml": "학습 담당",
               "interpreter": "해석 담당", "report": "보고 담당"}
        for stage, ts in by_stage.items():
            names = sorted(x["tool_name"] for x in ts)
            print(f"   {_KO.get(stage, stage):<10} {len(names)}개  {' · '.join(names)}")
        done("③", f"{len(by_stage)}명에게 배분")

        # -- report only ------------------------------------------------
        # -- ⑥ 만 하는 길 (--report-only) --------------------------------
        #
        # ④⑤ 를 건너뛰고 **정리만** 한다. 이미 끝나 있는 실행의 결과를 모아 한 장으로
        # 쓴다. 사람을 한 명(보고 담당)만 부르므로 값이 싸다.
        #
        # 중단됐거나 일부만 끝난 실행에서도, 그때까지 쌓인 것으로 보고서를 만든다.
        if args.report_only:
            step("⑥", "마지막에 정리한다",
                 f"'{args.run_tag}' 의 완료 서랍을 읽는다 — ④⑤ 는 건너뛴다")
            note("보고 담당을 한 번 부른다 (이 실행의 유일한 LLM 호출)")
            text = await call_agent(
                agents["report"],
                f"Write the report for run '{args.run_tag}'. Call read_results with that run_tag.",
                tools=by_stage["report"], registry=registry, stage="report",
            )
            (run_dir / "report.md").write_text(text, encoding="utf-8")
            done("⑥", f"보고서 {len(text.splitlines())}줄 → report.md")
            print()
            print(text)
            return 0

        # -- waves ------------------------------------------------------
        # ④ 와 ⑤ 를 **파도**로 감싼다. 한 파도 = 질문 만들기 → 씨뿌리기 → 다 처리하기.
        #
        # The wave boundary is what makes feedback possible at all. Seeding every trial
        # up front means the questions are all written before a single result exists,
        # so nothing any trial finds can affect what gets asked. A wave ends with
        # results on the table, and the next wave's curator reads them.
        #
        # 씨뿌렸는데 판에 아무것도 안 남긴 시행 번호. 파도를 넘어 쌓이고, 마지막에
        # 보고 담당에게도 넘어간다.
        missing_trials: list[int] = []
        for wave in range(args.waves):
            base = wave * args.trials          # 시행 번호는 파도를 넘어 이어진다
            if args.waves > 1:
                print(f"\n{'─' * 68}\n 파도 {wave + 1}/{args.waves}\n{'─' * 68}")

            # -- ③′ 무엇을 물을지 정한다 --------------------------------
            questions: list[dict] = []
            if not args.no_curator:
                step("③′", "무엇을 물을지 정한다",
                     f"질문 담당이 코퍼스"
                     + ("" if wave == 0 else "와 앞 파도의 결과")
                     + f"를 보고 질문 {args.trials}개를 만든다")
                questions = await questions_for_wave(
                    registry, agents, by_stage,
                    run_tag=args.run_tag, wave=wave, want=args.trials,
                )
                for q in questions:
                    note(f"질문 #{q['question_id']} {q['text']}"
                         f"  [{'·'.join(q.get('okf_tags') or []) or '태그없음'}]")
                done("③′", f"질문 {len(questions)}개")

            # 질문 담당을 껐거나 실패했으면 코드에 박힌 관점 목록으로 되돌아간다.
            # 코퍼스와 어긋나는 목록이지만, 실행이 멈추는 것보다는 낫다.
            if not questions:
                questions = [{"question_id": 0, "text": perspective_for(base + k)}
                             for k in range(args.trials)]

            # -- seed -------------------------------------------------------
            # -- ④ 첫 지시서를 게시판에 붙인다 -------------------------------
            #
            # 시행 수만큼 가설 담당을 부른다. 매번 **다른 관점**을 주고, 답의 폭도 조금씩
            # 다르게 한다. 같은 답이 세 번 나오면 비교할 것이 없기 때문이다.
            #
            # 관점을 흔들어야 겹침이 "다른 각도에서 출발했는데 같은 곳에 모였다" 가 된다.
            step("④", "첫 지시서를 게시판에 붙인다",
                 f"가설 담당을 {len(questions)}번 부른다 — 매번 다른 질문으로")
            # A trial that never calls `create_task` leaves nothing behind: no board row,
            # no result, no error. On 2026-08-30 one of four trials spent 31 steps and
            # $1.88 that way and the run ended looking successful — the only thing that
            # noticed was the report agent, in prose, by luck. The count was already
            # being printed below; it was never compared, so nothing could notice.
            #
            # ↑ **create_task 를 안 부른 시행은 흔적을 하나도 안 남긴다.** 판에도 결과표에도
            #   오류에도 없다. 8/30 실행에서 4시행 중 하나가 그렇게 31단계·$1.88 을 쓰고
            #   사라졌는데 실행은 성공처럼 끝났다. 알아챈 것은 보고 담당이 우연히 산문으로
            #   적었기 때문이다. 종이 수는 이미 찍고 있었다 — 비교를 안 했을 뿐이다.
            seeded = (await board_state(registry, args.run_tag))["count"]
            for k, q in enumerate(questions):
                i = base + k                       # 파도를 넘어 이어지는 시행 번호
                text = q["text"]
                # question_id travels with the task so a finished result can be traced
                # back to what was asked. 0 means the fallback list was used.
                await call_agent(
                    agents["hypothesis"],
                    f"The outcome column is '{args.y_column}'. Choose the columns that will predict it, "
                    f"{text}. Then put the task on the board with "
                    f"run_tag='{args.run_tag}', trial={i}, perspective='{text}', "
                    f"question_id={q['question_id']}.",
                    tools=by_stage["hypothesis"], registry=registry, temperature=temperature_for(i),
                    stage=f"hypothesis{i}",
                )
                # Has to happen here, not at the end of the run. `submit_result` copies a
                # row from the board to the results table the moment it turns done, so a
                # trace attached after stage ⑤ would land on a board row whose result had
                # already been written without it — recorded in the place that gets cleared
                # and missing from the place that is kept.
                #
                # ↑ **여기서 해야 한다.** 판의 줄이 done 이 되는 순간 결과표로 복사되므로,
                #   ⑤단계 뒤에 붙이면 이미 복사가 끝난 뒤다. 치우는 표에는 남고 남는
                #   표에는 없는, 정확히 고치려던 그 상태가 된다.
                attached, refused = await harvest_match_trace(registry, _CALLS[-1])

                # 게시판에 종이가 정말 늘었는지 한 장씩 확인하며 간다.
                # 안 늘면 그 사람이 실패한 것이다.
                state = await board_state(registry, args.run_tag)
                extra = ""
                if attached:
                    extra += f" · 매처 기록 {attached}장에 붙였다"
                if refused:
                    # Reported, not hidden. All-refused and never-called are different
                    # failures with different fixes, and they look the same if this is
                    # silent. ↑ 전부 거절된 것과 아예 안 부른 것은 고칠 곳이 다르다.
                    extra += f" · 매처 호출 {refused}건이 거절돼 근거에서 뺐다"
                note(f"시행 {i} ({text}) → 게시판에 종이 {state['count']}장" + extra)

                if state["count"] <= seeded:
                    note(f"⚠ 시행 {i} 가 판에 아무것도 남기지 못했다 "
                         f"— create_task 가 불리지 않았다")
                    missing_trials.append(i)
                seeded = state["count"]

            # -- work it down ----------------------------------------------
            # -- ⑤ 게시판이 빌 때까지 돌린다 ---------------------------------
            #
            # Retries are unlimited by decision, so this loop has no cap. It prints what it
            # sees every round precisely because the person watching is the only thing that
            # ends it if a task can never succeed.
            #
            # ↑ 재시도에 상한이 없으므로 이 루프에도 상한이 없다. 매 바퀴 현황을 찍는 이유가
            #   그것이다 — 끝내 성공하지 못할 과제를 멈출 수 있는 것은 **보고 있는 사람뿐**이다.
            lost_here = [i for i in missing_trials if base <= i < base + len(questions)]
            done("④", f"게시판에 종이 {state['count']}장"
                 + (f" · 시행 {len(questions)}개 중 {len(lost_here)}개가 빈손으로 끝났다 "
                    f"({', '.join(str(i) for i in lost_here)})" if lost_here else ""))
            step("⑤", "게시판이 빌 때까지 돌린다",
                 "Ctrl-C 로 멈춰도 게시판은 그대로 남는다")
            rounds = 0
            while True:
                state = await board_state(registry, args.run_tag)      # 게시판을 본다
                counts, retried = summarise(state["tasks"])            # 현황 · 되돌아온 것

                # 게시판에 남은 것이 없으면 끝이다.
                if not counts:
                    done("⑤", f"게시판이 비었다 — {rounds}바퀴 만에")
                    break

                rounds += 1
                desc = " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))

                # Named, not aggregated: "somewhere retried 5 times" does not tell a person
                # which task is stuck, and stuck-ness is what they are deciding about.
                #
                # ↑ "어딘가에서 5회 재시도" 로는 어느 과제가 막혔는지 알 수 없다.
                #   사람이 판단하려는 것이 바로 "무엇이 막혔나" 이므로 번호를 찍는다.
                # 이름을 `note` 로 두면 위에서 정의한 note() 함수를 가린다.
                # 그러면 이 루프 안에서 note(...) 를 부르는 순간 TypeError 로 죽는다.
                stuck = ""
                if retried:
                    worst = sorted(retried, key=lambda p: -p[1])[:3]   # 심한 것 셋만
                    stuck = "  ← 되돌아온 일: " + ", ".join(f"#{tid} {n}회" for tid, n in worst)
                print(f"   [{rounds:>3}바퀴] {desc}{stuck}")

                # 이번 바퀴에 누구라도 불렀는가. 아무도 안 불렀으면 아래로 간다.
                worked = False
                for stage in CLAIMING_STAGES:                 # data → ml → interpreter 순
                    waiting = counts.get(f"{STAGE_TASK_TYPE[stage]}/ready", 0)
                    if not waiting:
                        continue                              # 이 사람이 떼어 갈 종이가 없다

                    # No outcome column in this message on purpose. It is on the task, put
                    # there by the hypothesis stage, and a task has to carry everything its
                    # stage needs. Saying it here as well would leave two sources for one
                    # fact — and the one in the prompt is the one that goes unrecorded.
                    #
                    # ↑ 이 메시지에 결과변수를 **일부러 안 적는다.** 그 값은 가설 단계가
                    #   과제에 적어 뒀고, 과제는 자기 단계에 필요한 것을 다 들고 있어야 한다.
                    #   여기서도 말하면 한 사실의 출처가 둘이 되는데, 프롬프트 쪽은 기록에
                    #   안 남는다 — 나중에 어긋나도 확인할 방법이 없다.
                    await call_agent(
                        agents[stage],
                        f"Claim a '{STAGE_TASK_TYPE[stage]}' task and do your part.",
                        tools=by_stage[stage], registry=registry, stage=stage,
                    )
                    worked = True

                if not worked:
                    # Nothing is waiting for any stage, so what is left is in_progress.
                    # Either its agent died without submitting, or it is simply still
                    # running. Only the first kind may be taken back, which is what the
                    # staleness window decides.
                    #
                    # ↑ 어느 단계도 집을 게 없다 = 남은 것은 전부 '진행중'이다. 그 중에는
                    #   ① 에이전트가 제출 없이 죽은 것과 ② 그냥 아직 하고 있는 것이 섞여 있다.
                    #   ①만 되찾아야 하고, 그 둘을 가르는 것이 시간 창(stale_after)이다.
                    n = await reclaim_stalled(registry, args.run_tag, args.stale_after)
                    if n:
                        print(f"       {n}개가 {args.stale_after}초 넘게 멈춰 있어 대기로 되돌렸다")
                    else:
                        # Everything still in progress is young enough to be presumed
                        # alive. Waiting is correct; looping without waiting would spin
                        # the CPU and hammer the board for no reason.
                        #
                        # ↑ 전부 아직 살아 있다고 볼 만큼 최근이다. 기다리는 게 맞다.
                        #   안 쉬고 돌면 CPU 만 태우고 판에 조회만 퍼붓는다.
                        print(f"       진행중인 것을 기다린다 ({POLL_SECONDS}초)")
                        await asyncio.sleep(POLL_SECONDS)

            # -- ⑥′ 이번 파도의 성적을 질문 은행에 적는다 ----------------
            #
            # Has to be here, not after the last wave: the next wave's curator reads the
            # bank, so a score written after the loop is a score no question ever used.
            try:
                folded = await call_board_tool(
                    registry, "record_question_outcomes", {"run_tag": args.run_tag})
                if folded.get("questions_updated"):
                    note(f"질문 {folded['questions_updated']}개에 이번 성적을 적었다")
            except Exception as e:  # noqa: BLE001 - bookkeeping must not fail the run
                note(f"(질문 은행에 성적을 못 적었다: {type(e).__name__})")


        # -- report -----------------------------------------------------
        # -- ⑥ 마지막에 정리한다 ----------------------------------------
        #
        # 보고 담당은 **게시판이 아니라 완료 서랍**을 읽는다. 게시판은 작업대라 치우면
        # 사라지지만, 완료 서랍은 남는 기록이기 때문이다.
        step("⑥", "마지막에 정리한다", "보고 담당이 완료 서랍을 읽는다")
        # How many trials were seeded is told to the reporter, because the results table
        # cannot say it. read_results only returns rows that exist, so a trial that died
        # before create_task is invisible there — and a report that silently describes
        # three results as if three were all that were attempted is a false report.
        #
        # ↑ **몇 개를 뿌렸는지는 결과표가 말해 주지 못한다.** read_results 는 있는 행만
        #   돌려주므로 create_task 전에 죽은 시행은 거기 없다. 3개를 뿌린 전부인 양
        #   적는 보고서는 틀린 보고서다. 그래서 뿌린 수를 여기서 알려 준다.
        seeded_total = args.waves * args.trials
        lost_note = (
            f" Trials {', '.join(str(i) for i in missing_trials)} produced no result at all "
            f"(the hypothesis agent never called create_task); they will be absent from "
            f"read_results. Say so explicitly."
            if missing_trials else ""
        )
        text = await call_agent(
            agents["report"],
            f"Write the report for run '{args.run_tag}'. Call read_results with that run_tag. "
            f"{seeded_total} trials were seeded across {args.waves} wave(s). "
            f"State how many of those {seeded_total} produced a result.{lost_note}",
            tools=by_stage["report"], registry=registry, stage="report",
        )
        (run_dir / "report.md").write_text(text, encoding="utf-8")

        # 게시판의 마지막 모습도 통째로 저장해 둔다. 나중에 되짚을 때 쓴다.
        final = await board_state(registry, args.run_tag)
        (run_dir / "board.json").write_text(
            json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        run_ids = [t.get("task_id") for t in final["tasks"]]
        print(f"\n{'=' * 68}\n{text}\n{'=' * 68}")
        print(f"\nrun directory: {run_dir}")
        print(f"  report.md · board.json ({len(run_ids)} tasks)")
        if log_path:
            print(f"  {log_path.name}")
        return 0
    finally:
        # 추적 파일을 **finally 안에서** 쓴다. 중간에 죽거나 Ctrl-C 로 끊겨도 그때까지
        # 부른 실행의 기록은 남아야 하기 때문이다 — 죽은 실행이야말로 되짚어 볼 대상이다.
        # 도구 서버를 끊기 전에 쓴다: 여기서 읽는 것은 core 의 DB 라 도구 서버와 무관하지만,
        # 순서를 바꾸면 나중에 누가 도구를 쓰도록 고칠 때 조용히 깨진다.
        try:
            n = await write_traces(run_dir)
            if n:
                print(f"  trace/ 에 {n}개 · runs.json — 에이전트가 도구에 무엇을 묻고 "
                      f"무엇을 받았는지가 여기 있다")
        except Exception as e:  # noqa: BLE001 - 기록 실패가 실행을 망치면 안 된다
            print(f"!! 추적 파일을 쓰지 못했다: {type(e).__name__}: {e}", file=sys.stderr)

        # 성공이든 실패든 자식 프로세스 넷을 반드시 정리한다.
        await registry.disconnect_all()


async def reclaim_stalled(registry: MCPServerRegistry, run_tag: str, stale_after: int) -> int:
    """Put tasks nobody is working on back into the queue.

    An agent that finished without submitting leaves its task marked in_progress
    forever. Since retries are unlimited, these go back to waiting rather than being
    closed — that is the decision, and this is where it is enforced.

    **Only rows untouched for *stale_after* seconds.** Without that condition this
    reclaims work that is in progress right now, one second after it was claimed. A
    single driver mostly gets away with it, because it only calls this when it has
    nothing else to do — but "nothing waiting for me" and "nothing being worked on"
    are different statements, and the gap between them is where a stage that simply
    takes a long time gets its task yanked away mid-run. It then submits against a
    task somebody else has since claimed.

    Returns:
        How many were returned to the queue. Zero means everything still in progress
        is young enough to be presumed alive — the caller should wait, not spin.

    ↑ **아무도 안 하고 있는 종이를 게시판으로 되돌린다.**

      누가 떼어 갔는데 결과를 안 붙이고 사라지면, 그 종이는 영영 "하는 중" 으로
      남는다. 그런 것을 도로 붙여 다른 사람이 할 수 있게 한다.

      단, **오래 손대지 않은 것만.** 그 조건이 없으면 방금 떼어 간 일까지 뺏어 오고,
      오래 걸리는 사람이 일하는 도중에 종이를 빼앗긴다.
    """
    # 이 한 곳만 게시판을 직접 만진다. 창구를 안 거치는 이유는, 이것이 일하는
    # 사람의 일이 아니라 **관리자의 일**이기 때문이다 — 누구에게도 줄 버튼이 아니다.
    conn = await asyncpg.connect(dsn())
    try:
        n = await conn.fetchval(
            """
            WITH returned AS (
                UPDATE memstara_blackboard
                SET status = 'ready', claimed_at = NULL, updated_at = now()
                WHERE run_tag = $1 AND status = 'in_progress'
                  AND claimed_at IS NOT NULL
                  -- 집어 간 지 stale_after 초가 넘은 것만. 이 줄이 안전장치다.
                  AND claimed_at < now() - make_interval(secs => $2::double precision)
                RETURNING 1
            ) SELECT count(*) FROM returned
            """,
            run_tag,
            float(stale_after),
        )
    finally:
        await conn.close()
    return int(n)


async def main() -> int:
    """명령줄에서 들어오는 문. 인자를 읽고, 검사하고, 잠금을 잡고 run() 을 부른다."""
    # 이 프로젝트는 `.env` 가 **둘**이고, 서로 다른 것을 담는다.
    #
    #     memstara/.env   MEMSTARA_* 경로들
    #     agentic-core/.env           LLM 자격증명 · AGENTIC_DATABASE_URL
    #
    # 그런데 `settings.py:27` 의 `env_file=".env"` 는 **현재 폴더 하나만** 읽는다.
    # 그래서 core 쪽 것을 따로 읽어 주지 않으면 LLM 자격증명이 안 들어오고,
    # 그 결과가 첫 호출에서 터지는 이 오류다:
    #
    #     ValueError: Azure Anthropic requests require an api_base.
    #
    # 셸에서 `source` 둘을 하면 안 걸리지만, VS Code 의 `envFile` 은 파일 하나만
    # 받으므로 F5 로 띄우면 걸린다. 실행 방법마다 다르게 동작하는 셈이라,
    # **프로그램이 직접 읽어** 어디서 띄우든 같게 만든다.
    #
    # 샌드박스 것을 먼저 읽는다. `load_dotenv` 는 이미 있는 값을 덮지 않으므로
    # (override=False 가 기본) 먼저 읽은 쪽이 이기고, 셸이나 launch.json 이 준
    # 값은 둘 다보다 앞선다 — "이 실행에만 다른 번들" 이라는 의도가 유지된다.
    load_dotenv(HERE / ".env")
    load_dotenv(HERE / ".." / "agentic-core" / ".env")

    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3, help="how many hypotheses to seed per wave")
    ap.add_argument("--waves", type=int, default=1,
                    help="how many question-then-investigate rounds; wave 2 onward reads "
                         "the results of the one before it")
    ap.add_argument("--no-curator", action="store_true",
                    help="skip question generation and use the built-in perspective list")
    ap.add_argument("--y-column", default="outcome")
    ap.add_argument("--provider", default="azure_foundry", choices=["anthropic", "azure_foundry", "openai"])
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--run-tag", default=None, help="names this run on the board")
    ap.add_argument("--report-only", action="store_true", help="write the report from what has finished")
    ap.add_argument(
        "--stale-after", type=int, default=600,
        help="seconds a task may sit in_progress before it is presumed abandoned (default 600)",
    )
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--run-dir", default=None)
    args = ap.parse_args()

    # 준비물이 없으면 **아무것도 하지 않고** 끝낸다. 반쯤 하다 죽는 것보다
    # 시작 전에 멈추는 편이 게시판을 깨끗하게 남긴다.
    problems = await check_environment(provider=args.provider, y_column=args.y_column)
    if problems:
        print("Environment is not ready:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    started = datetime.now()
    # 실행 이름을 안 주면 시각으로 만든다. 이 이름으로 게시판의 종이들이 묶인다.
    args.run_tag = args.run_tag or started.strftime("board_%Y%m%dT%H%M%S")
    run_dir = Path(args.run_dir) if args.run_dir else new_run_dir(
        f"board_{args.trials}trials", started.strftime("%Y-%m-%dT%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    # 화면에 찍히는 것을 console.log 에도 그대로 남긴다.
    with tee_console(run_dir / "console.log"):
        try:
            # Refuse to be the second driver on this tag. Held for the whole run and
            # released with the connection, so a killed process leaves nothing behind.
            #
            # ↑ **같은 게시판에 두 번째 관리자가 붙는 것을 막는다.** 예전에 둘이 동시에
            #   돌아 서로의 종이를 뺏어 가며 판이 뒤섞인 적이 있다.
            #
            #   데이터베이스가 잡아 주는 잠금이라, 프로그램이 강제로 죽어도 연결이
            #   끊기는 순간 **자동으로 풀린다** — 찌꺼기가 안 남는다.
            async with run_lock(args.run_tag):
                return await run(args, run_dir)
        except BoardBusy as e:
            # 이미 누가 이 이름으로 돌리고 있다.
            print(f"\n{e}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            # The board is a database; whatever was written stays written. Say what to
            # do next rather than leaving a bare traceback.
            #
            # ↑ Ctrl-C 로 멈춰도 **게시판은 그대로 남는다.** 그러니 알 수 없는 오류
            #   덩어리 대신 "다음에 무엇을 하면 되는지" 를 알려 준다.
            print("\n\n중단됐다. 판은 그대로 남아 있다.")
            print(f"  상태 보기:  python blackboard.py --show")
            print(f"  보고만:     python 03_board_pipeline.py --report-only --run-tag {args.run_tag}")
            return 130


if __name__ == "__main__":
    # asyncio.run 이 main() 을 끝까지 돌리고, 그 반환값(0/1/2/130)이 종료 코드가 된다.
    raise SystemExit(asyncio.run(main()))
