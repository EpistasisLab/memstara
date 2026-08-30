#!/usr/bin/env python3
"""A debugging harness — call the tools directly, in one process.

Why this is needed
------------------
In a normal run `tools_okf.py`, `tools_data.py`, `tools_ml.py` and
`tools_blackboard.py` are **child processes** started by
`03_board_pipeline.py:119 setup_tools()`. Attaching a debugger to the pipeline
therefore **never** hits a breakpoint in the tool code.

This file pulls the same functions **into this process** and calls them. Breakpoints
then fire the ordinary way, and since no LLM is ever called it costs neither money
nor time. It is exactly the method used for today's verification.

`@mcp.tool()` returns the function unchanged rather than wrapping it, so a registered
tool can be called as a plain Python function — no adapter, no JSON-RPC.

Usage
-----
    uv run --no-sync --project ../agentic-core python debug_harness.py okf
    uv run --no-sync --project ../agentic-core python debug_harness.py data
    uv run --no-sync --project ../agentic-core python debug_harness.py ml
    uv run --no-sync --project ../agentic-core python debug_harness.py board

Without `--no-sync`, uv tries to rebuild litellm from source and fails.

In VS Code, press F5 on the "1. 도구 하네스" configuration.

디버깅용 하네스 — 도구를 한 프로세스에서 직접 부른다.

왜 이게 필요한가
----------------
평소 실행에서 `tools_okf.py` · `tools_data.py` · `tools_ml.py` · `tools_blackboard.py`
는 `03_board_pipeline.py:119 setup_tools()` 가 띄우는 **자식 프로세스**다. 그래서
파이프라인에 디버거를 붙여도 도구 코드의 브레이크포인트는 **걸리지 않는다.**

이 파일은 같은 함수들을 **이 프로세스 안으로 불러들여** 부른다. 그러면
브레이크포인트가 평범하게 걸리고, LLM 을 한 번도 부르지 않으므로 돈도 시간도 들지
않는다. 오늘 검증에 쓴 방식 그대로다.

`@mcp.tool()` 은 함수를 감싸지 않고 그대로 돌려주므로, 등록된 도구를 파이썬 함수로
직접 부를 수 있다 — 어댑터도 JSON-RPC 도 거치지 않는다.

쓰는 법
-------
    uv run --no-sync --project ../agentic-core python debug_harness.py okf
    uv run --no-sync --project ../agentic-core python debug_harness.py data
    uv run --no-sync --project ../agentic-core python debug_harness.py ml
    uv run --no-sync --project ../agentic-core python debug_harness.py board

`--no-sync` 가 없으면 uv 가 litellm 을 소스에서 다시 빌드하려다 실패한다.

VS Code 에서는 "1. 도구 하네스" 구성으로 F5.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# **Both** `.env` files have to be read. The sandbox's holds the dataset and bundle
# paths, core's holds AGENTIC_DATABASE_URL. Read only one and the pipeline cannot
# even start — it stops at "Environment is not ready".
#
# 환경변수는 .env 를 **둘 다** 읽어야 한다. 샌드박스의 .env 에는 데이터셋·번들 경로가,
# core 의 .env 에는 AGENTIC_DATABASE_URL 이 있다. 하나만 읽으면 파이프라인이
# "Environment is not ready" 로 시작도 못 한다.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(HERE / ".." / "agentic-core" / ".env")
load_dotenv(HERE / ".env")

# Which bundle and which data to look at — overridden for this run only, without
# touching `.env`.
#
# 어느 번들·어느 데이터를 볼지. .env 를 고치지 않고 이 실행에만 덮어쓴다.
BUNDLE = HERE / ".." / "shared" / "hiv-suppression" / "okf"
DATASET = HERE / "outputs" / "hiv_cohort.csv"
Y = "HIV_DETECTABLE"

if BUNDLE.is_dir():
    os.environ["AGENTIC_OKF_BUNDLE_DIR"] = str(BUNDLE.resolve())
if DATASET.is_file():
    os.environ["MEMSTARA_DATASET_PATH"] = str(DATASET.resolve())
os.environ.setdefault("MEMSTARA_OUTPUT_DIR", str(HERE / "outputs"))


def load(name: str):
    """Load a module such as `tools_okf` into this process.

    It is registered in sys.modules *before* it is executed: a dataclass looks its own
    module back up in sys.modules while being defined, so executing first would die
    there with an AttributeError.

    `tools_okf` 같은 모듈을 이 프로세스에 올린다.

    sys.modules 에 먼저 넣는다. dataclass 는 정의될 때 자기 모듈을 sys.modules 에서
    되찾아 보는데, 등록 전에 exec 하면 거기서 AttributeError 로 죽는다.
    """
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def show(label: str, payload: str, limit: int = 900) -> None:
    """Pretty-print a tool's JSON string under a heading, clipped to *limit* chars.

    도구가 돌려준 JSON 문자열을 제목과 함께 보기 좋게 찍는다. *limit* 자에서 자른다.
    """
    print(f"\n── {label} " + "─" * max(0, 60 - len(label)))
    text = json.dumps(json.loads(payload), ensure_ascii=False, indent=2)
    print(text[:limit] + (" …" if len(text) > limit else ""))


def do_okf() -> None:
    """Knowledge source. Put breakpoints in tools_okf.py: _load, scoring, section extraction.

    지식원. 브레이크포인트는 tools_okf.py 의 _load / 점수 매김 / 절 뽑기에.
    """
    okf = load("tools_okf")

    show("okf_list_domains", okf.okf_list_domains())
    show("okf_search('adherence')", okf.okf_search("adherence", k=3))
    show("okf_search('art')  ← 예전에는 132편이 걸렸다", okf.okf_search("art", k=3))

    first = json.loads(okf.okf_search("adherence", k=1))["results"][0]["hits"][0]["id"]
    whole = json.loads(okf.okf_read(first))["documents"][0]
    part = json.loads(okf.okf_read(first, section="Bottom line"))["documents"][0]
    print(f"\n── 절 읽기 ────────────────────────────────────────────")
    print(f"   {first}")
    print(f"   전체 {len(whole['text']):,}자  vs  Bottom line {len(part['text']):,}자")
    print(f"   절 목록: {whole['sections']}")


def do_data() -> None:
    """Data. Put a breakpoint on the hash computation at tools_data.py:149.

    데이터. 브레이크포인트는 tools_data.py:149 해시 계산에.
    """
    data = load("tools_data")

    show("describe_dataset", data.describe_dataset(), limit=600)

    a = "CURRENT_AGE,SEX,TOBACCO_LAST_STATUS,n_diagnoses"
    b = "CURRENT_AGE,SEX,RACE_1,MARITAL_STATUS"
    # Same tag, different columns — this used to overwrite a single file twice.
    # 같은 태그, 다른 컬럼 — 예전에는 여기서 한 파일을 두 번 덮어썼다.
    show("slice_columns(A, tag='dbg')", data.slice_columns(a, Y, "dbg"))
    show("slice_columns(B, tag='dbg')  ← 같은 태그", data.slice_columns(b, Y, "dbg"))
    made = sorted(p.name for p in (HERE / "outputs").glob("sub_dbg_*.csv"))
    print(f"\n   만들어진 파일 {len(made)}개: {made}")
    print("   두 개면 충돌이 없는 것이다. 하나면 덮어쓴 것이다.")


def do_ml() -> None:
    """Training. Put breakpoints on get_dummies at tools_ml.py:118 and features at :141.

    학습. 브레이크포인트는 tools_ml.py:118 get_dummies 와 :141 features 에.
    """
    data, ml = load("tools_data"), load("tools_ml")

    cols = "CURRENT_AGE,SEX,RACE_1,MARITAL_STATUS,n_diagnoses"
    sliced = json.loads(data.slice_columns(cols, Y, "dbgml"))
    print(f"\n   하위 데이터: {Path(sliced['path']).name}")

    result = json.loads(ml.train_and_score(sliced["path"], Y))
    print(f"   AUC {result['auc']}   학습 {result['n_train']} / 시험 {result['n_test']}")
    print(f"   features (원-핫 이전) {len(result['features'])}개: {result['features']}")
    print(f"   feature_importance 키 {len(result['feature_importance'])}개 — 원-핫 이후라 더 많다:")
    for k, v in list(result["feature_importance"].items())[:6]:
        print(f"      {k:<28} {v}")


def do_board() -> None:
    """Board. Read-only — this harness never writes anything to the board.

    판. 읽기만 한다 — 이 하네스는 판에 아무것도 쓰지 않는다.
    """
    board = load("tools_blackboard")

    async def go() -> None:
        show("read_board(run_tag='example')", await board.read_board("example"), limit=1200)
        show("read_results(run_tag='example')", await board.read_results("example"), limit=800)

    asyncio.run(go())


MODES = {"okf": do_okf, "data": do_data, "ml": do_ml, "board": do_board}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "okf"
    if mode not in MODES:
        sys.exit(f"모드는 {' / '.join(MODES)} 중 하나다. 받은 값: {mode!r}")
    print(f"번들   {os.environ.get('AGENTIC_OKF_BUNDLE_DIR', '(없음)')}")
    print(f"데이터 {os.environ.get('MEMSTARA_DATASET_PATH', '(없음)')}")
    MODES[mode]()
