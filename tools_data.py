#!/usr/bin/env python3
"""Data-tool MCP server — inspect the columns, slice a subset.

Core launches this file as a stdio subprocess. Same FastMCP shape as
`examples/mcp_server.py`.

**Configuration arrives only through the environment.** Same convention as core's
own OKF server (`AGENTIC_OKF_BUNDLE_DIR`): an agent never supplies a path.

    MEMSTARA_DATASET_PATH   source dataset CSV (required)
    MEMSTARA_OUTPUT_DIR     where sub-datasets are written (default: outputs/ beside this file)

WARNING: these must be on core's MCP subprocess env allowlist to reach this
process — see `mcp_allowed_env_vars` in `sandbox/settings.py`. Without them the
tools below return `{"error": ...}`.

Reading the environment inside the functions rather than at module scope is
deliberate. `os.environ[...]` at import time kills the server during startup, and
the caller sees only "failed to connect" with no indication of why.


==============================================================================
 이 파일을 읽는 법
==============================================================================

 데이터 담당 도구 서버. 도구가 **둘뿐**이다.

   describe_dataset()   이 데이터에 무슨 컬럼이 있고, 얼마나 비어 있나
   slice_columns(...)   고른 컬럼만 잘라 작은 CSV 로 저장한다

 이 파일은 `python tools_data.py` 로 **따로 뜨는 프로세스**다. 파이프라인이
 자식으로 띄우고 표준입출력으로 대화한다. 그래서 파이프라인에 디버거를 붙여도
 여기 브레이크포인트는 안 걸린다.

 사람이 직접 불러 보려면: `python debug_harness.py data`
"""

from __future__ import annotations

import hashlib     # 파일 이름에 넣을 짧은 지문(해시)을 만든다
import json        # 도구는 반드시 **문자열**을 돌려줘야 해서 JSON 으로 싼다
import os          # 환경변수
from pathlib import Path

import pandas as pd                      # 표 데이터를 다루는 라이브러리
from mcp.server.fastmcp import FastMCP    # MCP 서버를 만드는 도구

# 이 서버의 이름. 파이프라인이 "memstara-data" 로 찾는다.
# 자식 프로세스라 부모 디버거가 안 닿는다. MEMSTARA_DEBUGPY 에 이 서버 이름이
# 들어 있을 때만 디버거를 기다린다 — 없으면 아무 일도 하지 않는다. debug_hook.py 참고.
from debug_hook import quiet_child, wait_for_debugger

quiet_child()          # 자식이 켜질 때 찍는 잡음 세 가지를 끈다
wait_for_debugger('memstara-data')

mcp = FastMCP("memstara-data")

# 출력 폴더를 환경변수로 안 줬을 때 쓸 기본값 — 이 파일 옆의 outputs/.
_DEFAULT_OUT = Path(__file__).parent / "outputs"


def _dataset_path() -> Path:
    """원본 데이터 CSV 의 경로. 없으면 사람이 읽을 수 있는 오류를 던진다."""
    raw = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if not raw:
        # 그냥 KeyError 를 내지 않고 **어디를 고쳐야 하는지**까지 적는다.
        # 이 오류는 대개 allowlist 를 빠뜨려서 난다.
        raise RuntimeError(
            "MEMSTARA_DATASET_PATH is not set. Check that you exported it, and that it "
            "appears in mcp_allowed_env_vars in sandbox/settings.py."
        )
    path = Path(raw)
    if not path.is_file():
        raise RuntimeError(f"dataset file not found: {path}")
    return path


def _output_dir() -> Path:
    """잘라 낸 CSV 를 넣을 폴더. 없으면 만든다."""
    out = Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "").strip() or _DEFAULT_OUT)
    out.mkdir(parents=True, exist_ok=True)   # 이미 있어도 오류 안 남
    return out


