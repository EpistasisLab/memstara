#!/usr/bin/env python3
"""Memstara MVP — hypothesis -> data -> ML -> interpreter, repeated N times.

An executable example of the four-stage pipeline fixed in the 2026-08-06 meeting. It
runs over synthetic data and a sample OKF bundle, and reads feature importance out of
the overlap in column selections across trials.

↑ 2026-08-06 회의에서 정한 4단계 파이프라인을 그대로 돌려 보는 예제다. 합성 데이터와
  표본 OKF 번들 위에서 돌며, **여러 시행이 고른 컬럼이 서로 얼마나 겹치는지**를 세어
  변수 중요도를 읽어 낸다. 한 번 잘 맞힌 시행보다, 관점을 바꿔 가며 여러 번 돌렸을
  때 반복해서 뽑히는 컬럼이 더 믿을 만하다는 발상이다.

Setup::

    cp .env.example .env && docker compose up -d
    uv sync --frozen --group dev          # or: uv pip install -e .
    uv pip install pandas scikit-learn

    SB=../memstara                 # this folder, outside the repo
    python $SB/make_sample_data.py

    set -a && . ./.env && set +a
    export AGENTIC_OKF_BUNDLE_DIR="$PWD/$SB/outputs/okf_synthetic_sample"
    export MEMSTARA_DATASET_PATH="$PWD/$SB/outputs/dataset.csv"
    export MEMSTARA_OUTPUT_DIR="$PWD/$SB/outputs"

Run::

    python $SB/02_mvp_pipeline.py --trials 3      # smoke
    python $SB/02_mvp_pipeline.py --trials 20     # full

Point AGENTIC_OKF_BUNDLE_DIR at a different bundle folder to swap knowledge
sources — the server reads exactly one bundle. See outputs/README.md.

↑ 지식 원천을 바꾸고 싶으면 AGENTIC_OKF_BUNDLE_DIR 을 다른 번들 폴더로 돌리면 된다.
  서버는 **한 번에 번들 하나만** 읽는다. 여러 번들을 동시에 얹을 수는 없다.

Every invocation writes one directory under ``outputs/runs/``::

    2026-08-13T142530_mvp_3trials/
      REPORT.md        did it go normally, and if not, what was wrong — read this first
      run.jsonl        structured, DEBUG, every record tagged with trial and stage
      console.log      what the terminal showed, colour codes stripped
      manifest.json    arguments, paths, timing, result
      trace/           one file per trial: every step, tool arguments, tool results
      todo_rows.json   this run's rows and summary (outputs/ keeps only the latest)
      summary.json

Nothing appends to a previous run, so a folder is always exactly one invocation.

↑ 한 번 실행할 때마다 ``outputs/runs/`` 아래에 폴더 하나가 새로 생긴다. 이전 실행에
  덧붙이는 것은 아무것도 없으므로, 폴더 하나는 정확히 실행 한 번이다. 어제 것과
  섞이지 않으니 나중에 열어 봐도 무엇을 보고 있는지 헷갈리지 않는다.

  폴더 안의 파일들:
    REPORT.md      정상으로 끝났는지, 아니면 무엇이 잘못됐는지 — 여기부터 읽는다
    run.jsonl      기계가 읽는 상세 기록. 줄마다 몇 번째 시행·어느 단계인지 붙어 있다
    console.log    터미널에 나온 그대로(색 코드는 지움)
    manifest.json  어떤 인자로 돌렸는지, 경로·시각·결과
    trace/         시행마다 파일 하나. 모든 단계와 도구 호출 인자·결과가 다 있다
    todo_rows.json 이번 실행의 시행별 결과 행
    summary.json   집계 결과

==============================================================================
 이 파일을 읽는 법
==============================================================================

 이 파일은 **감독자(supervisor) 방식** 파이프라인이다. 파이썬 함수가 네 단계
 (가설 → 데이터 → 머신러닝 → 해석)를 정해진 순서로 직접 부르고, 앞 단계의 결과를
 변수에 담아 뒤 단계에 넘긴다. 순서를 정하는 것은 파이썬 코드이지 LLM이 아니다.
 이것을 시행 횟수만큼 반복한 뒤, 시행들이 고른 컬럼을 모아 집계한다.

 주요 함수 (위에서 아래로 실행 순서)
   main()             — .env 두 개를 읽고, 인자를 받고, 실행 폴더를 만들고,
                        콘솔 기록을 켠 뒤 run_pipeline 을 부른다
   run_pipeline()     — 실제 작업을 _run_pipeline 에 맡기되, 성공하든 죽든
                        manifest.json 만은 반드시 남긴다
   _run_pipeline()    — 환경 점검 → 에이전트 준비 → 도구 연결 → 시행 N번 →
                        집계 → 파일 저장 → 보고서 생성 → 출력
   check_environment()— 필요한 환경변수가 다 있는지 **시작 전에** 한꺼번에 확인
   setup_tools()      — MCP 서버 네 개를 등록하고 연결
   dataset_columns()  — CSV 첫 줄만 읽어 컬럼 이름 목록을 얻는다
   write_manifest()   — 이번 실행이 무엇이었는지 파일로 남긴다
   print_summary()    — 집계 결과를 터미널에 보기 좋게 찍는다

 놓치기 쉬운 핵심
   1. **이 파일은 03(판 방식)과 나란히 놓인 비교 대상이다.** 03은 같은 일을 다른
      구조 — 공용 게시판(blackboard)에 에이전트들이 각자 써 넣는 방식 — 로 한다.
      둘이 다른 답을 내면 그 사실 자체가 정보다. 그러려면 비교 기준이 움직이면
      안 되므로, **이 파일은 건드리지 않는다.** 새 아이디어는 03에 넣는다.
   2. **LLM 감독자가 아니다.** "supervisor"라는 말 때문에 오해하기 쉬운데,
      여기서 감독하는 것은 `_run_pipeline` 안의 평범한 파이썬 코드다. 어떤 LLM도
      "다음에 무엇을 할지"를 정하지 않는다.
   3. **`.env` 파일이 둘이다.** 그래서 main() 맨 앞에서 둘 다 읽는다.
      이유는 main() 안의 주석에 자세히 적혀 있다.
   4. **`dump_all` 로 시행별 추적 파일을 남긴다.** 데이터베이스에는 모든 도구
      호출이 인자·결과까지 남지만 꺼내 오기 전에는 볼 수 없어서, 실행이 끝날 때
      파일로 뽑아 둔다. 03은 다른 방식으로 기록한다.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

# 아래는 이 폴더 안의 형제 모듈들이다. 실제 일은 대부분 여기서 일어나고,
# 이 파일은 그것들을 순서대로 부르는 역할을 한다.
#   logging_setup  — 실행 폴더 만들기, 로그 설정, 콘솔 기록
#   pipeline_core  — 시행 한 번 돌리기, 집계하기, 에이전트 준비하기
#   run_report     — 실행 폴더를 읽어 REPORT.md 를 쓰고 정상/이상을 판정
#   settings       — 환경변수를 읽어 들이는 설정 객체
#   trace_run      — 데이터베이스의 도구 호출 기록을 파일로 뽑아내기
from logging_setup import new_run_dir, setup_logging, tee_console
from pipeline_core import (
    TrialConfig,
    aggregate,
    interpret_overall,
    provision_all,
    run_one_trial,
    save_rows,
)
from run_report import build_report
from settings import Settings

# .env 가 둘이라 프로그램이 직접 읽는다 — main() 의 주석 참고.
from dotenv import load_dotenv
from trace_run import dump_all

from agentic_core import configure
from agentic_core.mcp.registry import MCPServerRegistry
from agentic_core.services.mcp_service import (
    get_server_by_name,
    hydrate_registry,
    register_server,
    update_server,
)

HERE = Path(__file__).parent
OUT_DIR = HERE / "outputs"

# Recorded in the manifest by name. Never dump os.environ: it holds the provider
# credentials, and a run directory is something you hand to someone else to read.
#
# ↑ manifest.json 에 기록할 환경변수를 **이름으로 하나하나 지정**한다.
#   os.environ 전체를 그대로 쏟아 붓는 일은 절대 하지 않는다. 거기에는 LLM
#   제공자의 API 키가 들어 있고, 실행 폴더는 남에게 통째로 건네 읽히는 물건이기
#   때문이다. 여기 적힌 셋은 경로일 뿐이라 새어 나가도 문제가 없다.
RECORDED_ENV_VARS = ("AGENTIC_OKF_BUNDLE_DIR", "MEMSTARA_DATASET_PATH", "MEMSTARA_OUTPUT_DIR")


def dataset_columns() -> list[str] | None:
    """The dataset's column names, read from its header row alone.

    Only `aggregate` needs this, and only to decide whether the planted-signal answer
    key belongs to this dataset. Reading one line beats loading the file.

    ↑ 데이터셋의 컬럼 이름 목록을 **첫 줄(헤더)만 읽어서** 얻는다.

    이것을 쓰는 곳은 `aggregate` 한 군데뿐이고, 용도도 하나다: 이 데이터셋이
    make_sample_data.py 가 만든 그 합성 데이터인지 — 즉 심어 둔 정답(채점표)을
    적용해도 되는 데이터인지 — 판단하는 것. 그 판단 하나 때문에 수만 행짜리
    파일을 통째로 메모리에 올릴 이유는 없어서 한 줄만 읽는다.

    Returns:
        컬럼 이름 목록. 경로가 없거나, 파일이 없거나, 읽다 실패하면 None.
        None 은 "모르겠다"는 뜻이고, aggregate 는 그때 채점을 건너뛴다.
    """
    path = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if not path or not Path(path).is_file():
        return None
    try:
        with Path(path).open(encoding="utf-8", newline="") as fh:
            # next(...) 는 CSV 리더에서 첫 줄만 꺼낸다. 나머지는 읽지 않는다.
            return next(csv.reader(fh))
    # 빈 파일(StopIteration), 읽기 실패(OSError), 인코딩 깨짐(UnicodeDecodeError).
    # 셋 다 "컬럼을 알 수 없다"로 같게 처리한다 — 여기서 예외를 위로 던져
    # 실행 전체를 죽일 만한 사안이 아니기 때문이다.
    except (StopIteration, OSError, UnicodeDecodeError):
        return None


def write_manifest(path: Path, *, args: argparse.Namespace, started: str, summary: dict | None) -> None:
    """Record what this run was, so the folder explains itself a month later.

    Every key is read with .get. This function is also the last thing that runs when a
    run dies, so it has to survive a half-built summary — and it did not: reading
    ``summary["planted_recall"]`` directly raised KeyError on the first dataset without
    a planted signal, taking down the manifest and the report along with it.

    ↑ 이번 실행이 무엇이었는지 파일로 남긴다. 한 달 뒤에 이 폴더를 열어도 폴더가
    스스로를 설명할 수 있게 하려는 것이다.

    **결함 이력**: 모든 키를 `.get` 으로 읽는 데는 이유가 있다. 이 함수는 실행이
    도중에 죽었을 때 **마지막으로 실행되는** 코드이기도 해서, 절반만 만들어진
    summary 를 받아도 살아남아야 한다. 그런데 예전에는 그러지 못했다.
    `summary["planted_recall"]` 을 대괄호로 곧장 읽었는데, 심어 둔 정답이 없는
    데이터셋을 처음 돌린 날 그 키가 없어서 KeyError 가 났고, manifest 는 물론
    그것을 읽는 보고서까지 함께 무너졌다. 기록을 남기는 코드가 기록을 남길 수
    없게 만드는 셈이라, 이후로는 없는 키를 만나도 그냥 None 이 되게 바꿨다.

    Args:
        path: 쓸 파일 경로(manifest.json).
        args: 명령줄 인자 전체.
        started: 시작 시각 문자열.
        summary: 집계 결과. 실행이 거기까지 못 갔으면 None 이다.
    """
    result = None
    if summary is not None:
        result = {
            "n_trials": summary.get("n_trials"),
            "n_succeeded": summary.get("n_succeeded"),
            "n_failed": summary.get("n_failed"),
            "mean_auc": summary.get("mean_auc"),
            "errors": summary.get("errors", []),
        }
        # Present only on the dataset that carries the answer key — see aggregate().
        #
        # ↑ `planted_recall`(심어 둔 정답을 몇 개나 되찾았는가)은 채점표가 있는
        #   데이터셋에서만 나온다. 다른 데이터셋에는 정답이 없으므로 이 키 자체가
        #   없고, 그때는 아무것도 기록하지 않는다.
        if "planted_recall" in summary:
            result["planted_recall"] = summary["planted_recall"]

    manifest = {
        "started_at": started,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "args": vars(args),
        "environment": {name: os.environ.get(name, "") for name in RECORDED_ENV_VARS},
        "result": result,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# provider 마다 있어야 하는 자격증명. `--provider` 로 고른 것만 검사한다.
#
# 이것이 없던 동안은 자격증명이 비어도 **첫 LLM 호출까지 가서야** 터졌다. 시작 전에
# 멈추는 편이 낫다 — 아무것도 쓰지 않고, 무엇을 채워야 하는지도 그 자리에서 안다.
_PROVIDER_KEYS = {
    "azure_foundry": ("ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


def check_environment(provider: str = "") -> list[str]:
    """Report everything missing at once, before anything starts.

    Without this the MCP servers fail to connect quietly, and the only symptom is a
    line reading "tools available: []".

    ↑ 빠진 것을 **아무것도 시작하기 전에, 한꺼번에** 보고한다. 하나 고치고 다시
    돌렸더니 또 다른 하나가 없다는 식으로 반복하지 않게 하려는 것이다.

    이 점검이 없으면 MCP 서버들이 조용히 연결에 실패하고, 겉으로 드러나는 유일한
    증상은 "tools available: []" 라는 한 줄뿐이다. 그 줄만 보고 원인이 환경변수
    누락이라는 것을 알아내기는 어렵다.

    Returns:
        문제 설명 문자열의 목록. 비어 있으면 준비가 끝난 것이다.

    Args:
        provider: `--provider` 로 고른 값. 그것에 맞는 자격증명만 검사한다.
    """
    problems: list[str] = []

    # LLM 자격증명. 이 값들은 `agentic-core/.env` 에 있고 main() 이 읽어 준다.
    for name in _PROVIDER_KEYS.get(provider, ()):
        if not os.environ.get(name, "").strip():
            problems.append(
                f"{name} is not set — needed for --provider {provider}. "
                "Check agentic-core/.env."
            )

    # 아래 셋은 이 샌드박스의 경로 설정이다. "없다"와 "있는데 가리키는 곳이
    # 없다"를 따로 구분해 알려 준다 — 오타로 경로가 틀린 경우가 실제로 잦다.
    okf = os.environ.get("AGENTIC_OKF_BUNDLE_DIR", "").strip()
    if not okf:
        problems.append(
            "AGENTIC_OKF_BUNDLE_DIR is not set — export AGENTIC_OKF_BUNDLE_DIR="
            f'"{OUT_DIR / "okf_synthetic_sample"}"'
        )
    elif not Path(okf).is_dir():
        problems.append(f"AGENTIC_OKF_BUNDLE_DIR does not exist: {okf}")

    ds = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if not ds:
        problems.append(f'MEMSTARA_DATASET_PATH is not set — export MEMSTARA_DATASET_PATH="{OUT_DIR / "dataset.csv"}"')
    elif not Path(ds).is_file():
        problems.append(f"MEMSTARA_DATASET_PATH file not found: {ds} (run make_sample_data.py first)")

    if not os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip():
        problems.append(f'MEMSTARA_OUTPUT_DIR is not set — export MEMSTARA_OUTPUT_DIR="{OUT_DIR}"')

    return problems


async def setup_tools() -> MCPServerRegistry:
    """Register the three MCP servers (once) and hydrate the registry.

    register_server is a one-time setup step of the same character as provision.py;
    hydrate_registry runs every process, exactly as a worker or a restarted API would.

    ↑ MCP 서버들을 (한 번) 등록하고, 레지스트리를 채워 연결한다.

    MCP 서버란 에이전트가 쓸 **도구 꾸러미**를 제공하는 별도 프로세스다. 여기서는
    지식 조회(okf), 데이터 접근(memstara-data), 머신러닝(memstara-ml),
    게시판(memstara-blackboard) 네 가지가 있다.

    두 동작의 성격이 다르다:
      - `register_server` 는 "이런 서버가 있다"를 데이터베이스에 한 번 적어 두는
        준비 작업이다. provision.py 가 에이전트를 등록해 두는 것과 같은 성격이다.
      - `hydrate_registry` 는 그 기록을 읽어 실제로 프로세스를 띄우고 연결하는
        일이며, **프로세스마다 매번** 일어난다. 워커나 재시작된 API 서버도 똑같이
        이 과정을 거친다.

    Returns:
        연결이 끝난 MCP 서버 레지스트리.
    """
    registry = MCPServerRegistry()

    # The executable must be on core's allowlist (python/node/npx/...) and the command
    # must contain no shell metacharacters. sys.executable is python, whose
    # basename is python, so it passes.
    #
    # ↑ 실행 파일은 core가 허용한 목록(python / node / npx …)에 있어야 하고, 명령
    #   문자열에 셸 특수문자가 섞여 있으면 안 된다. 임의의 명령이 실행되는 것을
    #   막는 안전장치다. `sys.executable` 은 지금 이 스크립트를 돌리고 있는 파이썬
    #   실행 파일의 경로이고, 그 파일 이름이 python 이므로 검사를 통과한다.
    #
    # okf runs core's server through tools_okf.py rather than `-m ...okf` directly. That
    # wrapper turns off one YAML behaviour so list_concepts stops failing on bundles core
    # did not write; core's tools themselves are unchanged. See tools_okf.py.
    #
    # ↑ okf 만은 core의 서버를 `-m ...okf` 로 곧장 부르지 않고 tools_okf.py 라는
    #   껍데기를 거쳐 부른다. 그 껍데기가 YAML 처리 동작 하나를 꺼 주는데, 그래야
    #   core가 직접 쓰지 않은 번들(예: 지금 이 합성 번들)에서도 list_concepts 가
    #   실패하지 않는다. core의 도구 자체는 손대지 않았다 — 감싸기만 했다.
    #
    # memstara-blackboard is connected but not yet handed to any agent. The board exists
    # and its window works (see test_blackboard.py), but no agent is told to use it —
    # the prompts still receive their input from run_one_trial. Connecting it now means
    # the wiring is exercised on every run instead of only when someone remembers to
    # test it; handing out its tools waits until the prompts ask for them.
    #
    # ↑ memstara-blackboard(공용 게시판)는 **연결만 해 두고 아직 어떤 에이전트에게도
    #   주지 않았다.** 게시판 자체는 동작하고 그 창(window) 기능도 시험을 통과했지만
    #   (test_blackboard.py), 프롬프트는 여전히 run_one_trial 이 건네주는 입력을
    #   받는다. 그런데도 지금 연결해 두는 이유는, 그래야 배선이 **매 실행마다** 한
    #   번씩 시험되기 때문이다. 연결을 미뤄 두면 누군가 생각나서 시험할 때만
    #   확인되고, 그사이 조용히 망가져 있어도 모른다. 도구를 실제로 에이전트에게
    #   넘기는 일은 프롬프트가 그것을 요구하게 될 때로 미룬다.
    servers = [
        ("okf", f"{sys.executable} {HERE / 'tools_okf.py'}"),
        ("memstara-data", f"{sys.executable} {HERE / 'tools_data.py'}"),
        ("memstara-ml", f"{sys.executable} {HERE / 'tools_ml.py'}"),
        ("memstara-blackboard", f"{sys.executable} {HERE / 'tools_blackboard.py'}"),
        # PROTOTYPE semantic matcher: OKF 개념명 → EcoXAI 컬럼명 변환
        # 캐시 필요: python scripts/build_matcher_cache.py
        ("semantic-matcher", f"{sys.executable} {HERE / 'tools_matcher.py'}"),
    ]

    for name, command in servers:
        existing = await get_server_by_name(name)
        if existing is None:
            # 처음 보는 이름이면 새로 등록한다.
            await register_server(name=name, transport="stdio", command=command, registry=registry)
        elif existing.command != command:
            # Registration is idempotent by name, so an edited command would otherwise
            # never reach the running server — the same trap _ensure_agent avoids for
            # agents. A server's identity is its name, not the command behind it.
            #
            # ↑ 등록은 **이름 기준**으로 멱등(같은 이름이면 두 번 등록해도 하나)이다.
            #   그래서 이름은 그대로 두고 명령만 고쳤을 경우, 새로 등록하는 코드만
            #   있으면 "이미 있음"으로 넘어가 버려서 **고친 명령이 영영 반영되지
            #   않는다.** 에이전트 쪽에서 _ensure_agent 가 피해 가는 것과 같은
            #   함정이다. 서버의 정체성은 이름이지 그 뒤의 명령이 아니므로, 이름이
            #   같고 명령이 다르면 갱신해 준다.
            await update_server(existing.id, command=command, registry=registry)

    # 등록된 서버들을 실제로 띄우고 연결한다. 실패한 것이 있으면 목록으로 돌아온다.
    failed = await hydrate_registry(registry=registry)
    if failed:
        # 여기서 멈추지는 않는다. 도구가 하나도 없으면 _run_pipeline 이 그때
        # 판단해 중단한다. 일부만 실패한 경우까지 여기서 끊을 이유는 없다.
        print(f"!! MCP reconnect failed: {failed}", file=sys.stderr)
    return registry


def print_summary(summary: dict) -> None:
    """집계 결과를 터미널에 사람이 읽을 형태로 찍는다.

    같은 내용이 summary.json 과 REPORT.md 에도 남으므로, 여기서 출력에 실패해도
    기록이 사라지지는 않는다.
    """
    print("\n" + "=" * 68)
    print("AGGREGATE")
    print("=" * 68)
    print(f"trials: {summary['n_succeeded']}/{summary['n_trials']} succeeded", end="")
    if summary["n_failed"]:
        print(f"  ({summary['n_failed']} failed)")
    else:
        print()
    if summary["mean_auc"] is not None:
        print(f"AUC: mean {summary['mean_auc']}  best {summary['best_auc']} (trial #{summary['best_trial']})")

    print("\nColumn selection frequency — the meeting's 'overlap'")
    # ↑ **컬럼이 몇 번 선택됐는가.** 회의에서 말한 '겹침(overlap)'이 이것이다.
    #   관점이 다른 시행들이 반복해서 같은 컬럼을 골랐다면, 그 컬럼은 어느 한
    #   관점의 취향이 아니라 데이터가 실제로 밀고 있는 것일 가능성이 높다.
    #   `#` 막대는 횟수를 눈으로 보이게 한 것뿐이다. 상위 12개만 찍는다.
    for col, n in summary["selection_frequency"][:12]:
        bar = "#" * n
        print(f"  {col:16} {n:2}  {bar}")

    print("\nCumulative feature importance — actual contribution")
    # ↑ **누적 변수 중요도.** 위가 "몇 번 뽑혔나"라면 이것은 "뽑혔을 때 모델에
    #   실제로 얼마나 기여했나"다. 자주 뽑혔지만 기여가 없는 컬럼과, 드물게
    #   뽑혔지만 뽑히면 크게 기여하는 컬럼을 이 둘을 나란히 놓아야 구분할 수 있다.
    for col, val in summary["weighted_importance"][:8]:
        print(f"  {col:16} {val}")

    if summary["columns_missing_seen"]:
        # ↑ 에이전트가 골랐는데 데이터셋에 없던 컬럼들. 대개는 OKF의 함정 개념
        #   (PAQ620 등)을 물었다는 뜻이다. 이것이 비어 있지 않다고 실행이 실패한
        #   것은 아니지만, 개념과 컬럼이 어긋나 있다는 신호이므로 드러내 준다.
        print(f"\nColumns absent from the dataset (concept/column name mismatch): {summary['columns_missing_seen']}")

    # Present only when the dataset actually carries the planted signal. On any other
    # dataset there is no answer key, and printing "0/4" would report a failure that
    # did not happen — see aggregate().
    #
    # ↑ **채점 결과는 채점표가 있을 때만 찍는다.** 심어 둔 정답이 있는 합성
    #   데이터에서만 이 키가 생긴다. 다른 데이터셋에는 애초에 정답이 없는데
    #   여기서 "0/4"라고 찍으면, 일어나지도 않은 실패를 보고하는 셈이 된다.
    #   없으면 아예 말하지 않는 편이 맞다.
    if "planted_signal" in summary:
        print(f"\nPlanted signal {summary['planted_signal']}")
        print(f"  found in top 6: {summary['planted_found_in_top6']}  ({summary['planted_recall']})")

    if summary["errors"]:
        print("\nFailed trials:")
        for e in summary["errors"]:
            print(f"  #{e['trial']}: {e['error']}")


async def main() -> int:
    """설정을 읽고, 인자를 받고, 실행 폴더를 준비한 뒤 파이프라인을 시작한다.

    Returns:
        종료 코드. 0이면 성공한 시행이 하나라도 있었다는 뜻이다.
    """
    # 이 프로젝트는 `.env` 가 **둘**이고 서로 다른 것을 담는다.
    #
    #     memstara/.env   MEMSTARA_* 경로들
    #     agentic-core/.env           LLM 자격증명 · AGENTIC_DATABASE_URL
    #
    # `settings.py:27` 의 `env_file=".env"` 는 현재 폴더 하나만 읽으므로, core 쪽을
    # 따로 읽어 주지 않으면 첫 LLM 호출에서
    # "Azure Anthropic requests require an api_base" 로 죽는다. 셸에서 `source` 를
    # 둘 다 하면 안 걸리지만 실행 방법마다 달라지므로, 프로그램이 직접 읽는다.
    #
    # `load_dotenv` 는 이미 있는 값을 덮지 않는다(override=False 가 기본). 그래서
    # 셸이나 launch.json 이 준 값이 둘 다보다 앞선다 — 그 실행에만 다른 번들을
    # 쓰겠다는 의도가 유지된다.
    load_dotenv(HERE / ".env")
    load_dotenv(HERE / ".." / "agentic-core" / ".env")

    ap = argparse.ArgumentParser()
    # --trials: 가설을 몇 번 세워 볼 것인가. 3은 빠른 점검용, 20이 본 실행이다.
    ap.add_argument("--trials", type=int, default=20, help="number of hypothesis trials")
    # At 5 the Foundry endpoint slows enough that reason_act's pre_act hook times out
    # (observed: 5 failures out of 8). 3 is stable against this resource.
    #
    # ↑ 동시에 몇 개를 돌릴지. 5로 올렸더니 Foundry 엔드포인트가 느려져서
    #   reason_act 의 pre_act 훅이 시간 초과로 죽었다(8번 중 5번 실패를 관측).
    #   3이면 이 자원에서 안정적이다. 이 숫자는 이론이 아니라 관측에서 나왔다.
    ap.add_argument("--concurrency", type=int, default=3, help="concurrency cap (rate limits)")
    # --y-column: 예측 대상 컬럼 이름. MEMSTARA_OUTCOME_COLUMN env var 우선, 없으면 "outcome".
    ap.add_argument(
        "--y-column",
        default=os.environ.get("MEMSTARA_OUTCOME_COLUMN", "outcome"),
        help="name of the outcome column",
    )
    ap.add_argument("--provider", default="azure_foundry", choices=["anthropic", "azure_foundry", "openai"])
    ap.add_argument("--model", default="claude-sonnet-4-6")
    # --no-overall: 마지막에 집계 전체를 해석하는 단계를 건너뛴다. LLM 호출이
    # 한 번 줄어서 빠르지만, 사람이 읽을 총평은 없어진다.
    ap.add_argument("--no-overall", action="store_true", help="skip the final interpretation of the aggregate")
    # Ablation: withhold the OKF tools. Since the dataset's columns are opaque codes,
    # this leaves the hypothesis agent with no way to learn what any column measures.
    # Run it against a normal run — if the planted signal is still recovered, OKF was
    # not what produced the answer.
    #
    # ↑ **제거 실험(ablation).** OKF 도구를 일부러 빼고 돌린다. 데이터셋의 컬럼
    #   이름이 암호이므로, OKF가 없으면 가설 에이전트는 어떤 컬럼이 무엇을
    #   재는지 알아낼 방법이 아예 없다. 정상 실행과 나란히 놓고 비교하는 것이
    #   요점이다 — OKF를 빼고도 심어 둔 정답이 그대로 나온다면, 정답을 만들어 낸
    #   것은 OKF가 아니었다는 뜻이다. 즉 "OKF가 도움이 된다"는 주장을 반증할 수
    #   있게 해 주는 장치다.
    ap.add_argument("--ablate-okf", action="store_true", help="run without the OKF tools (ablation)")
    ap.add_argument("--trace", action="store_true", help="print per-trial detail")
    ap.add_argument("--verbose", action="store_true", help="console DEBUG: phases, hooks, every tool call")
    ap.add_argument("--run-dir", default=None, help="where to write this run's records (default: a new one)")
    args = ap.parse_args()

    started = datetime.now()
    # 폴더 이름에 붙일 꼬리표. 제거 실험이면 `_ablate` 가 붙어서, 나중에 폴더
    # 목록만 봐도 정상 실행과 제거 실험을 구분할 수 있다.
    tag = f"mvp_{args.trials}trials{'_ablate' if args.ablate_okf else ''}"
    run_dir = (
        Path(args.run_dir)
        if args.run_dir
        else new_run_dir(tag, started.strftime("%Y-%m-%dT%H%M%S"))
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    # The tee goes on first: dictConfig's StreamHandler binds sys.stderr when it is
    # constructed, so a tee installed after setup_logging would not reach it.
    #
    # ↑ 콘솔 복사(tee)를 **먼저** 켠다. 순서가 중요하다. 로그 설정(dictConfig)이
    #   만드는 StreamHandler 는 만들어지는 그 순간의 sys.stderr 를 붙잡아 둔다.
    #   그래서 setup_logging 뒤에 tee 를 켜면, 이미 붙잡힌 원래 stderr 로 로그가
    #   나가 버려서 console.log 에는 그 부분이 남지 않는다.
    with tee_console(run_dir / "console.log"):
        code = await run_pipeline(args, run_dir=run_dir, started=started)
    return code


async def run_pipeline(args: argparse.Namespace, *, run_dir: Path, started: datetime) -> int:
    """Run the pipeline and write the manifest, finished or not.

    ↑ 파이프라인을 돌리되, 끝까지 갔든 도중에 죽었든 manifest.json 은 **반드시**
    남긴다. 이 함수의 존재 이유가 그 보장 하나다.
    """
    # _run_pipeline fills this in once it has a summary. Passing a box rather than
    # returning the summary keeps the manifest writable from `finally` — which is when
    # it matters most, since a run that died is the one someone comes back to.
    #
    # ↑ `outcome` 은 빈 상자다. _run_pipeline 이 집계를 마치면 그 안에 결과를
    #   넣어 준다. 왜 반환값으로 받지 않고 상자를 건네는가: 반환값은 예외가 나면
    #   돌아오지 않는데, 상자는 예외가 나도 이미 채워진 만큼 남아 있기 때문이다.
    #   그래야 아래 `finally` 에서 있는 만큼이라도 기록할 수 있다. 그리고 기록이
    #   가장 아쉬운 순간은 바로 실행이 죽었을 때다 — 사람이 다시 열어 보는 폴더는
    #   잘 끝난 실행이 아니라 죽은 실행이다.
    outcome: dict[str, dict] = {}
    # partial 은 "인자 일부를 미리 채워 둔 함수"를 만든다. 이후로는 summary 만
    # 넘기면 나머지(경로·인자·시작시각)는 이미 들어가 있다.
    write = partial(write_manifest, run_dir / "manifest.json", args=args, started=started.isoformat(timespec="seconds"))
    try:
        return await _run_pipeline(args, run_dir=run_dir, outcome=outcome, write_manifest_now=write)
    finally:
        # 성공이든 예외든 여기는 반드시 지나간다. summary 가 아직 없으면
        # .get 이 None 을 돌려주고, write_manifest 는 그것을 받아들이게 되어 있다.
        write(summary=outcome.get("summary"))


async def _run_pipeline(
    args: argparse.Namespace,
    *,
    run_dir: Path,
    outcome: dict[str, dict],
    write_manifest_now: Any,
) -> int:
    """파이프라인의 실제 본문. 위에서 아래로 한 번 읽으면 전체 흐름이 보인다.

    이 함수가 곧 '감독자'다. LLM이 다음 순서를 정하는 것이 아니라, 아래 파이썬
    코드가 정해진 차례대로 각 단계를 부르고 결과를 변수에 담아 넘긴다.

    Returns:
        종료 코드. 성공한 시행이 하나도 없으면 1, 있으면 0.
    """
    # [1] 환경 점검. 빠진 것이 있으면 아무 일도 시작하지 않고 여기서 끝낸다.
    problems = check_environment(provider=args.provider)
    if problems:
        print("Environment is not ready:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    # Once per process, and necessarily before any core module reads a setting.
    #
    # ↑ [2] 설정 주입. 프로세스당 딱 한 번이고, core의 어떤 모듈이 설정을 읽기
    #   **전에** 해야 한다. 나중에 하면 이미 옛 설정을 읽어 간 모듈이 생긴다.
    configure(Settings())

    # [3] 로그 설정. --verbose 면 DEBUG(훅·도구 호출까지 전부), 아니면 INFO.
    log_path = setup_logging(
        level="DEBUG" if args.verbose else "INFO",
        log_file=run_dir / "run.jsonl",
    )

    # [4] 에이전트 준비. 가설·데이터·ML·해석 담당이 여기서 만들어진다.
    #     이미 등록돼 있으면 그대로 쓰고, 없으면 만든다.
    agents = await provision_all(provider=args.provider, model=args.model)
    print(f"{len(agents)} agents ready: {', '.join(agents)}")

    # [5] 도구 연결. 여기서부터 registry 를 반드시 닫아야 하므로 try 로 감싼다.
    registry = await setup_tools()
    try:
        tools = registry.get_all_tools()
        print(f"{len(tools)} tools: {[t['name'] for t in tools]}\n")
        if not tools:
            # 도구가 하나도 없으면 시행을 돌려 봐야 의미가 없다. 이 증상이 바로
            # check_environment 의 주석이 말한 "tools available: []" 상황이다.
            print("!! no tools at all — the MCP servers did not connect.", file=sys.stderr)
            print("   Check mcp_allowed_env_vars in settings.py.", file=sys.stderr)
            return 1

        if args.ablate_okf:
            print("ABLATION: OKF tools withheld from the hypothesis agent\n")
        # [6] 시행 한 번에 필요한 것들을 한 묶음으로 만든다. 시행마다 달라지는
        #     것은 번호뿐이고, 나머지 설정은 전 시행이 공유한다.
        #     use_okf=False 면 가설 에이전트에게 OKF 도구를 주지 않는다.
        cfg = TrialConfig(
            agents=agents,
            registry=registry,
            y_column=args.y_column,
            use_okf=not args.ablate_okf,
        )
        # 세마포어는 "동시에 이만큼만"을 강제하는 자물쇠다. 전체 시행을 한꺼번에
        # 띄우되, 실제로 LLM을 부르는 것은 항상 concurrency 개 이하가 된다.
        sem = asyncio.Semaphore(args.concurrency)

        async def guarded(i: int):
            """시행 하나를 자물쇠 안에서 돌리고, 결과 한 줄을 찍는다."""
            async with sem:
                # 네 단계(가설 → 데이터 → ML → 해석)는 run_one_trial 안에서
                # 순서대로 일어난다. 이 파일은 그것을 시행 수만큼 부를 뿐이다.
                row = await run_one_trial(i, cfg)
                status = f"AUC {row.auc}" if row.ok else f"failed: {row.error}"
                # 한 시행이 끝날 때마다 바로 찍는다. 20번짜리 실행에서 끝까지
                # 아무것도 안 보이면 멈춘 것인지 도는 중인지 알 수 없기 때문이다.
                print(f"  #{i:2} [{row.perspective}] {row.columns_used or row.columns} -> {status}")
                if args.trace and row.interpretation:
                    # --trace 일 때만 해석문 앞부분 200자를 덧붙인다.
                    print(f"      {row.interpretation[:200]}")
                return row

        # [7] 시행 N번. gather 는 전부를 동시에 걸어 두고 모두 끝날 때까지 기다린다.
        #     실제 동시 실행 수는 위의 세마포어가 눌러 준다.
        print(f"starting {args.trials} trials (concurrency {args.concurrency})")
        rows = await asyncio.gather(*[guarded(i) for i in range(args.trials)])

        # [8] 집계. 시행별 결과를 한데 모아 선택 빈도와 중요도를 계산한다.
        #     dataset_columns() 를 넘기는 이유는 aggregate 가 "이 데이터셋에
        #     채점표를 적용해도 되는가"를 판단해야 하기 때문이다.
        summary = aggregate(list(rows), y_column=args.y_column, dataset_columns=dataset_columns())

        # [9] 집계 전체에 대한 총평. 성공한 시행이 하나도 없으면 해석할 것이
        #     없으므로 건너뛴다. --no-overall 로도 끌 수 있다.
        if not args.no_overall and summary["n_succeeded"]:
            summary["overall_interpretation"] = await interpret_overall(
                agents["interpreter"], summary, registry=registry
            )

        # 앞서 받은 빈 상자를 여기서 채운다. 이 줄을 지나면 실행이 죽더라도
        # run_pipeline 의 finally 가 집계를 manifest 에 남길 수 있다.
        outcome["summary"] = summary

        summary_json = json.dumps(summary, ensure_ascii=False, indent=2)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        # outputs/ keeps the latest — that is what trace_run.py reads by default. The
        # run directory keeps this run's, which the latest will overwrite tomorrow.
        #
        # ↑ [10] 같은 파일을 두 곳에 쓴다. outputs/ 에는 **가장 최근 것**이 놓이고
        #   (trace_run.py 가 기본으로 그곳을 읽는다), 실행 폴더에는 **이번 실행
        #   것**이 놓인다. outputs/ 쪽은 내일 실행하면 덮어써지지만 실행 폴더
        #   쪽은 남는다. 편의(늘 같은 자리)와 보존(실행마다 따로)을 둘 다 얻는다.
        for target in (OUT_DIR, run_dir):
            save_rows(list(rows), target / "todo_rows.json")
            (target / "summary.json").write_text(summary_json, encoding="utf-8")

        # Turn the step rows into files. The database holds every tool call with its
        # arguments and its result, but only until someone goes and gets them; the
        # live log never carried them at all.
        #
        # ↑ [11] 시행별 추적 파일을 만든다. 데이터베이스에는 모든 도구 호출이
        #   인자와 결과까지 통째로 남아 있지만, **누가 꺼내 오기 전에는 보이지
        #   않는다.** 반면 실행 중에 흐르는 로그에는 그 내용이 애초에 실려 있지
        #   않다. 그래서 실행이 끝날 때 여기서 파일로 뽑아 trace/ 아래에 둔다.
        #   시행 하나가 파일 하나다. (03은 이 일을 다른 방식으로 처리한다.)
        traces = await dump_all(run_dir / "todo_rows.json", run_dir / "trace")

        # The manifest has to exist before the report, which reads it for the run's
        # headline numbers. The write in `finally` is the safety net for a run that
        # died, not the normal path; this is the normal path.
        #
        # ↑ [12] 여기서 manifest 를 쓰는 이유는 **순서** 때문이다. 다음 줄의
        #   보고서 생성이 manifest 를 읽어 대표 수치를 가져가므로, 그 전에
        #   존재해야 한다. run_pipeline 의 finally 에도 같은 쓰기가 있지만
        #   그것은 실행이 죽었을 때를 위한 안전망이고, **정상 경로는 여기**다.
        write_manifest_now(summary=summary)
        # [13] REPORT.md 생성. 정상/이상 판정과 그 근거가 함께 나온다.
        verdict, reasons, report_path = build_report(run_dir)

        print_summary(summary)
        if summary.get("overall_interpretation"):
            print("\nOverall interpretation")
            print("-" * 68)
            print(summary["overall_interpretation"])

        print(f"\nrun directory: {run_dir}")
        print(f"  REPORT.md  ← start here")
        print(f"  console.log · manifest.json · todo_rows.json · summary.json")
        if log_path:
            print(f"  {log_path.name}  (structured, DEBUG, tagged with trial/stage)")
        print(f"  trace/  {len(traces)} files — every step, tool arguments and results")

        # The verdict goes last, and after the run directory, because the whole point is
        # that nobody should have to go looking for it. "3/3 succeeded" was printed on a
        # run that had two warnings in it and nobody noticed.
        #
        # ↑ [14] 판정을 **맨 마지막**에, 실행 폴더 경로보다도 뒤에 찍는다. 터미널에서
        #   눈이 가장 먼저 닿는 곳이 마지막 줄이기 때문이다. 아무도 판정을 찾아
        #   위로 스크롤하지 않아도 되게 하려는 것이다.
        #
        #   **결함 이력**: 예전에 "3/3 succeeded" 만 크게 찍힌 실행이 있었는데,
        #   그 안에 경고가 둘 있었고 아무도 알아채지 못했다. 성공 횟수만으로는
        #   실행이 멀쩡했는지 알 수 없다는 것이 그때 드러났다.
        print(f"\n판정: {verdict}")
        for reason in reasons:
            print(f"  - {reason}")
        print(f"  {report_path}")
        # 성공한 시행이 하나라도 있으면 0, 하나도 없으면 1.
        return 0 if summary["n_succeeded"] else 1
    finally:
        # The registry's lifetime is the process's, not a run's.
        #
        # ↑ 레지스트리의 수명은 **프로세스**의 수명이지 실행 한 번의 수명이
        #   아니다. 그래서 성공하든 실패하든 이 자리에서 반드시 연결을 닫는다.
        #   닫지 않으면 MCP 서버 프로세스들이 뒤에 남는다.
        await registry.disconnect_all()


if __name__ == "__main__":
    # 이 파일을 직접 실행했을 때만 여기가 돈다. asyncio.run 이 비동기 main() 을
    # 끝까지 돌리고, 그 반환값을 프로세스 종료 코드로 그대로 내보낸다.
    raise SystemExit(asyncio.run(main()))