@mcp.tool()
def describe_dataset() -> str:
    """Return the dataset's actual column names, row count, and how empty each column is.

    Call this FIRST, before choosing any columns. Concept names in the knowledge
    source and column names in the dataset are not the same thing (for example
    "body mass index" versus "bmi"). Choosing a column that does not exist wastes
    the trial.

    ``missing_pct`` lists only the columns that have gaps. A column can exist and
    still be nearly empty — the shared HIV cohort has a BMI column that is 90%
    blank — and a name alone cannot say so. Choosing such a column is close to
    choosing nothing, so check this before selecting.

    ↑ 요약: **컬럼을 고르기 전에 반드시 먼저 부르는 도구.** 지식원이 부르는 이름과
      데이터의 컬럼 이름은 다르다("body mass index" vs "bmi"). 없는 컬럼을 고르면
      그 시행은 헛돈다. 그리고 컬럼이 있어도 90% 가 비어 있으면 고른 것이나 마찬가지다.
    """
    try:
        df = pd.read_csv(_dataset_path())
    except Exception as e:
        # 도구는 예외를 던지지 않고 {"error": ...} 를 돌려준다. 그래야 에이전트가
        # 읽고 판단할 수 있다 — 예외는 에이전트에게 "도구가 고장났다"로만 보인다.
        return json.dumps({"error": str(e)})

    # 결과 컬럼(outcome)은 에이전트에게 노출하지 않는다.
    # feature로 선택하면 답을 입력에 넣는 것 — data leakage.
    # reviewer's build_catalog.py 와 동일한 원천 차단 방식.
    outcome_col = os.environ.get("MEMSTARA_OUTCOME_COLUMN", "").strip()
    feature_cols = [c for c in df.columns if c != outcome_col] if outcome_col else list(df.columns)

    # 컬럼마다 결측 비율. isna() 가 True/False 표를 주고, mean() 이 그 평균 = 비율.
    missing = df[feature_cols].isna().mean()

    return json.dumps(
        {
            "n_rows": int(len(df)),
            "n_columns": len(feature_cols),
            "columns": feature_cols,
            # 결측이 **있는 컬럼만** 싣는다. 0% 짜리까지 다 실으면 목록이 길어지고,
            # 그 길이는 이후 모든 라운드의 대화에 계속 실려 간다.
            "missing_pct": {c: round(float(v) * 100, 1) for c, v in missing.items() if v > 0},
        }
    )


@mcp.tool()
def slice_columns(columns: list[str], y_column: str, tag: str) -> str:
    """Extract the named columns plus the outcome into a sub-dataset CSV.

    Args:
        columns: a LIST of column names, one name per element, e.g.
            ["BMI", "LAB__HDL CHOLESTEROL, DIRECT", "CURRENT_AGE"]. Pass them
            exactly as `describe_dataset` or the matcher spelled them, commas
            and all — this is a list, not a comma-separated string.
        y_column: name of the outcome column.
        tag: identifier used in the output filename, e.g. "t03"

    Returns:
        JSON with path, n_rows, columns_used and columns_missing. A non-empty
        columns_missing means those names are not in the dataset — check the
        spelling against describe_dataset and report what stays missing.

    A LIST rather than a comma-separated string, because 158 of this cohort's
    1,393 columns carry a comma inside the name (`DX__E78.5__Hyperlipidemia,
    unspecified`, `LAB__HDL CHOLESTEROL, DIRECT`). Splitting on commas cut each
    of those into two names that exist nowhere, and the old docstring told the
    agent to read that as "the knowledge source's names diverged from the
    dataset's" — a wrong diagnosis of a bug in this function. `match_concepts`
    already takes a list; the two tools now agree.

    ↑ 요약: 고른 컬럼 + 결과변수만 남긴 작은 CSV 를 만들고 그 경로를 돌려준다.
      **컬럼은 쉼표로 이은 문자열이 아니라 목록으로 준다.** 이 코호트의 컬럼
      1,393개 중 158개가 이름 안에 쉼표를 갖고 있어서, 쉼표로 쪼개면 그 158개가
      존재하지 않는 이름 두 조각으로 부서졌다.
      `columns_missing` 이 비어 있지 않으면 그 이름이 데이터에 없다는 뜻이다.
    """
    try:
        df = pd.read_csv(_dataset_path())
        out_dir = _output_dir()
    except Exception as e:
        return json.dumps({"error": str(e)})

    # outcome 컬럼 — describe_dataset 에서와 같은 방어선.
    # y_column 이름이 틀려도(예: "outcome" vs "HIV_DETECTABLE") 환경변수로 이중 차단.
    outcome_col = os.environ.get("MEMSTARA_OUTCOME_COLUMN", "").strip()

    # A bare string is refused rather than iterated. Python would iterate it
    # character by character and hand back 30 single-letter names in
    # columns_missing — a failure that reads like a naming problem and is not one.
    if isinstance(columns, str):
        return json.dumps(
            {
                "error": "columns must be a list of column names, not a string",
                "hint": 'Pass ["BMI", "LAB__HDL CHOLESTEROL, DIRECT"], not '
                '"BMI, LAB__HDL CHOLESTEROL, DIRECT". Column names contain commas, '
                "so a comma-separated string cannot be split back apart.",
            }
        )

    # Surrounding whitespace is stripped and empty entries dropped; the name
    # itself, commas included, is left exactly as given.
    wanted = [str(c).strip() for c in columns if str(c).strip()]
    # outcome 컬럼이 feature 목록에 섞여 있으면 조용히 제거한다 (leakage 원천 차단).
    if outcome_col:
        wanted = [c for c in wanted if c != outcome_col]
    if not wanted:
        return json.dumps({"error": "columns is empty"})

    if y_column not in df.columns:
        # 결과변수가 없으면 아무것도 할 수 없다.
        # 오류 메시지의 컬럼 목록에서도 outcome 을 숨긴다 — 에이전트가 그 이름을 알면
        # 다음 호출에서 feature 로 쓸 수 있어 누수가 된다.
        safe_cols = [c for c in df.columns if c != outcome_col] if outcome_col else list(df.columns)
        return json.dumps(
            {"error": f"y_column '{y_column}' is not in the dataset", "columns": safe_cols}
        )

    # Feeding the outcome back in as a feature is leakage. Drop it if requested.
    # ↑ 결과변수를 특징으로 다시 넣으면 누수(leakage)다 — 답을 보고 답을 맞히는 셈이라
    #   AUC 가 1.0 에 가깝게 나오고 아무 의미가 없다. 요청에 들어 있어도 뺀다.
    present = [c for c in wanted if c in df.columns and c != y_column]   # 실제로 있는 것
    missing = [c for c in wanted if c not in df.columns]                 # 없는 것

    if not present:
        return json.dumps(
            {
                "error": "none of the requested columns exist in the dataset",
                "columns_missing": missing,
                "hint": "Call describe_dataset to see the real column names.",
            }
        )

    # The tag reaches the filesystem, so strip anything that could traverse it.
    # ↑ tag 는 에이전트가 정한 문자열이고 그대로 파일 이름이 된다. "../../etc/passwd"
    #   같은 것이 들어오면 안 되므로 영숫자와 -_ 만 남기고 40자로 자른다.
    safe_tag = "".join(ch for ch in tag if ch.isalnum() or ch in "-_")[:40] or "untagged"

    # The filename carries a digest of the request, not the tag alone. The tag is chosen
    # by an agent, and on a board run three data agents pick it independently — nothing
    # makes them differ. On run `example` all three chose the run tag, so all three wrote
    # `sub_example.csv` in turn and each ml stage trained on whichever slice happened to
    # be on disk at that moment. Every AUC on the board belonged to a different
    # hypothesis than the row it sat in:
    #
    #     task 90 (8 cols) recorded 0.6443, its own columns score 0.6175
    #     task 91 (7 cols) recorded 0.6169, its own columns score 0.6443
    #     task 92 (5 cols) recorded 0.6169  — the only one that was its own
    #
    # Nothing failed and nothing warned. The earlier NHANES run survived only because
    # its agents happened to pick t86/t87/t88.
    #
    # Hashed in the order given, not sorted: the CSV is written in that order too, so
    # sorting would map two genuinely different files onto one name and reopen the same
    # silent overwrite. Identical requests still land on one file with one content,
    # which is what makes a repeat idempotent rather than a collision.
    #
    # ↑ 한국어 요약: 파일 이름을 **태그만으로** 정하면 안 된다. 태그는 에이전트가
    #   고르는데 셋이 서로 다르게 고를 이유가 없다. 실제로 셋 다 같은 태그를 골라
    #   한 파일을 세 번 덮어썼고, 판에 적힌 AUC 가 전부 다른 가설의 것이 됐다.
    #   그래서 **요청 내용(컬럼 + 결과변수)의 지문**을 이름에 붙인다.
    #   - 컬럼이 다르면 이름이 달라진다 → 덮어쓸 수 없다
    #   - 같은 요청이면 같은 이름 · 같은 내용 → 다시 해도 안전하다
    #   정렬하지 않고 **준 순서 그대로** 해싱한다. CSV 도 그 순서로 쓰이기 때문에,
    #   정렬하면 서로 다른 두 파일이 한 이름으로 몰려 같은 문제가 되살아난다.
    digest = hashlib.sha1("|".join(present + [y_column]).encode("utf-8")).hexdigest()[:8]
    out_path = out_dir / f"sub_{safe_tag}_{digest}.csv"

    # 고른 컬럼 + 결과변수. 결과변수를 **맨 뒤**에 두는 것이 이 프로젝트의 약속이다.
    subset = df[present + [y_column]]
    subset.to_csv(out_path, index=False)   # index=False — 줄 번호 컬럼을 안 만든다

    return json.dumps(
        {
            "path": str(out_path),          # 다음 단계(ml)가 이 경로로 학습한다
            "n_rows": int(len(subset)),
            "columns_used": present + [y_column],
            "columns_missing": missing,     # 비어 있지 않으면 이름이 어긋났다는 신호
        }
    )


if __name__ == "__main__":
    # 이 파일이 직접 실행될 때만 서버로 뜬다. import 될 때는 안 뜬다 —
    # debug_harness.py 가 함수만 빌려 쓸 수 있는 이유다.
    mcp.run()
